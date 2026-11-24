"""Chromium smoke for the Portal's actual Ironmate-generated Studio routes."""
import functools
import importlib.util
import json
import subprocess
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import zipfile
from xml.etree import ElementTree

import pytest
from playwright.sync_api import sync_playwright


@pytest.fixture(scope="module")
def studio_origin(tmp_path_factory):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("project_pages", root / "scripts/project_pages.py")
    pages = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pages)
    site = tmp_path_factory.mktemp("portfolio-studios")
    pages.build(site)
    ironmate = root / ".test-deps/ironmate-studio"
    sha = subprocess.check_output(["git", "-C", str(ironmate), "rev-parse", "HEAD"], text=True).strip()
    receipt = pages.collect_tools(site, {"ironmate": ironmate}, {"ironmate": sha})
    assert receipt["made"] == ["ironmate"] and not receipt["failed"], receipt
    assert not (site / "tools/ironmate").exists()
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(SimpleHTTPRequestHandler, directory=site))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chromium")
        yield browser
        browser.close()


def _page(browser, origin, *, mobile=False):
    context = browser.new_context(
        viewport={"width": 390, "height": 844} if mobile else {"width": 1200, "height": 900},
        is_mobile=mobile, has_touch=mobile,
    )
    page = context.new_page()
    page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(origin + "/") else route.abort())
    return page


def _download(page, selector):
    with page.expect_download() as pending:
        page.locator(selector).click()
    return pending.value.path().read_bytes()


@pytest.mark.parametrize("mobile", [False, True], ids=["desktop", "touch-390"])
def test_image_studio_import_edit_and_download(browser, studio_origin, mobile):
    page = _page(browser, studio_origin, mobile=mobile)
    try:
        assert page.goto(studio_origin + "/tools/image-studio/").ok
        assert page.locator('[data-testid="portfolio-back"]').count() == 1
        page.wait_for_function("!!window.IronmateStudio")
        png = page.evaluate("""() => {
            const c = Object.assign(document.createElement('canvas'), {width: 19, height: 13});
            const ctx = c.getContext('2d');
            ctx.fillStyle = '#ff0000'; ctx.fillRect(0, 0, 9, 13);
            ctx.fillStyle = '#0000ff'; ctx.fillRect(9, 0, 10, 13);
            return Array.from(atob(c.toDataURL('image/png').split(',')[1]), c => c.charCodeAt(0));
        }""")
        page.locator("#image").set_input_files({"name": "fixture.png", "mimeType": "image/png", "buffer": bytes(png)})
        page.wait_for_function("IronmateStudio.scene.layers.at(-1)?.kind === 'image'")
        page.evaluate("IronmateStudio.ready")
        page.locator("#cell").fill("7")
        page.locator("#cell").dispatch_event("change")
        page.evaluate("IronmateStudio.ready")
        scene = json.loads(_download(page, "#save"))
        assert scene["schema"] == "ironmate-image-studio/1"
        assert scene["layers"][-1]["kind"] == "image"
        assert scene["layers"][-1]["cell"] == 7
        png = _download(page, "#png")
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        assert int.from_bytes(png[16:20], "big") == scene["width"]
        assert int.from_bytes(png[20:24], "big") == scene["height"]
    finally:
        page.context.close()


def test_slide_studio_import_edit_and_export_pptx(browser, studio_origin):
    from io import BytesIO

    page = _page(browser, studio_origin)
    try:
        assert page.goto(studio_origin + "/tools/slide-studio/").ok
        assert page.locator('[data-testid="portfolio-back"]').count() == 1
        page.wait_for_function("!!window.IronmateSlideEditor")
        page.locator("#slide-template").click()
        page.wait_for_function("IronmateStudio.scene.layers.length === 2")
        deck = json.loads(_download(page, "#deck-save"))
        assert deck["schema"] == "ironmate-slide-deck/1"
        deck["slides"][0]["layers"][0]["text"] = "Imported fixture title"
        page.locator("#deck-open").set_input_files({
            "name": "fixture.json", "mimeType": "application/json", "buffer": json.dumps(deck).encode(),
        })
        page.wait_for_function("IronmateStudio.scene.layers[0]?.text === 'Imported fixture title'")
        title_id = page.evaluate("IronmateStudio.scene.layers[0].id")
        page.locator(f'[data-layer-id="{title_id}"]').click()
        page.locator("#text").fill("Edited fixture title")
        page.locator("#apply-text").click()
        saved = json.loads(_download(page, "#deck-save"))
        assert saved["slides"][0]["layers"][0]["text"] == "Edited fixture title"
        pptx = _download(page, "#deck-pptx")
        with zipfile.ZipFile(BytesIO(pptx)) as office:
            xml = ElementTree.fromstring(office.read("ppt/slides/slide1.xml"))
            text = [node.text for node in xml.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}t")]
            assert "Edited fixture title" in text
    finally:
        page.context.close()
