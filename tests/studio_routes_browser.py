"""Chromium smoke for Ironmate's generated studios as the one screen's framed panels (tools/#image-studio, #slide-studio, #browser-tools)."""
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
    receipt = pages.collect_tools(site, {"ironmate": ironmate}, {"ironmate": sha})   # 🧰 the tools first: the screen takes them in
    assert receipt["made"] == ["ironmate"] and not receipt["failed"], receipt
    pages.build(site)
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


def _saved(page, studio, face):
    """💾 Image Studio saves with its own 📤 どの形式に？: the toolbar's candidates, hidden again after each pick."""
    studio.locator('#studio-toolbar [data-act="export"]').click()
    return _download(page, studio.locator(f'#studio-candidates button:text-is("{face}")'))


def _imported(page, studio, face, file):
    """📥 どの形式から？: the toolbar's candidate opens the toolbar's own file chooser (the page has no input of its own)."""
    studio.locator('#studio-toolbar [data-act="import"]').click()
    with page.expect_file_chooser() as chosen:
        studio.locator(f'#studio-candidates button:text-is("{face}")').click()
    chosen.value.set_files(file)


@pytest.mark.parametrize("mobile", [False, True], ids=["desktop", "touch-390"])
def test_image_studio_import_edit_and_download(browser, studio_origin, mobile):
    page = _page(browser, studio_origin, mobile=mobile)
    try:
        studio = _studio(page, studio_origin, "image-studio")
        assert studio.locator('[data-testid="portfolio-back"]').count() == 0      # 🖼️ the way back and the chrome are the screen's
        expect(page.locator(".ui-chrome a.ui-world-home")).to_have_count(1)
        expect(studio.locator("#board svg")).to_have_count(1)
        _imported(page, studio, "画像", {"name": "fixture.png", "mimeType": "image/png", "buffer": _fixture_png()})
        expect(studio.locator("#layers button").filter(has_text="fixture.png")).to_have_count(1)
        studio.locator("#cell").fill("7")
        studio.locator("#cell").dispatch_event("change")
        expect(studio.locator('#studio-toolbar [data-act="export"]')).to_be_visible()   # 💾 its own 📤
        scene = json.loads(_saved(page, studio, "JSON"))
        assert scene["schema"] == "ironmate-image-studio/1"
        assert scene["layers"][-1]["kind"] == "image"
        assert scene["layers"][-1]["cell"] == 7
        png = _saved(page, studio, "PNG")
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        assert int.from_bytes(png[16:20], "big") == scene["width"]
        assert int.from_bytes(png[20:24], "big") == scene["height"]
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
        studio = _studio(page, studio_origin, "image-studio")
        assert "script-src 'self';" in studio.evaluate("document.querySelector('meta[http-equiv=Content-Security-Policy]').content")
        expect(page.locator(".ui-chrome [data-clock]")).to_have_text(re.compile(r"^\d\d:\d\d:\d\d$"))
        box = page.locator('.ui-chrome [data-menu="spots"] > summary').bounding_box()
        assert (box["width"], box["height"]) == ((40, 40) if mobile else (48, 48)), box
        assert page.evaluate("getComputedStyle(document.querySelector('.ui-chrome .ui-board-run')).animationDuration") != "24s"   # set by the script
        page.locator('.ui-chrome [data-menu="spots"] > summary').click()
        expect(page.locator(".ui-chrome .ui-world-spots a[aria-current=page]")).to_have_text(re.compile("^📍"))   # ☰ this page, then its sections
        assert page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") == 0
        door = page.locator(".ui-door-foot [data-door-select]")                 # 🚪 Door-to-Door's sheet and module are listed too
        assert door.is_visible() and door.bounding_box()["height"] == 40 and door.input_value() == "../tools/#image-studio"
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
        studio.wait_for_function("() => !!window.IronmatePhone")
        assert studio.locator('[data-testid="portfolio-back"]').count() == 0
        expect(page.locator(".ui-chrome a.ui-world-home")).to_have_count(1)
        studio.locator('[data-act="text"]').click()
        page.keyboard.type("Portfolio fixture")
        studio.locator('[data-act="export"]').click()                            # 📤 then the format, in the candidate row
        deck = json.loads(_download(page, studio.locator('#phone-candidates button[aria-label^="JSON"]')))
        assert deck["schema"] == "ironmate-slide-deck/1" and deck["slides"][0]["layers"][0]["text"] == "Portfolio fixture"
        deck["slides"][0]["layers"][0]["text"] = "Imported fixture title"
        studio.locator('[data-act="import"]').click()                            # 📥 どの形式から？ JSON: the file chooser it opens
        with page.expect_file_chooser() as chosen:
            studio.locator('#phone-candidates button[aria-label^="JSON"]').click()
        chosen.value.set_files({"name": "fixture.json", "mimeType": "application/json", "buffer": json.dumps(deck).encode()})
        studio.wait_for_function("() => IronmatePhone.deck.slides[0].layers[0].text === 'Imported fixture title'")
        if not studio.locator("#phone-candidates").is_visible():
            studio.locator('[data-act="export"]').click()
        pptx = _download(page, studio.locator('#phone-candidates button[aria-label^="PPTX"]'))
        with zipfile.ZipFile(BytesIO(pptx)) as office:
            xml = ElementTree.fromstring(office.read("ppt/slides/slide1.xml"))
            text = [node.text for node in xml.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}t")]
            assert "Imported fixture title" in text
    finally:
        page.context.close()


def test_the_old_slide_addresses_are_gone(browser, studio_origin):
    """🗑 /tools/slide-studio/ and its phone/ and pc/ (Ironmate's forward-only pages) are not published: the studio is the screen's
    #slide-studio, one editor, one address."""
    page = _page(browser, studio_origin)
    try:
        assert [page.request.get(studio_origin + "/tools/slide-studio/" + old).status for old in ("", "phone/", "pc/")] == [404] * 3
    finally:
        page.context.close()


@pytest.mark.parametrize("mobile", [False, True], ids=["desktop", "touch-390"])
@pytest.mark.parametrize("route", ["home", "image-studio/", "slide-studio/", "browser-tools/"])
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
def test_image_shelf_sends_current_png_to_slide_in_the_same_tab(browser, studio_origin, mobile):
    page = _page(browser, studio_origin, mobile=mobile)
    try:
        studio = _studio(page, studio_origin, "image-studio")
        _imported(page, studio, "画像", {"name": "fixture.png", "mimeType": "image/png", "buffer": _fixture_png()})
        layer = studio.locator("#layers button").filter(has_text="fixture.png")
        expect(layer).to_have_count(1)
        link = studio.get_by_role("link", name="編集中の画像をスライド工房へ")
        errors = []
        page.on("console", lambda m: errors.append(m.text) if "Content Security Policy" in m.text else None)
        for _ in range(2):  # first on a cold destination, then in the already-mounted editor
            studio.locator('#studio-toolbar [data-act="import"]').click()           # 📥 どの形式から？ → シェルフ
            studio.locator('#studio-candidates button:text-is("シェルフ")').click()
            expect(link).to_have_attribute("href", "/tools/#slide-studio")
            link.click()
            page.wait_for_url("**/tools/#slide-studio")
            slide = page.locator("#slide-studio iframe").element_handle().content_frame()
            slide.wait_for_function("""() => {
                const layers = window.IronmatePhone?.deck.slides[0].layers;
                return layers?.length === 1 && layers[0].kind === 'image' && layers[0].src.startsWith('data:image/png');
            }""")
            assert slide.evaluate("""async () => {
                const img = new Image();
                img.src = IronmatePhone.deck.slides[0].layers[0].src;
                await img.decode();
                const canvas = document.createElement('canvas');
                canvas.width = img.width;
                canvas.height = img.height;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0);
                return [[150, 180], [700, 180]].map(([x, y]) => Array.from(ctx.getImageData(x, y, 1, 1).data));
            }""") == [[255, 0, 0, 255], [0, 0, 255, 255]]
            assert len(page.context.pages) == 1
            slide.locator('[data-act="undo"]').click()
            slide.wait_for_function("() => IronmatePhone.deck.slides[0].layers.length === 0")
            page.go_back()
            page.wait_for_url("**/tools/#image-studio")
            expect(layer).to_be_visible()
            expect(studio.locator("#shelf-dialog")).to_be_hidden()
        assert errors == []
    finally:
        page.context.close()


def test_image_handoff_can_be_retried_after_the_slide_layer_limit(browser, studio_origin):
    page = _page(browser, studio_origin)
    try:
        slide = _studio(page, studio_origin, "slide-studio")
        slide.evaluate("""async () => {
            await IronmatePhone.act('rect');
            const deck = IronmatePhone.deck;
            const layer = deck.slides[0].layers[0];
            deck.slides[0].layers = Array.from({length: 99}, (_, i) => ({...layer, id: 'fixture-' + i}));
            await IronmatePhone.act('open', new Blob([JSON.stringify(deck)], {type: 'application/json'}));
            await IronmatePhone.act('rect');
        }""")
        full = slide.evaluate("IronmatePhone.deck")
        selected = slide.evaluate("IronmatePhone.selected")
        assert len(full["slides"][0]["layers"]) == 100 and selected

        page.evaluate("location.hash = 'image-studio'")
        page.wait_for_function("() => document.querySelector('#image-studio iframe')?.dataset.ready")
        studio = page.locator("#image-studio iframe").element_handle().content_frame()
        _imported(page, studio, "画像", {"name": "fixture.png", "mimeType": "image/png", "buffer": _fixture_png()})
        expect(studio.locator("#layers button").filter(has_text="fixture.png")).to_have_count(1)
        original = studio.evaluate("IronmateStudio.scene")
        studio.locator('#studio-toolbar [data-act="import"]').click()
        studio.locator('#studio-candidates button:text-is("シェルフ")').click()
        link = studio.get_by_role("link", name="編集中の画像をスライド工房へ")
        link.click()
        expect(studio.get_by_role("status").filter(has_text="画像を渡せませんでした")).to_be_visible()
        expect(page).to_have_url(re.compile(r"/tools/#image-studio$"))
        expect(link).to_be_visible()
        assert slide.evaluate("IronmatePhone.deck") == full
        assert slide.evaluate("IronmatePhone.selected") == selected
        assert studio.evaluate("IronmateStudio.scene") == original

        slide.evaluate("IronmatePhone.act('delete')")
        available = slide.evaluate("IronmatePhone.deck")
        link.click()
        page.wait_for_url("**/tools/#slide-studio")
        assert slide.evaluate("IronmatePhone.deck.slides[0].layers.at(-1).kind") == "image"
        slide.locator('[data-act="undo"]').click()
        assert slide.evaluate("IronmatePhone.deck") == available
    finally:
        page.context.close()
