"""Chromium smoke for Ironmate's generated studios as the one screen's framed panels (tools/#slide-studio and #browser-tools)."""
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
    ironmate = root / ".test-deps/ironmate-studio"
    sha = subprocess.check_output(["git", "-C", str(ironmate), "rev-parse", "HEAD"], text=True).strip()
    repository = "myon-bioinformatics/Ironmate"
    receipt = pages.collect_tools(site, {repository: ironmate}, {repository: sha})   # 🧰 the tools first: the screen takes them in
    assert receipt["made"] == ["slide-studio", "browser-tools"] and not receipt["failed"], receipt
    pages.build(site)
    assert sorted(file.relative_to(site).as_posix() for file in site.rglob("*.html")) == [
        "index.html", "tools/index.html",
    ]  # Published HTML remains two pages; hosted Ironmate documents live in views.
    assert not (site / "tools/ironmate").exists() and not list((site / "tools").glob("*-studio/index.html"))
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


def _studio(page, origin, name):
    """🖼️ The one screen opened at a studio's #panel, and the studio's own document (its frame)."""
    assert page.goto(f"{origin}/tools/#{name}").ok
    page.wait_for_function(f"() => document.querySelector('#{name} iframe')?.dataset.ready")
    return page.locator(f"#{name} iframe").element_handle().content_frame()


def _download(page, locator):
    with page.expect_download() as pending:
        locator.click()
    return pending.value.path().read_bytes()


def _imported(page, studio, face, file):
    studio.locator('#slides-toolbar [data-act="import"]').click()
    with page.expect_file_chooser() as chosen:
        studio.locator(f'#slides-candidates button[aria-label^="{face}"]').click()
    chosen.value.set_files(file)


@pytest.mark.parametrize("mobile", [False, True], ids=["desktop", "touch-390"])
def test_unified_studio_imports_an_image_and_undoes_it(browser, studio_origin, mobile):
    page = _page(browser, studio_origin, mobile=mobile)
    try:
        studio = _studio(page, studio_origin, "slide-studio")
        _imported(page, studio, "画像", {"name": "fixture.png", "mimeType": "image/png", "buffer": _fixture_png()})
        studio.wait_for_function("""() => IronmateSlideStudio.deck.slides[0].layers.some(
            layer => layer.kind === 'image' && layer.src.startsWith('data:image/png'))""")
        studio.locator('[data-act="export"]').click()
        png = _download(page, studio.locator('#slides-candidates button[aria-label^="PNG"]'))
        assert png[:8].hex() == "89504e470d0a1a0a"
        studio.locator('[data-act="undo"]').click()
        studio.wait_for_function("() => IronmateSlideStudio.deck.slides[0].layers.length === 0")
    finally:
        page.context.close()


@pytest.mark.parametrize("mobile", [False, True], ids=["desktop", "touch-390"])
def test_studio_csp_admits_the_tools_chrome(browser, studio_origin, mobile):
    """🧰 A studio allows neither inline scripts nor inline styles, and keeps that CSP whole in its frame: the screen's chrome and
    🚪 Door-to-Door are outside it, so the board's clock runs and its buttons are drawn (☰: 48px at the edge of a desktop, 40px in a
    phone's header), and the studio reports no CSP refusal."""
    page = _page(browser, studio_origin, mobile=mobile)
    try:
        blocked = []
        page.on("console", lambda message: blocked.append(message.text) if "Content Security Policy" in message.text else None)
        studio = _studio(page, studio_origin, "slide-studio")
        assert "script-src 'self';" in studio.evaluate("document.querySelector('meta[http-equiv=Content-Security-Policy]').content")
        expect(page.locator(".ui-chrome [data-clock]")).to_have_text(re.compile(r"^\d\d:\d\d:\d\d$"))
        box = page.locator('.ui-chrome [data-menu="spots"] > summary').bounding_box()
        assert (box["width"], box["height"]) == ((40, 40) if mobile else (48, 48)), box
        assert page.evaluate("getComputedStyle(document.querySelector('.ui-chrome .ui-board-run')).animationDuration") != "24s"   # set by the script
        page.locator('.ui-chrome [data-menu="spots"] > summary').click()
        expect(page.locator(".ui-chrome .ui-world-spots a[aria-current=page]")).to_have_text(re.compile("^📍"))   # ☰ this page, then its sections
        assert page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") == 0
        door = page.locator(".ui-door-foot [data-door-select]")                 # 🚪 Door-to-Door's sheet and module are listed too
        assert door.is_visible() and door.bounding_box()["height"] == 40 and door.input_value() == "../tools/#slide-studio"
        assert blocked == [], blocked
    finally:
        page.context.close()


@pytest.mark.parametrize("mobile", [False, True], ids=["desktop", "touch-390"])
def test_the_one_slide_editor_opens_a_deck_and_exports_pptx(browser, studio_origin, mobile):
    """📽️ /tools/slide-studio/ is Ironmate's one slide editor, phone-first and the same page on a PC."""
    from io import BytesIO

    page = _page(browser, studio_origin, mobile=mobile)
    try:
        studio = _studio(page, studio_origin, "slide-studio")
        studio.wait_for_function("() => !!window.IronmateSlideStudio")
        assert studio.locator('[data-testid="portfolio-back"]').count() == 0
        expect(page.locator(".ui-chrome a.ui-world-home")).to_have_count(1)
        studio.locator('[data-act="text"]').click()
        page.keyboard.type("Portfolio fixture")
        studio.locator('[data-act="export"]').click()                            # 📤 then the format, in the candidate row
        deck = json.loads(_download(page, studio.locator('#slides-candidates button[aria-label^="JSON"]')))
        assert deck["schema"] == "ironmate-slide-deck/1" and deck["slides"][0]["layers"][0]["text"] == "Portfolio fixture"
        deck["slides"][0]["layers"][0]["text"] = "Imported fixture title"
        studio.locator('[data-act="import"]').click()                            # 📥 どの形式から？ JSON: the file chooser it opens
        with page.expect_file_chooser() as chosen:
            studio.locator('#slides-candidates button[aria-label^="JSON"]').click()
        chosen.value.set_files({"name": "fixture.json", "mimeType": "application/json", "buffer": json.dumps(deck).encode()})
        studio.wait_for_function("() => IronmateSlideStudio.deck.slides[0].layers[0].text === 'Imported fixture title'")
        if not studio.locator("#slides-candidates").is_visible():
            studio.locator('[data-act="export"]').click()
        pptx = _download(page, studio.locator('#slides-candidates button[aria-label^="PPTX"]'))
        with zipfile.ZipFile(BytesIO(pptx)) as office:
            xml = ElementTree.fromstring(office.read("ppt/slides/slide1.xml"))
            text = [node.text for node in xml.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}t")]
            assert "Imported fixture title" in text
    finally:
        page.context.close()


@pytest.mark.parametrize("mobile", [False, True], ids=["desktop", "touch-390"])
def test_pixel_art_in_unified_editor_exports_svg_and_undoes(browser, studio_origin, mobile):
    """A pixel grid is placed in the shared editor, exported and undone via Portfolio on both layouts."""
    page = _page(browser, studio_origin, mobile=mobile)
    try:
        studio = _studio(page, studio_origin, "slide-studio")
        studio.locator("#pixel-editor summary").click()
        studio.wait_for_function("() => !!window.IronmateWorkbench?.grid")
        studio.locator("#generate").click()
        before = studio.evaluate("IronmateSlideStudio.deck.slides[IronmateSlideStudio.active].layers.length")
        studio.locator("#place-grid").click()
        studio.wait_for_function(
            """n => IronmateSlideStudio.deck.slides[IronmateSlideStudio.active].layers.length === n + 1""", arg=before
        )
        art = studio.evaluate("IronmateSlideStudio.deck.slides[IronmateSlideStudio.active].layers.at(-1)")
        assert art["kind"] == "image" and art["sampling"] == "pixelated"
        studio.locator('[data-act="export"]').click()
        svg = _download(page, studio.locator('#slides-candidates button[aria-label^="SVG"]'))
        assert b"<svg" in svg[:1024]
        studio.locator('[data-act="undo"]').click()
        studio.wait_for_function(
            """n => IronmateSlideStudio.deck.slides[IronmateSlideStudio.active].layers.length === n""", arg=before
        )
        assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    finally:
        page.context.close()


def test_the_old_slide_addresses_are_gone(browser, studio_origin):
    """🗑 /tools/slide-studio/ and its phone/ and pc/ (Ironmate's forward-only pages) are not published: the studio is the screen's
    #slide-studio, one editor, one address."""
    page = _page(browser, studio_origin)
    try:
        assert [page.request.get(studio_origin + "/tools/slide-studio/" + old).status for old in ("index.html", "phone/", "pc/")] == [404] * 3
    finally:
        page.context.close()


@pytest.mark.parametrize("mobile", [False, True], ids=["desktop", "touch-390"])
@pytest.mark.parametrize("route", ["home", "slide-studio/", "browser-tools/"])
def test_studio_has_one_tools_destination(browser, studio_origin, mobile, route):
    page = _page(browser, studio_origin, mobile=mobile)
    try:
        if route == "home":
            assert page.goto(studio_origin + "/tools/#home").ok
        else:
            _studio(page, studio_origin, route.removesuffix("/"))
        target = studio_origin + "/index.html#tools"
        links = page.locator("a[href]").evaluate_all(  # Include hidden anchors, not only visible ones.
            "(anchors, target) => anchors.filter(a => a.href === target).length", target
        )
        assert links == 1
        home = page.locator(".ui-chrome a.ui-world-home")
        expect(home).to_be_visible()
        home.click()
        page.wait_for_url(target)
    finally:
        page.context.close()


@pytest.mark.parametrize("mobile", [False, True], ids=["desktop", "touch-390"])
def test_heatmap_scene_opens_in_unified_editor_and_browser_tools_remain(browser, studio_origin, mobile):
    page = _page(browser, studio_origin, mobile=mobile)
    try:
        tools = _studio(page, studio_origin, "browser-tools")
        expect(tools.locator("header a.brand")).to_have_count(0)
        assert tools.locator("#brand a[download]").count() > 0
        tools.get_by_role("link", name="📽️ 工房で編集 ↗").click()
        page.wait_for_url("**/tools/#slide-studio")
        page.wait_for_function("() => document.querySelector('#slide-studio iframe')?.dataset.ready")
        studio = page.locator("#slide-studio iframe").element_handle().content_frame()
        scene = {"schema": "ironmate-image-studio/1", "width": 640, "height": 480, "background": "#FFFFFF", "layers": [
            {"id": "heat", "kind": "heatmap", "name": "heat", "x": 40, "y": 40, "w": 560, "h": 400,
             "rotation": 0, "opacity": 1, "z": [[1, 2], [3, 4]], "xlabels": ["a", "b"], "ylabels": ["c", "d"],
             "low": 1, "high": 4, "levels": 0, "labels": True},
        ]}
        _imported(page, studio, "JSON", {"name": "scene.json", "mimeType": "application/json",
                                        "buffer": json.dumps(scene).encode()})
        studio.wait_for_function("""() => {
            const slide = IronmateSlideStudio.deck.slides[0];
            return slide.width === 640 && slide.height === 480 && slide.layers[0]?.kind === 'heatmap';
        }""")
        assert page.locator("#image-studio").count() == 0
    finally:
        page.context.close()


def test_the_screens_header_carries_the_studio_switch_and_colours(browser, studio_origin):
    """🧰 The one screen's header places what the open studio brings: one ⋯ 💻 To textual ⇄ 📱 To iconic (the studio's own row, or
    PySaiyanWeBoo's for the switch it holds), which flips the studio inside its frame; ⚙️ 🎨 recolours the studio too, and
    "this page's own" gives it its own look back. Another panel takes the row away."""
    page = _page(browser, studio_origin)
    try:
        studio = _studio(page, studio_origin, "slide-studio")
        rows = page.locator('.ui-chrome [data-chrome-hosted] [data-chrome-action="labels"]')
        expect(rows).to_have_count(1)
        before, own = studio.evaluate("[document.body.dataset.uiLabels, document.body.dataset.uiTheme]")
        page.click('.ui-chrome [data-menu="more"] > summary')
        rows.click()
        assert studio.evaluate("document.body.dataset.uiLabels") == ("emoji" if before == "words" else "words")
        page.click('.ui-chrome [data-menu="settings"] > summary')
        page.select_option(".ui-chrome [data-ui-theme-switch]", "purple")
        assert studio.evaluate("document.body.dataset.uiTheme") == "purple"
        page.select_option(".ui-chrome [data-ui-theme-switch]", "")
        assert studio.evaluate("document.body.dataset.uiTheme") == own
        page.evaluate("location.hash = 'home'")
        expect(rows).to_have_count(0)
    finally:
        page.context.close()
