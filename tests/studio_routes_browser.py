"""Chromium smoke for the Portal's actual Ironmate-generated Studio routes."""
import functools
import importlib.util
import json
import re
import struct
import subprocess
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import zipfile
import zlib
from xml.etree import ElementTree

import pytest
from playwright.sync_api import expect, sync_playwright


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


def _fixture_png():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    row = b"\x00" + b"\xff\x00\x00" * 9 + b"\x00\x00\xff" * 10
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 19, 13, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(row * 13))
        + chunk(b"IEND", b"")
    )


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
        expect(page.locator("#board svg")).to_have_count(1)
        page.locator("#image").set_input_files({"name": "fixture.png", "mimeType": "image/png", "buffer": _fixture_png()})
        expect(page.locator("#layers button").filter(has_text="fixture.png")).to_have_count(1)
        page.locator("#cell").fill("7")
        page.locator("#cell").dispatch_event("change")
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


@pytest.mark.parametrize("mobile", [False, True], ids=["desktop", "touch-390"])
def test_studio_csp_admits_the_tools_chrome(browser, studio_origin, mobile):
    """🧰 The studios allow neither inline scripts nor inline styles; the modules and sheets of the chrome and 🚪 Door-to-Door are
    listed by hash, so the board's clock runs and its buttons are drawn (☰: 48px at the edge of a desktop, 40px in a phone's header), with no CSP report."""
    page = _page(browser, studio_origin, mobile=mobile)
    try:
        blocked = []
        page.on("console", lambda message: blocked.append(message.text) if "Content Security Policy" in message.text else None)
        assert page.goto(studio_origin + "/tools/image-studio/").ok
        expect(page.locator(".ui-chrome [data-clock]")).to_have_text(re.compile(r"^\d\d:\d\d:\d\d$"))
        box = page.locator('.ui-chrome [data-menu="spots"] > summary').bounding_box()
        assert (box["width"], box["height"]) == ((40, 40) if mobile else (48, 48)), box
        assert page.evaluate("getComputedStyle(document.querySelector('.ui-chrome .ui-board-run')).animationDuration") != "24s"   # set by the script
        page.locator('.ui-chrome [data-menu="spots"] > summary').click()
        expect(page.locator(".ui-chrome .ui-world-spots a[aria-current=page]")).to_have_text(re.compile("^📍"))   # ☰ this page, then its sections
        assert page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") == 0
        door = page.locator(".ui-door-foot [data-door-select]")                 # 🚪 Door-to-Door's sheet and module are listed too
        assert door.is_visible() and door.bounding_box()["height"] == 40 and door.input_value() == "../../tools/image-studio/"
        assert blocked == [], blocked
    finally:
        page.context.close()


def test_slide_studio_import_edit_and_export_pptx(browser, studio_origin):
    from io import BytesIO

    page = _page(browser, studio_origin)
    try:
        assert page.goto(studio_origin + "/tools/slide-studio/").ok
        assert page.locator('[data-testid="portfolio-back"]').count() == 1
        expect(page.locator("#slide-select option")).to_have_count(1)
        page.locator("#slide-template").click()
        expect(page.locator("#layers button")).to_have_count(2)
        deck = json.loads(_download(page, "#deck-save"))
        assert deck["schema"] == "ironmate-slide-deck/1"
        deck["slides"][0]["layers"][0]["text"] = "Imported fixture title"
        page.locator("#deck-open").set_input_files({
            "name": "fixture.json", "mimeType": "application/json", "buffer": json.dumps(deck).encode(),
        })
        expect(page.locator("#deck-status")).to_have_text("全スライドを読み込みました。")
        title_id = deck["slides"][0]["layers"][0]["id"]
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
