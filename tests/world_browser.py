"""Required Chromium contract for the 🌍 world (scripts/world.py): python tests/world_browser.py -v.

The emoji picker comes first, then the player walks by tap, arrow keys / WASD and the on-screen pad.
Solid props (desks, board, shelves) are never entered, whichever way the player moves.
Invoked explicitly by the browser CI job; missing Playwright/browser is an error. WEB_UI_CHROME may name a local Chrome.
``SharedBoardTests`` checks the opt-in shared board against a mocked GitHub API. ``CitiesTests`` sweeps the three cities (every spot, sign, tool, width and language); with WORLD_SHOTS=DIR it also keeps a
screenshot of each check, a manifest.json and one index.html in DIR (Pillow writes them as WebP).
"""
import copy
from html import escape
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import world as W  # noqa: E402  (scripts/world.py: the engine, the specs and the demo recorder)
import pysaiyanweboo as ui  # noqa: E402  (the pinned web UI: the tool page's chrome and add_part)

SPEC = W.example_data("school")
CLASSROOM = '.ui-floor[data-floor="classroom"]'
POS = f"() => {{ const s = document.querySelector('{CLASSROOM} .ui-player').style; return [parseFloat(s.getPropertyValue('--px')), parseFloat(s.getPropertyValue('--py'))]; }}"


class SchoolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.page_path = Path(cls.tmp.name) / "school.html"
        cls.page_path.write_text(W.world_document(SPEC), encoding="utf-8")
        cls.pw = sync_playwright().start()
        cls.browser = W.launch(cls.pw)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.tmp.cleanup()

    def open(self, width=1280, height=800, touch=False, js=True, path=None):
        context = self.browser.new_context(viewport={"width": width, "height": height}, has_touch=touch, is_mobile=touch,
                                           java_script_enabled=js)
        self.addCleanup(context.close)
        page = context.new_page()
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.goto((path or self.page_path).as_uri())
        return page

    def start(self, page, emoji="🐱"):
        page.click(f'[data-emoji="{emoji}"]')
        page.wait_for_function("() => !document.querySelector('.ui-world').hasAttribute('data-pick')")
        page.wait_for_timeout(400)                                          # the camera finishes its short glide

    def test_blackboard_allows_retry_with_explanation(self):
        page = self.open(width=390, height=844, touch=True)
        self.start(page)
        self.menu(page, "spots")
        page.click('.ui-world-spots a[href="#school-spot-classroom-board"]')
        board = page.get_by_role("region", name="黒板の練習問題")
        self.assertEqual(board.locator(":scope > details").count(), len(W.SCHOOL_LESSONS))
        topic = board.locator(":scope > details").first
        topic.locator(":scope > summary").click()
        question = topic.locator(":scope > details").first
        question.locator(":scope > summary").click()
        choices = question.locator(":scope > details")
        choices.nth(1).locator("summary").click()
        self.assertIn("もう一度", choices.nth(1).inner_text())
        choices.first.locator("summary").click()
        self.assertIn("正解。", choices.first.inner_text())
        self.assertEqual(self.errors, [])

    def cell(self, page):
        x, y = page.evaluate(POS)
        tile = int(page.get_attribute(CLASSROOM, "data-tile"))
        return int(x // tile), int(y // tile)

    def assert_free(self, page, point):
        wall = "() => document.querySelector('.ui-floor[data-floor=\"classroom\"]').dataset.blocked.split(',')"
        tile = int(page.get_attribute(CLASSROOM, "data-tile"))
        rows = page.evaluate(wall)
        self.assertEqual(rows[int(point[1] // tile)][int(point[0] // tile)], "0", f"inside a solid tile at {point}")

    def menu(self, page, name):
        """Open (or close) one of the side or header menus: ``spots`` ☰, ``more`` ⋯, ``favorites`` ⭐, ``settings`` ⚙️."""
        page.click(f'.ui-world-menu[data-menu="{name}"] summary')

    def settle(self, page, timeout=15000):
        """Wait until the player of the shown floor stands still at its target."""
        page.wait_for_function(W.SETTLED, timeout=timeout)

    def tap_map(self, page, x, y):
        box = page.evaluate(f"() => {{ const r = document.querySelector('{CLASSROOM}').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }}")
        page.mouse.click(box[0] + x * box[2] / 384, box[1] + y * box[3] / 512)

    def test_picker_comes_first_and_changes_every_player(self):
        page = self.open()
        self.assertTrue(page.is_visible(".ui-world-pick"))
        self.assertEqual(page.eval_on_selector(f"{CLASSROOM} .ui-player", "e => getComputedStyle(e).visibility"), "hidden")
        page.fill('.ui-world-pick-form input', "x" * 17)                    # too long for one label
        page.press('.ui-world-pick-form input', "Enter")
        self.assertTrue(page.is_visible(".ui-world-pick"))
        page.fill('.ui-world-pick-form input', "   ")
        page.press('.ui-world-pick-form input', "Enter")
        self.assertTrue(page.is_visible(".ui-world-pick"))
        page.fill('.ui-world-pick-form input', "ねこ🐱")                    # text, or emoji and text, is a character too
        page.press('.ui-world-pick-form input', "Enter")
        self.assertFalse(page.is_visible(".ui-world-pick"))
        self.assertEqual(page.eval_on_selector_all(".ui-player span", "els => els.map(e => e.textContent)"), ["ねこ🐱", "ねこ🐱"])
        self.menu(page, "settings")        # the ⚙️ menu (header) holds the picker button
        page.click("[data-pick-open]")
        page.fill('.ui-world-pick-form input', "🦖")
        page.press('.ui-world-pick-form input', "Enter")
        self.assertFalse(page.is_visible(".ui-world-pick"))
        self.assertEqual(page.eval_on_selector_all(".ui-player span", "els => els.map(e => e.textContent)"), ["🦖", "🦖"])
        self.menu(page, "settings")        # the ⚙️ menu (header) holds the picker button
        page.click("[data-pick-open]")
        self.assertTrue(page.is_visible(".ui-world-pick"))
        self.assertEqual(self.errors, [])

    def test_every_demo_scene_records_a_gif(self):
        """The README demos (tools/W.py) are real operations; a UI change that breaks one fails here, not in the next README."""
        with tempfile.TemporaryDirectory() as out:
            paths = W.record(out, browser=self.browser)
            self.assertEqual({p.name for p in paths}, {f"{sc.world}-{name}.gif" for name, sc in W.SCENES.items()})
            for path in paths:
                data = path.read_bytes()
                self.assertEqual(data[:6], b"GIF89a", path.name)
                self.assertGreater(len(data), 20_000, path.name)               # something moved
                self.assertLess(len(data), 3 * 1024 * 1024, path.name)         # and the README stays light

    def test_without_javascript_the_static_map_stays_and_nothing_interactive_shows(self):
        page = self.open(js=False)
        self.assertFalse(page.is_visible(".ui-world-pick"))
        self.assertFalse(page.is_visible(".ui-world-dpad"))
        self.assertTrue(page.is_visible(f"{CLASSROOM} .ui-spot"))

    def test_arrow_keys_wasd_and_walls(self):
        page = self.open()
        self.start(page)
        start = self.cell(page)
        page.keyboard.press("ArrowLeft")                                    # the shelf beside the door
        page.wait_for_timeout(300)
        self.assertEqual(self.cell(page), start)
        page.keyboard.press("ArrowDown")                                    # the edge of the floor
        page.wait_for_timeout(300)
        self.assertEqual(self.cell(page), start)
        page.keyboard.press("w")
        self.settle(page)
        self.assertEqual(self.cell(page), (start[0], start[1] - 1))
        page.keyboard.press("ArrowRight")
        self.settle(page)
        self.assertEqual(self.cell(page), (start[0] + 1, start[1] - 1))
        page.keyboard.press("a")
        self.settle(page)
        self.assertEqual(self.cell(page), (start[0], start[1] - 1))
        self.assertEqual(self.errors, [])

    def test_holding_a_key_walks_on_and_stops_at_a_desk(self):
        page = self.open()
        self.start(page)
        for _ in range(60):                                                 # straight up from the door, key repeating, into a desk row
            page.keyboard.down("ArrowUp")
            page.wait_for_timeout(40)
            self.assert_free(page, page.evaluate(POS))
        page.keyboard.up("ArrowUp")
        self.settle(page)
        self.assertEqual(self.cell(page), (5, 12))                          # the chair tile just below the first desk
        self.assert_free(page, page.evaluate(POS))

    def test_tap_walks_around_desks_and_never_cuts_through_them(self):
        page = self.open()
        self.start(page)
        self.tap_map(page, 80, 272)                                         # a chair behind two desk rows: a straight line crosses desks
        seen = []
        for _ in range(600):
            seen.append(page.evaluate(POS))
            if abs(seen[-1][0] - 80) < .01 and abs(seen[-1][1] - 272) < .01:
                break
            page.wait_for_timeout(30)
        for point in seen:
            self.assert_free(page, point)
        self.assertEqual(self.cell(page), (2, 8))
        self.assertGreater(len({tuple(p) for p in seen}), 20)

    def test_tap_on_a_desk_ends_on_the_nearest_free_tile(self):
        page = self.open()
        self.start(page)
        self.tap_map(page, 80, 176)                                         # on a desk (tile 2,5)
        self.settle(page)
        self.assert_free(page, page.evaluate(POS))
        x, y = page.evaluate(POS)
        self.assertLess(abs(x - 80) + abs(y - 176), 64)

    def test_on_screen_pad_on_a_phone(self):
        page = self.open(390, 844, touch=True)
        self.start(page)
        self.assertTrue(page.is_visible(".ui-world-dpad"))
        start = self.cell(page)
        page.dispatch_event('[data-step="0,-1"]', "pointerdown")             # press and hold the up button
        page.wait_for_timeout(700)
        page.dispatch_event('[data-step="0,-1"]', "pointerup")
        self.settle(page)
        self.assertLessEqual(self.cell(page)[1], start[1] - 2)
        self.assert_free(page, page.evaluate(POS))
        before = self.cell(page)
        page.dispatch_event('[data-step="-1,0"]', "pointerdown")
        page.dispatch_event('[data-step="-1,0"]', "pointerup")
        self.settle(page)
        self.assertNotEqual(self.cell(page), before)
        self.assertEqual(self.errors, [])

    def test_side_menus_footer_pulldown_and_arrows(self):
        """Header: the board. Side: ☰ places with arrows, ⋯ settings. Footer: the door-to-door pulldown. The page never grows taller."""
        page = self.open(390, 844, True)
        self.start(page)
        self.assertLessEqual(page.evaluate("document.documentElement.scrollHeight - innerHeight"), 0)
        self.assertFalse(page.is_visible(".ui-world-panel"))
        self.assertFalse(page.is_visible(".ui-world-foot .ui-world-bar"))              # the pulldown replaces the floor labels
        spots, more = '.ui-world-menu[data-menu="spots"]', '.ui-world-menu[data-menu="more"]'
        arrows = lambda floor: page.eval_on_selector_all(f'.ui-world-spots[data-floor="{floor}"] .ui-world-arrow', "els => els.map(e => e.textContent)")
        page.click(f"{spots} summary")
        self.assertTrue(page.is_visible('.ui-world-spots[data-floor="classroom"]'))
        self.assertFalse(page.is_visible('.ui-world-spots[data-floor="yard"]'))
        page.wait_for_function("() => document.querySelector('.ui-world-arrow').textContent !== '📍'")
        self.assertEqual(arrows("classroom"), ["⬆️", "⬆️", "⬆️"])                      # standing at the door: all three are ahead
        page.click(f"{more} summary")                                                  # one menu at a time
        page.wait_for_function(f"() => !document.querySelector('{spots}').open")      # (the toggle event is queued)
        page.keyboard.press("Escape")
        self.assertFalse(page.evaluate(f"document.querySelector('{more}').open"))
        page.click(f"{spots} summary")
        page.click('.ui-world-spots a[href="#school-spot-classroom-board"]')          # a place in the list: walk there and read it
        self.assertFalse(page.evaluate(f"document.querySelector('{spots}').open"))
        page.wait_for_function("() => { const p = document.querySelector('.ui-floor[data-floor=\"classroom\"] .ui-player'); const s = p.style;"
                               " return Math.abs(parseFloat(s.getPropertyValue('--py')) - +p.dataset.targetY) < .01 }")
        self.assertTrue(page.is_visible("#school-spot-classroom-board"))
        page.click(".ui-sheet-close:visible")
        page.click(f"{spots} summary")
        page.wait_for_function("() => document.querySelector('.ui-world-arrow').textContent === '📍'")   # arrived: within a tile
        player = page.evaluate(POS)                                                    # the page's arrows are the oracle's, point for point
        want = [W.world_direction(player, [x, y], 32) for x, y in ((192, 16), (192, 112), (192, 432))]
        self.assertEqual(arrows("classroom"), want)
        self.assertEqual(want[0], "📍")
        page.keyboard.press("Escape")
        page.select_option(".ui-world-goto", "yard")                                   # door to door: the footer pulldown
        page.click(f"{spots} summary")
        self.assertTrue(page.is_visible('.ui-world-spots[data-floor="yard"]'))
        self.assertFalse(page.is_visible('.ui-world-spots[data-floor="classroom"]'))
        page.click('.ui-world-spots a[href="#school-spot-flowers"]')
        self.assertEqual(page.input_value(".ui-world-goto"), "yard")
        self.assertTrue(page.is_visible("#school-spot-flowers"))
        self.assertEqual(self.errors, [])

    def test_header_home_favorites_settings_language_and_emoji_tools(self):
        """The header holds what is global: 🏠 ⭐ ⚙️ and the emoji tools; every button is an icon whose words are its aria-label."""
        page = self.open(390, 844, True)
        self.start(page)
        head = ".ui-world-head"
        menu = lambda name: f'{head} .ui-world-menu[data-menu="{name}"]'
        label = lambda sel: page.get_attribute(sel, "aria-label")
        self.assertEqual(self.errors, [])
        self.assertEqual([label(sel) for sel in (f"{head} .ui-world-home", f'{menu("favorites")} summary', f'{menu("settings")} summary')],
                         ["ホーム", "お気に入り", "全体設定"])
        # ⭐: star places on two floors (session only), jump to one from the panel, remove it
        self.menu(page, "spots")
        page.click('.ui-world-spots[data-floor="classroom"] li:nth-child(1) .ui-world-star')
        page.select_option(".ui-world-goto", "yard")
        page.click('.ui-world-spots[data-floor="yard"] li:nth-child(2) .ui-world-star')
        self.assertEqual(page.eval_on_selector_all(".ui-world-spots .ui-world-star[aria-pressed=true]", "els => els.map(e => e.textContent)"), ["★", "★"])
        page.keyboard.press("Escape")
        page.click(f'{menu("favorites")} summary')
        self.assertFalse(page.is_visible(f"{head} .ui-world-empty"))
        self.assertEqual(page.eval_on_selector_all(f"{head} .ui-world-favs a", "els => els.map(e => e.lastChild.textContent)"), ["黒板", "花だん"])
        page.click(f'{head} .ui-world-favs a[href="#school-spot-classroom-board"]')    # a favourite on the other floor: go there
        self.assertEqual(page.input_value(".ui-world-goto"), "classroom")
        self.assertTrue(page.is_visible("#school-spot-classroom-board"))
        self.assertFalse(page.evaluate(f"document.querySelector('{menu('favorites')}').open"))
        page.click(f'{menu("favorites")} summary')
        page.click(f'{head} .ui-world-favs li:nth-child(1) .ui-world-star')           # un-star from the panel
        self.assertEqual(page.eval_on_selector_all(f"{head} .ui-world-favs a", "els => els.length"), 1)
        # 🏠: first floor in view, sheet and menus closed, categories cleared
        page.select_option(".ui-world-goto", "yard")
        page.click(f"{head} .ui-world-home")                                              # 🏠 asks first: ✖️ stays where it is, 🏠 goes
        self.assertEqual(page.get_attribute(".ui-world-ask [role=dialog]", "aria-label"), "ホーム")
        page.click('.ui-world-ask button[data-t="close"]')
        self.assertEqual(page.input_value(".ui-world-goto"), "yard")
        page.click(f"{head} .ui-world-home")
        page.click('.ui-world-ask button[data-t="home"]')
        self.assertEqual(page.input_value(".ui-world-goto"), "classroom")
        self.assertFalse(page.is_visible(".ui-sheet-item[data-open]"))
        self.assertEqual(page.evaluate("location.hash"), "")
        # ⚙️: pause is an icon that flips, 🌐 turns every label into English and back
        page.click(f'{menu("settings")} summary')
        page.click(f"{head} .ui-world-pause")
        self.assertEqual(page.text_content(f"{head} .ui-world-pause"), "▶️")
        self.assertEqual(page.get_attribute(f"{head} .ui-world-pause", "aria-pressed"), "true")
        self.assertTrue(page.evaluate("document.querySelector('.ui-world').hasAttribute('data-motion-paused')"))
        page.click(f"{head} .ui-world-pause")
        self.assertEqual(page.text_content(f"{head} .ui-world-pause"), "⏸️")
        page.select_option(f"{head} [data-lang]", "fr")
        self.assertEqual([label(f"{head} .ui-world-home"), label(f'{menu("favorites")} summary'), label('.ui-world-dpad [data-step="0,-1"]'), label(".ui-world-goto")],
                         ["Accueil", "Favoris", "Haut", "Aller à l'étage"])
        self.assertEqual(page.get_attribute(f"{head} .ui-world-home", "title"), "Accueil")
        self.assertEqual(page.evaluate("document.querySelector('.ui-world').lang"), "fr")
        page.select_option(f"{head} [data-lang]", "ar")
        self.assertEqual(label(f"{head} .ui-world-home"), "الرئيسية")
        page.select_option(f"{head} [data-lang]", "en")
        self.assertEqual([label(f"{head} .ui-world-home"), label(f'{menu("favorites")} summary'), label('.ui-world-dpad [data-step="0,-1"]'), label(".ui-world-goto")],
                         ["Home", "Favorites", "Up", "Go to floor"])
        page.select_option(f"{head} [data-lang]", "ja")
        self.assertEqual(label(f"{head} .ui-world-home"), "ホーム")
        # the emoji tools of the school example: 🗺️ lists places with arrows, 🏫 shows a note; one menu at a time
        page.keyboard.press("Escape")
        page.click(f'{menu("tool")}:has(summary:text("🗺️")) summary')
        self.assertTrue(page.is_visible(f'{head} .ui-world-rows:not(.ui-world-favs) a[href="#school-spot-flowers"]'))
        page.wait_for_function("() => document.querySelector('.ui-world-head .ui-world-rows:not(.ui-world-favs) a .ui-world-arrow').textContent !== '📍'")
        self.assertEqual(page.eval_on_selector_all(f"{head} .ui-world-rows:not(.ui-world-favs) .ui-world-arrow", "els => els.map(e => e.textContent)"), ["⬆️", "🛗"])
        page.click(f'{menu("tool")}:has(summary:text("🏫")) summary')
        page.wait_for_function("() => document.querySelectorAll('.ui-world-menu[open]').length === 1")
        self.assertIn("教室と校庭", page.inner_text(f'{menu("tool")}[open]'))
        self.assertEqual(self.errors, [])

    def test_favorites_and_language_come_back_from_the_cache_and_nothing_else_does(self):
        posting = Path(self.tmp.name) / "posting.html"                                     # the same school with the board's message box on
        posting.write_text(W.world_document({**SPEC, "board": {**SPEC["board"], "post": True}}), encoding="utf-8")
        page = self.open(path=posting)
        head = ".ui-world-head"
        self.start(page, "🦊")
        self.menu(page, "spots")
        page.click('.ui-world-spots[data-floor="classroom"] li:nth-child(1) .ui-world-star')
        page.keyboard.press("Escape")
        self.menu(page, "settings")
        page.select_option(f"{head} [data-lang]", "de")
        page.keyboard.press("Escape")
        page.fill(".ui-board-post input", "hallo")                                          # a board message is only in the page
        page.press(".ui-board-post input", "Enter")
        self.assertIn("hallo", page.inner_text(".ui-board-run"))
        stored = page.evaluate("Object.fromEntries(Object.entries(localStorage))")
        self.assertEqual(list(stored), ["ui-world:school-map"])
        self.assertEqual(sorted(__import__("json").loads(stored["ui-world:school-map"])), ["fav", "lang"])
        self.assertNotIn("🦊", stored["ui-world:school-map"])
        self.assertNotIn("hallo", stored["ui-world:school-map"])
        page.reload()                                                                        # a visit later: starred place and language are back, the picker is asked again
        self.assertEqual(page.get_attribute(f"{head} .ui-world-home", "aria-label"), "Startseite")
        self.assertEqual(page.eval_on_selector_all(".ui-world-spots .ui-world-star[aria-pressed=true]", "els => els.length"), 1)
        self.assertEqual(page.input_value(f"{head} [data-lang]"), "de")
        self.assertTrue(page.is_visible(".ui-world-pick"))
        page.evaluate("localStorage.setItem('ui-world:school-map', '{\"fav\":[\"#nope\",7],\"lang\":\"xx\"}')")      # damaged or foreign cache is ignored
        page.reload()
        self.assertEqual(page.get_attribute(f"{head} .ui-world-home", "aria-label"), "ホーム")
        self.assertEqual(page.eval_on_selector_all(".ui-world-spots .ui-world-star[aria-pressed=true]", "els => els.length"), 0)
        page.evaluate("localStorage.setItem('ui-world:school-map', 'not json')")
        page.reload()
        self.assertEqual(self.errors, [])

    def test_bag_item_ids_survive_reload_and_removal_ignores_unknown_ids(self):
        path = Path(self.tmp.name) / "bag.html"
        path.write_text(W.world_document(W.example_data("overworld")), encoding="utf-8")
        page = self.open(path=path)
        self.start(page, "🧙")
        item = "overworld-spot-meadow-hirugaoka"
        key = "ui-world:overworld-map"
        self.menu(page, "spots")
        page.click(f'.ui-world-spots a[href="#{item}"]')
        page.click(f'#{item} .ui-world-take')
        self.assertEqual(page.get_attribute(f'#{item} .ui-world-take', "aria-pressed"), "true")
        self.assertEqual(page.evaluate("(key) => JSON.parse(localStorage.getItem(key)).bag", key), [item])
        page.reload()
        self.start(page, "🧙")
        self.menu(page, "bag")
        self.assertEqual(page.locator(".ui-world-bag li").count(), 1)
        page.click(".ui-world-bag-rm")
        self.assertEqual(page.locator(".ui-world-bag li").count(), 0)
        self.assertEqual(page.evaluate("(key) => JSON.parse(localStorage.getItem(key)).bag", key), [])
        page.reload()
        self.assertEqual(page.locator(".ui-world-bag li").count(), 0)
        page.evaluate("([key, item]) => localStorage.setItem(key, JSON.stringify({bag: [item, 'unknown', 7, item]}))", [key, item])
        page.reload()
        self.assertEqual(page.locator(".ui-world-bag li").count(), 1)
        page.evaluate("(key) => localStorage.setItem(key, JSON.stringify({bag: 'invalid'}))", key)
        page.reload()
        self.assertEqual(page.locator(".ui-world-bag li").count(), 0)
        self.assertEqual(self.errors, [])

    def test_overworld_lands_are_swapped_by_the_pulldown_and_walked_across(self):
        """Six lands from one line of JSON each: terrain is CSS (colour and an emoji per tile), the walk is the same grid."""
        path = Path(self.tmp.name) / "overworld.html"
        path.write_text(W.world_document(W.example_data("overworld")), encoding="utf-8")
        page = self.open(path=path)
        self.start(page, "🧙")
        self.assertEqual(page.eval_on_selector_all(".ui-world-goto option", "els => els.map(e => e.value)"),
                         ["meadow", "forest", "mountain", "desert", "coast", "castle", "real"])
        for land, kind in (("meadow", "water"), ("forest", "tree"), ("mountain", "mountain"), ("desert", "cactus"), ("coast", "water"), ("castle", "castle")):
            page.select_option(".ui-world-goto", land)
            page.wait_for_function(f"() => getComputedStyle(document.querySelector('.ui-floor[data-floor=\"{land}\"]')).display !== 'none'")
            style = page.eval_on_selector(f'.ui-floor[data-floor="{land}"] .ui-prop[data-kind="{kind}"]',
                                          "e => { const c = getComputedStyle(e); return [c.backgroundImage, c.backgroundSize, c.borderTopWidth] }")
            self.assertIn("data:image/svg+xml", style[0], land)
            self.assertEqual(style[2], "0px")
            self.assertTrue(page.is_visible(f'.ui-floor[data-floor="{land}"] .ui-player'))
        self.assertIn("contain", style[1])                                           # the castle is drawn once; the trees below once per tile
        page.select_option(".ui-world-goto", "forest")
        self.assertEqual(page.eval_on_selector('.ui-floor[data-floor="forest"] .ui-prop[data-kind="tree"]', "e => getComputedStyle(e).backgroundSize").split(",")[0], "32px 32px")
        spot = next(s for f in W.world_validate(W.example_data("overworld"))["floors"] if f["id"] == "forest" for s in f["spots"] if s["id"] == "forest-town")
        self.menu(page, "spots")
        page.click('.ui-world-spots[data-floor="forest"] a[href="#overworld-spot-forest-town"]')
        page.click("#overworld-spot-forest-town .ui-world-go")
        page.wait_for_function(W.SETTLED, timeout=20000)
        x, y = page.evaluate("() => { const s = document.querySelector('.ui-floor[data-floor=\"forest\"] .ui-player').style; return [parseFloat(s.getPropertyValue('--px')), parseFloat(s.getPropertyValue('--py'))]; }")
        self.assertAlmostEqual(x, spot["x"], delta=1)
        self.assertAlmostEqual(y, spot["y"], delta=1)
        self.assertEqual(self.errors, [])

    def test_the_cities_flip_a_sign_into_a_dragon_and_burn_one_fire_per_block(self):
        """Signs are a dot until touched (Reverse London's wooden nogard: dot, text, 🐉, dot; Tokyo's electronic boards: dot, text); Tokyo has electronic boards; Fake Paris draws its fires as tile emoji."""
        path = Path(self.tmp.name) / "cities.html"
        path.write_text(W.world_document(W.example_data("cities")), encoding="utf-8")
        page = self.open(path=path)
        self.start(page, "🧳")
        self.assertEqual(page.eval_on_selector_all(".ui-world-goto option", "els => els.map(e => e.value)"), ["tokyo", "london", "paris", "osaka", "nagoya"])
        page.select_option(".ui-world-goto", "london")
        sign = '.ui-floor[data-floor="london"] .ui-spot[data-flip]'
        face = lambda: page.eval_on_selector(sign, "e => [e.textContent, e.dataset.show || '', getComputedStyle(e).fontSize]")    # noqa: E731
        self.assertEqual(page.get_attribute(sign, "data-sign"), "wood")
        style = page.eval_on_selector(sign, "e => { const c = getComputedStyle(e), b = getComputedStyle(e, '::before'); return [c.backgroundColor, b.content] }")
        self.assertEqual(style, ["rgb(139, 90, 43)", '"●"'])                                          # a wooden board: a bold dot until it is touched
        self.assertEqual(face(), ["nogard", "", "0px"])
        page.eval_on_selector(sign, "e => e.click()")
        self.assertEqual(face(), ["nogard", "label", "11.2px"])                                      # the board shows its text
        page.eval_on_selector(sign, "e => e.click()")
        self.assertEqual(face(), ["🐉", "flip", "11.2px"])                                           # then its second face
        page.eval_on_selector(sign, "e => e.click()")
        self.assertEqual(face(), ["nogard", "", "0px"])                                              # and the dot again
        led = '.ui-floor[data-floor="tokyo"] .ui-spot[data-sign=led]'
        self.assertEqual(page.eval_on_selector(led, "e => [getComputedStyle(e).color, getComputedStyle(e).fontSize]"), ["rgb(255, 176, 0)", "0px"])
        page.eval_on_selector(led, "e => e.click()")
        self.assertEqual(page.eval_on_selector(led, "e => getComputedStyle(e).fontSize"), "11.2px")
        page.eval_on_selector(led, "e => e.click()")
        self.assertEqual(page.eval_on_selector(led, "e => getComputedStyle(e).fontSize"), "0px")    # two faces only: dot and text
        page.select_option(".ui-world-goto", "paris")
        page.wait_for_function("() => getComputedStyle(document.querySelector('.ui-floor[data-floor=\"paris\"]')).display !== 'none'")
        fires = page.eval_on_selector_all('.ui-floor[data-floor="paris"] .ui-prop[data-kind="fire"]', "els => els.map(e => getComputedStyle(e).backgroundImage)")
        self.assertGreaterEqual(len(fires), 20)
        self.assertTrue(all("data:image/svg+xml" in image for image in fires))
        self.assertEqual(self.errors, [])

    def test_real_floor_shows_a_chosen_photo_or_the_camera_only_in_the_page(self):
        """🖼️📷 on the real floor: ask() offers camera or photo; the picture sits behind the props, is released by 🧹 or by leaving (camera), and is never stored or sent."""
        import io
        from PIL import Image
        path = Path(self.tmp.name) / "overworld.html"
        path.write_text(W.world_document(W.example_data("overworld")), encoding="utf-8")
        photo = Path(self.tmp.name) / "room.png"
        picture = io.BytesIO()
        Image.new("RGB", (64, 48), (200, 80, 40)).save(picture, format="PNG")
        photo.write_bytes(picture.getvalue())
        browser = W.launch(self.pw, extra=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
        self.addCleanup(browser.close)
        context = browser.new_context(viewport={"width": 1280, "height": 800}, permissions=["camera"])
        page = context.new_page()
        errors, requests = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("request", lambda r: requests.append(r.url))
        page.goto(path.as_uri())
        page.click('[data-emoji="🧙"]')
        page.wait_for_function("() => !document.querySelector('.ui-world').hasAttribute('data-pick')")
        real = '.ui-floor[data-floor="real"]'
        floor_shown = lambda name: page.wait_for_function(f"() => getComputedStyle(document.querySelector('.ui-floor[data-floor=\"{name}\"]')).display !== 'none'")
        hint = lambda: page.evaluate(f"() => getComputedStyle(document.querySelector('{real}'), '::after').content")
        self.menu(page, "more")
        self.assertFalse(page.is_visible("[data-real]"))                           # a land has no backdrop
        self.menu(page, "more")
        page.select_option(".ui-world-goto", "real")
        floor_shown("real")
        self.assertIn("🖼️📷", hint())                                              # until one is chosen, the floor says what it can show
        self.menu(page, "more")
        page.click("[data-real]")
        self.assertEqual(page.eval_on_selector_all(".ui-world-ask button", "els => els.map(e => [e.textContent, e.getAttribute('aria-label')])"),
                         [["📷", "カメラ"], ["🖼️", "写真をえらぶ"], ["✖️", "閉じる"]])           # nothing to clear yet
        self.assertEqual(page.get_attribute(".ui-world-ask [role=dialog]", "aria-label"), "写真かカメラをうしろに映す")
        page.keyboard.press("Escape")
        self.assertEqual(page.locator(".ui-world-ask").count(), 0)
        self.assertEqual(page.locator(f"{real} .ui-real").count(), 0)
        # a photo
        self.menu(page, "more")
        page.click("[data-real]")
        with page.expect_file_chooser() as chooser:
            page.click('.ui-world-ask button[data-t="photo"]')
        chooser.value.set_files(str(photo))
        page.wait_for_function(f"() => document.querySelector('{real} img.ui-real')?.complete")
        info = page.evaluate(f"() => {{ const i = document.querySelector('{real} img.ui-real'), f = document.querySelector('{real}'); "
                             "return [i.src.slice(0, 5), i.naturalWidth, i.offsetWidth, i.offsetHeight, getComputedStyle(i).pointerEvents, f.firstElementChild === i, f.hasAttribute('data-backdrop')]; }")
        self.assertEqual(info, ["blob:", 64, 384, 384, "none", True, True])      # behind the props, the size of the floor, taps pass through
        self.assertEqual(hint(), "none")
        self.assertTrue(page.is_visible(f"{real} .ui-player") and page.is_visible(f"{real} .ui-spot"))
        # 🧹 lets it go
        self.menu(page, "more")
        page.click("[data-real]")
        self.assertEqual(page.eval_on_selector_all(".ui-world-ask button", "els => els.map(e => e.textContent)"), ["📷", "🖼️", "🧹", "✖️"])
        page.click('.ui-world-ask button[data-t="clear"]')
        self.assertEqual(page.locator(f"{real} .ui-real").count(), 0)
        self.assertIn("🖼️📷", hint())
        # the camera: a stream on a <video>, stopped on leaving the floor
        self.menu(page, "more")
        page.click("[data-real]")
        page.click('.ui-world-ask button[data-t="camera"]')
        page.wait_for_function(f"() => {{ const v = document.querySelector('{real} video.ui-real'); return v && v.videoWidth > 0 && v.srcObject; }}")
        page.evaluate(f"() => {{ window.__stream = document.querySelector('{real} video.ui-real').srcObject; }}")
        self.assertTrue(page.evaluate("() => window.__stream.getTracks().every(t => t.readyState === 'live')"))
        page.select_option(".ui-world-goto", "meadow")
        floor_shown("meadow")
        self.assertEqual(page.locator("video").count(), 0)
        self.assertTrue(page.evaluate("() => window.__stream.getTracks().every(t => t.readyState === 'ended')"))
        # nothing is stored or sent: no request but the page itself, and the cache holds no picture
        self.assertTrue(all(u.startswith(("file:", "blob:", "data:")) for u in requests), requests)
        self.assertNotIn("blob:", page.evaluate("() => JSON.stringify({...localStorage})"))
        # the language of the words in the dialog follows 🌐; ask() is callable from the page that embeds the world
        self.menu(page, "settings")
        page.select_option("[data-lang]", "en")
        self.menu(page, "settings")
        page.evaluate("() => { document.querySelector('.ui-world').ask('❓', [{glyph: '✅', t: 'ok', value: 'yes'}], 'floor').then(v => { window.__answer = v; }); }")
        self.assertEqual(page.eval_on_selector_all(".ui-world-ask button", "els => els.map(e => e.getAttribute('aria-label'))"), ["Use this", "Close"])
        page.click('.ui-world-ask button[data-t="ok"]')
        page.wait_for_function("() => window.__answer === 'yes'")
        page.evaluate("() => { document.querySelector('.ui-world').ask('❓', []).then(v => { window.__answer = v; }); }")
        page.click(".ui-world-ask", position={"x": 4, "y": 4})                           # a tap outside the card cancels
        page.wait_for_function("() => window.__answer === null")
        self.assertEqual(errors, [])

    def test_camera_that_cannot_open_says_so_and_keeps_the_floor_plain(self):
        path = Path(self.tmp.name) / "overworld.html"
        path.write_text(W.world_document(W.example_data("overworld")), encoding="utf-8")
        page = self.open(path=path)
        self.start(page, "🧙")
        page.evaluate("() => { Object.defineProperty(navigator, 'mediaDevices', {value: {getUserMedia: () => Promise.reject(new DOMException('no', 'NotAllowedError'))}}); }")
        page.select_option(".ui-world-goto", "real")
        page.wait_for_function("() => getComputedStyle(document.querySelector('.ui-floor[data-floor=\"real\"]')).display !== 'none'")
        self.menu(page, "more")
        page.click("[data-real]")
        page.click('.ui-world-ask button[data-t="camera"]')
        page.wait_for_selector('.ui-world-ask [data-t="unavailable"]')
        self.assertIn("つかえません", page.get_attribute('.ui-world-ask [data-t="unavailable"]', "aria-label"))
        self.assertEqual(page.locator("video, img.ui-real").count(), 0)
        page.click('.ui-world-ask button[data-t="close"]')
        self.assertEqual(page.locator(".ui-world-ask").count(), 0)
        self.assertEqual(self.errors, [])

    def test_without_javascript_the_footer_keeps_plain_floor_labels(self):
        page = self.open(js=False)
        self.assertTrue(page.is_visible(".ui-world-foot .ui-world-bar"))
        self.assertFalse(page.is_visible(".ui-world-goto"))
        self.assertFalse(page.is_visible('.ui-world-menu[data-menu="more"]'))           # needs JS
        self.menu(page, "spots")
        self.assertTrue(page.is_visible('.ui-world-spots[data-floor="classroom"]'))
        page.click('label[for="school-floor-yard"]')
        self.assertTrue(page.is_visible('.ui-world-spots[data-floor="yard"]'))
        self.assertFalse(page.is_visible('.ui-world-spots[data-floor="classroom"]'))

    def test_open_floor_has_no_grid_pad_and_keeps_free_walking(self):
        page = self.open()
        self.start(page)
        page.select_option(".ui-world-goto", "yard")                        # the footer pulldown moves to the other floor
        page.wait_for_selector(".ui-world-dpad", state="hidden")
        page.keyboard.press("ArrowUp")                                      # no grid here: the key is left to the page
        self.assertEqual(self.errors, [])

    def test_layout_fits_at_phone_and_desktop_widths(self):
        for width, height, touch in ((320, 640, True), (390, 844, True), (768, 1024, False), (1280, 800, False)):
            page = self.open(width, height, touch)
            self.start(page)
            self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth - innerWidth"), 0, f"overflow at {width}")
            self.assertTrue(page.is_visible(".ui-world-dpad"), f"pad at {width}")
            box = page.evaluate(f"() => {{ const r = document.querySelector('{CLASSROOM} .ui-player').getBoundingClientRect(); return [r.left, r.right]; }}")
            self.assertGreaterEqual(box[0], 0)
            self.assertLessEqual(box[1], width)


class SharedBoardTests(unittest.TestCase):
    """The opt-in shared board at phone and desktop widths with every GitHub API answer mocked (nothing is posted): no fetch until asked, one anonymous
    GET per cooldown, comments as text, the posting link, local notes, a rate limit that keeps the last lines, and nothing kept across a reload."""

    @classmethod
    def setUpClass(cls):
        spec = W.example_data("world")
        spec["board"]["shared_issue"] = "myon-bioinformatics/PySaiyanWeBoo/123"
        cls.html = W.world_document(spec)
        cls.pw = sync_playwright().start()
        cls.browser = W.launch(cls.pw)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def test_refresh_cooldown_text_only_comments_and_rate_limit(self):
        for width in (320, 390, 1280):
            with self.subTest(width=width):
                page = self.browser.new_page(viewport={"width": width, "height": 844})
                self.addCleanup(page.close)
                calls, errors, answer = [], [], {"fail": False}
                page.on("pageerror", lambda error: errors.append(str(error)))

                def github(route):
                    calls.append((route.request.method, route.request.headers.get("authorization")))
                    if answer["fail"]:
                        return route.fulfill(status=429, json={"message": "rate limited"}, headers={"retry-after": "300"})
                    return route.fulfill(json=[{"body": "<img src=x onerror=alert(1)> 駅で集合", "user": {"login": "alice"}, "created_at": "2026-11-03T00:00:00Z"}])

                page.route("https://api.github.com/**", github)
                page.route("http://world.test/", lambda route: route.fulfill(content_type="text/html", body=self.html))
                page.goto("http://world.test/")
                self.assertEqual(calls, [])
                comments, refresh = page.locator("[data-shared-comments]"), page.locator("[data-shared-refresh]")
                page.locator(".ui-board-shared summary").click()
                refresh.click()
                page.locator("[data-shared-comments] li").first.wait_for()
                self.assertRegex(comments.inner_text(), r"alice.*駅で集合")
                self.assertEqual(page.locator("[data-shared-comments] img").count(), 0)
                refresh.click()
                self.assertEqual(calls, [("GET", None)])
                link = page.locator(".ui-board-shared a")
                self.assertRegex(link.get_attribute("href"), r"issues/123#new_comment_field$")
                self.assertEqual(link.get_attribute("target"), "_blank")
                page.locator(".ui-board-post input").fill("端末だけ")
                page.locator(".ui-board-post button").click()
                self.assertEqual(page.locator(".ui-board-note").count(), 2)
                self.assertIn("駅で集合", comments.inner_text())
                page.clock.install()
                page.clock.fast_forward(121000)
                answer["fail"] = True
                refresh.click()
                page.wait_for_function("() => document.querySelector('[data-shared-status]').textContent.includes('取得できません')")
                self.assertIn("駅で集合", comments.inner_text())
                refresh.click()
                self.assertEqual(calls, [("GET", None)] * 2)
                self.assertEqual(page.evaluate("() => localStorage.length"), 0)
                page.reload()
                self.assertEqual(page.locator(".ui-board-note").count(), 0)
                self.assertEqual(len(calls), 2)
                self.assertEqual(errors, [])


# --- The three cities: every spot, sign, tool, width and language, with an optional screenshot per check ---
CITIES = W.world_validate(W.example_data("cities"))
FAST = copy.deepcopy(CITIES)                     # the same floors, grid and routes; the player walks at the top speed so a sweep takes minutes
for _floor in FAST["floors"]:
    _floor["player"]["speed"] = 480
SIZES = {"phone": (390, 844, True), "desktop": (1280, 800, False)}
WIDTHS = {"phone-320": (320, 640, True), "phone": (390, 844, True), "phone-landscape": (844, 390, True),
          "tablet": (768, 1024, False), "desktop": (1280, 800, False), "wide": (1920, 1080, False)}
SHOTS = os.environ.get("WORLD_SHOTS")           # a folder: each check also keeps a screenshot, listed in manifest.json and index.html
CITY_FLOOR = '.ui-floor[data-floor="{}"]'
CITY_POS = "fl => { const s = document.querySelector(`.ui-floor[data-floor=\"${fl}\"] .ui-player`).style; return [parseFloat(s.getPropertyValue('--px')), parseFloat(s.getPropertyValue('--py'))]; }"
CITY_WALK = ("fl => new Promise(done => { const p = document.querySelector(`.ui-floor[data-floor=\"${fl}\"] .ui-player`), seen = [], t0 = performance.now();"
             " const step = () => { const s = p.style, x = parseFloat(s.getPropertyValue('--px')), y = parseFloat(s.getPropertyValue('--py')); seen.push([x, y]);"
             " if ((Math.abs(x - +p.dataset.targetX) < .01 && Math.abs(y - +p.dataset.targetY) < .01) || performance.now() - t0 > 30000) done(seen);"
             " else requestAnimationFrame(step) }; requestAnimationFrame(step) })")      # every frame of the walk, until the player stands at its target
CITY_TOP = ("sel => { const a = document.querySelector(sel), r = a.getBoundingClientRect(), x = r.x + r.width / 2, y = r.y + r.height / 2,"
            " e = document.elementFromPoint(x, y); return {self: !!e && (e === a || a.contains(e)), sheet: !!e?.closest('.ui-sheet'),"
            " what: (e?.closest('.ui-spot,.ui-sheet-item,.ui-world-dpad,.ui-world-side,.ui-player')?.textContent || e?.className || '').trim().slice(0, 24), x, y} }")


def city_cell(point, tile):
    return int(point[0] // tile), int(point[1] // tile)


def write_city_gallery(out, records, meta):
    """manifest.json and its one-page index.html (``city_gallery``) beside the shots/ written by the sweep.
    A run of some tests only (``CitiesTests.test_every_sign_shows_its_faces``) replaces its own records in an existing manifest and keeps the rest."""
    manifest = out / "manifest.json"
    if manifest.is_file():
        fresh = {(r["viewport"], r["floor"], r["kind"], r["id"]) for r in records}
        kept = [r for r in json.loads(manifest.read_text(encoding="utf-8")).get("records", []) if (r["viewport"], r["floor"], r["kind"], r["id"]) not in fresh]
        records = kept + records
    kinds = ["overview", "sheet", "map", "sign", "layer", "tool", "category", "favorite", "key", "fire", "width", "lang", "nojs", "pick"]
    records = sorted(records, key=lambda r: (kinds.index(r["kind"]) if r["kind"] in kinds else len(kinds), r["viewport"], r["floor"], r["order"]))
    ok = sum(1 for r in records if not r["notes"])
    (out / "manifest.json").write_text(json.dumps({"schema": "web-ui-cities-evidence/1", **meta, "shots": len(records), "clean": ok,
                                                   "noted": len(records) - ok, "records": records}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    write_city_gallery_page(out)


def city_gallery(manifest) -> str:
    """The review page of a cities sweep (``web-ui-cities-evidence/1``, written here with WORLD_SHOTS): one figure per record,
    no JavaScript, opens from file://. The page is not committed."""
    records, meta = manifest["records"], manifest
    ok = sum(1 for r in records if not r["notes"])
    sections = {}
    for r in records:
        sections.setdefault((r["kind"], r["viewport"], r["floor"]), []).append(r)
    css = ("body{font-family:Meiryo,'Hiragino Sans','Noto Sans JP',sans-serif;margin:16px;background:#0c1018;color:#e6edf3}"
           "a{color:#8fd694}h2{margin:32px 0 8px;font-size:16px}nav a{margin-right:8px;white-space:nowrap}"
           ".g{display:grid;gap:8px;grid-template-columns:repeat(auto-fill,minmax(var(--w),1fr))}.phone{--w:192px}.desktop,.wide,.tablet{--w:320px}"
           "figure{margin:0;padding:8px;border:1px solid #30363d;border-radius:8px}figure.n{border-color:#d29922}img{width:100%;height:auto;display:block}"
           "figcaption{font-size:12px;line-height:16px;margin-top:8px}.note{color:#d29922}")
    names = {"overview": "🗺️", "sheet": "📄", "map": "📍", "sign": "🪧", "layer": "🏷️", "tool": "🧰", "width": "📐", "lang": "🌐", "nojs": "🚫", "pick": "🙂", "favorite": "⭐", "fire": "🔥", "key": "⌨️", "category": "🏷️"}
    parts = [f"<!doctype html><html lang=ja><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
             f"<title>🗼🎡🥖 cities evidence</title><style>{css}</style><h1>🗼🎡🥖 cities evidence</h1>"
             f"<p>✅ {ok} · ⚠️ {len(records) - ok} · 📸 {len(records)} · {escape(meta['browser'])} · {escape(meta['date'])} · {escape(meta['commit'][:12])}</p><nav>"]
    if meta.get("revalidation"):
        count = len(meta["revalidation"]["files"])
        parts.append(f"<p>Partial revalidation: {count} records were recaptured; the other {len(records) - count} retain their original capture metadata. "
                     "<a href='revalidation.md'>Revalidation details</a></p>")
    keys = list(sections)
    parts += [f"<a href='#s{i}'>{names.get(k[0], k[0])} {escape(k[1])} {escape(k[2])} ({len(sections[k])})</a>" for i, k in enumerate(keys)]
    parts.append("</nav>")
    for i, key in enumerate(keys):
        kind, viewport, floor = key
        parts.append(f"<h2 id='s{i}'>{names.get(kind, kind)} {escape(kind)} · {escape(viewport)} · {escape(floor)}</h2><div class='g {escape(viewport.split('-')[0])}'>")
        for r in sections[key]:
            notes = "".join(f"<br><span class=note>{escape(n)}</span>" for n in r["notes"])
            parts.append(f"<figure class='{'n' if r['notes'] else ''}'><a href='shots/{escape(r['file'])}'><img src='shots/{escape(r['file'])}' loading=lazy "
                         f"alt='{escape(r['label'], quote=True)}'></a><figcaption>{'⚠️' if r['notes'] else '✅'} {escape(r['label'])}{notes}</figcaption></figure>")
        parts.append("</div>")
    return "".join(parts) + "\n"


def write_city_gallery_page(folder) -> Path:
    """Write ``folder/index.html`` from ``folder/manifest.json`` (``city_gallery``); returns the page's path."""
    page = Path(folder) / "index.html"
    page.write_text(city_gallery(json.loads((Path(folder) / "manifest.json").read_text(encoding="utf-8"))), encoding="utf-8")
    return page


class CitiesTests(unittest.TestCase):
    """Parallel Tokyo, Reverse London and Fake Paris end to end: every spot from the ☰ list (walked to, never through water, the sheet tells its text,
    the arrows agree with Python's world_direction and the target with world_route_points), every sign's faces, the tools, keys, categories,
    favourites, widths, languages and the page without JavaScript. What works but looks wrong (a sheet over the destination, a label over a label)
    is kept as a note next to the screenshot instead of failing."""
    records = []

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.page_path, cls.fast_path = Path(cls.tmp.name) / "cities.html", Path(cls.tmp.name) / "fast.html"
        cls.page_path.write_text(W.world_document(CITIES), encoding="utf-8")
        cls.fast_path.write_text(W.world_document(FAST), encoding="utf-8")
        cls.pw = sync_playwright().start()
        cls.browser = W.launch(cls.pw)
        cls.out = Path(SHOTS) if SHOTS else None
        if cls.out:
            (cls.out / "shots").mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        version = cls.browser.version
        cls.browser.close()
        cls.pw.stop()
        cls.tmp.cleanup()
        if cls.out and cls.records:
            from importlib.metadata import version as package_version
            commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() or "unknown"
            write_city_gallery(cls.out, sorted(cls.records, key=lambda r: r["order"]), {
                "browser": f"Chromium {version} (Playwright {package_version('playwright')})", "commit": commit,
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "player_speed": "480 (FAST) for the sweeps; 96 for keys, pad and reduced motion"})

    def open(self, size, path=None, js=True, reduced=False):
        width, height, touch = WIDTHS[size]
        context = self.browser.new_context(viewport={"width": width, "height": height}, has_touch=touch, is_mobile=touch, java_script_enabled=js,
                                           reduced_motion="reduce" if reduced else "no-preference")
        self.addCleanup(context.close)
        page = context.new_page()
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and self.errors.append(m.text))
        page.goto((path or self.fast_path).as_uri())
        page.size, page.touch = size, touch
        return page

    def start(self, page, emoji="🧳"):
        page.click(f'[data-emoji="{emoji}"]')
        page.wait_for_function(W.PICKED)
        page.wait_for_timeout(300)

    def show(self, page, floor):
        page.select_option(".ui-world-goto", floor)
        page.wait_for_function(f"() => getComputedStyle(document.querySelector('{CITY_FLOOR.format(floor)}')).display !== 'none'")
        page.wait_for_timeout(150)

    def menu(self, page, name):
        page.click(f'.ui-world-menu[data-menu="{name}"] > summary')

    def tap(self, page, x, y):
        """A finger (phone) or the mouse (desktop) on a point of the map."""
        if page.touch:
            page.touchscreen.tap(x, y)
        else:
            page.mouse.click(x, y)

    def press(self, page, selector):
        """A finger or the mouse on an element (Playwright's own tap/click: it scrolls the element into view and refuses one that is covered).
        Returns the notes: empty when the real press worked, one line when it was covered and a script click stood in."""
        target = page.locator(selector)
        try:
            (target.tap if page.touch else target.click)(timeout=3000)
            return []
        except PlaywrightTimeoutError:
            top = page.evaluate(CITY_TOP, selector)
            target.evaluate("e => e.click()")
            return [f"⚠️ 目印の上に「{top['what']}」が重なり押せない（スクリプトで代用）"]

    def shot(self, page, kind, floor, ident, label, notes=()):
        """One screenshot of the world (the page around it is cut off), kept only with WORLD_SHOTS."""
        if not self.out:
            return
        from PIL import Image
        import io
        box = page.eval_on_selector(".ui-world", "e => { const r = e.getBoundingClientRect(); return {x: r.x, y: r.y, width: r.width, height: Math.min(r.height, innerHeight - r.y)} }")
        png = page.screenshot(type="png", clip={k: round(v) for k, v in box.items()})
        name = f"{page.size}-{floor}-{kind}-{ident}".replace("/", "_") + ".webp"
        Image.open(io.BytesIO(png)).convert("RGB").save(self.out / "shots" / name, "WEBP", quality=80, method=6)
        type(self).records.append({"order": len(self.records), "file": name, "viewport": page.size, "floor": floor, "kind": kind, "id": ident,
                                   "label": label, "notes": list(notes)})

    def still(self, page):
        """Wait for the camera: after a walk with the camera following, or a press (focusSpot), it glides for .24 s."""
        city_still = ("() => new Promise(done => { const cam = document.querySelector('.ui-world-cam'); let last = getComputedStyle(cam).transform, same = 0, n = 0;"
                      " const step = () => { const now = getComputedStyle(cam).transform; same = now === last ? same + 1 : 0; last = now;"
                      " if (same >= 3 || ++n > 120) done(same >= 3); else requestAnimationFrame(step) }; requestAnimationFrame(step) })")   # the camera's glide (.24s) has ended
        self.assertTrue(page.evaluate(city_still), "the camera kept moving")

    def arrows(self, page, floor):
        return page.eval_on_selector_all(f'.ui-world-spots[data-floor="{floor}"] a', "els => els.map(a => [a.getAttribute('href'), a.querySelector('.ui-world-arrow').textContent])")

    def sweep(self, size):
        """Every spot of every city, one after another, from the ☰ list; then a real tap on its marker."""
        city_target = "fl => { const p = document.querySelector(`.ui-floor[data-floor=\"${fl}\"] .ui-player`); return [+p.dataset.targetX, +p.dataset.targetY]; }"
        page = self.open(size)
        self.start(page)
        for f in CITIES["floors"]:
            fl, tile = f["id"], f["tile"]
            blocked = W.world_blocked(f["width"], f["height"], tile, f["props"])
            self.show(page, fl)
            self.shot(page, "overview", fl, "fit", f["label"])
            for s in f["spots"]:
                with self.subTest(size=size, spot=s["id"]):
                    href, sheet = f"#cities-spot-{s['id']}", f"#cities-spot-{s['id']}"
                    marker = f'{CITY_FLOOR.format(fl)} .ui-spot[href="{href}"]'
                    here = page.evaluate(CITY_POS, fl)
                    self.menu(page, "spots")
                    want = [[f"#cities-spot-{t['id']}", W.world_direction(here, [t["x"], t["y"]], tile)] for t in f["spots"]]
                    try:
                        page.wait_for_function("([fl, want]) => JSON.stringify([...document.querySelectorAll(`.ui-world-spots[data-floor=\"${fl}\"] a`)].map(a => "
                                               "[a.getAttribute('href'), a.querySelector('.ui-world-arrow').textContent])) === JSON.stringify(want)", arg=[fl, want], timeout=3000)
                    except Exception:
                        pass
                    self.assertEqual(self.arrows(page, fl), want)                                   # the ☰ arrows from where the player stands
                    goal = W.world_route_points(blocked, tile, here, [s["x"], s["y"]])[-1]
                    page.click(f'.ui-world-spots[data-floor="{fl}"] a[href="{href}"]')
                    seen = page.evaluate(CITY_WALK, fl)
                    self.assertEqual([p for p in seen if blocked[city_cell(p, tile)[1]][city_cell(p, tile)[0]] == "1"], [], "walked into water")
                    target = page.evaluate(city_target, fl)
                    self.assertAlmostEqual(target[0], goal[0], delta=.01)
                    self.assertAlmostEqual(target[1], goal[1], delta=.01)
                    end = page.evaluate(CITY_POS, fl)
                    self.assertLess(abs(end[0] - target[0]) + abs(end[1] - target[1]), .05)
                    self.still(page)
                    self.assertEqual(page.evaluate("location.hash"), sheet)
                    self.assertTrue(page.is_visible(sheet))
                    self.assertEqual([page.text_content(f"{sheet} h3"), page.text_content(f"{sheet} p")], [s["label"], s["body"]])
                    self.assertEqual(page.input_value(".ui-world-goto"), fl)
                    self.assertGreaterEqual(float(page.evaluate("document.querySelector('.ui-world-cam').style.getPropertyValue('--z')")), 2 - 1e-9)
                    notes = []
                    if page.evaluate(CITY_TOP, marker)["sheet"]:
                        notes.append("⚠️ シートが行き先の目印を隠す")
                    if page.evaluate(CITY_TOP, f"{CITY_FLOOR.format(fl)} .ui-player")["sheet"]:
                        notes.append("⚠️ シートが🧳を隠す")
                    self.shot(page, "sheet", fl, s["id"], s["label"], notes)
                    page.click(".ui-sheet-close:visible")
                    notes = []
                    if not s.get("sign"):                                                           # signs are pressed by test_every_sign_shows_its_faces
                        notes = self.press(page, marker)
                        page.wait_for_selector(sheet, state="visible", timeout=3000)
                        page.click(".ui-sheet-close:visible")
                        self.still(page)
                    self.shot(page, "map", fl, s["id"], s["label"], notes)
        self.assertEqual(self.errors, [])

    def test_every_spot_on_a_phone(self):
        self.sweep("phone")

    def test_every_spot_on_a_desktop(self):
        self.sweep("desktop")

    def test_every_sign_shows_its_faces(self):
        """A sign is a dot until touched; then its text; then its second face if it has one (nogard 🐉); then the dot again."""
        for size in SIZES:
            page = self.open(size)
            self.start(page)
            for f in CITIES["floors"]:
                self.show(page, f["id"])
                for s in (s for s in f["spots"] if s.get("sign")):
                    with self.subTest(size=size, sign=s["id"]):
                        marker = f'{CITY_FLOOR.format(f["id"])} .ui-spot[href="#cities-spot-{s["id"]}"]'
                        self.menu(page, "spots")
                        page.click(f'.ui-world-spots a[href="#cities-spot-{s["id"]}"]')                 # the list walks there without turning the board
                        page.evaluate(CITY_WALK, f["id"])
                        page.click(".ui-sheet-close:visible")
                        self.still(page)
                        faces = ["", "label", "flip", ""] if s.get("flip") else ["", "label", ""]
                        for i, face in enumerate(faces):
                            notes = []
                            if i:
                                notes = self.press(page, marker)
                                page.wait_for_selector(f"#cities-spot-{s['id']}", state="visible", timeout=3000)
                                page.click(".ui-sheet-close:visible")
                                self.still(page)
                            state = page.eval_on_selector(marker, "e => { const c = getComputedStyle(e); return [e.textContent, e.dataset.show || '', c.fontSize, c.color,"
                                                          " c.backgroundColor, getComputedStyle(e, '::before').content] }")
                            self.assertEqual(state[:2], [s["flip"] if face == "flip" else s["label"], face])
                            self.assertEqual(state[2] == "0px", face == "")                              # the dot hides the text
                            self.assertIn("●", state[5])
                            self.assertEqual(state[4], {"led": "rgb(17, 17, 17)", "wood": "rgb(139, 90, 43)"}[s["sign"]])
                            if s["sign"] == "led":
                                self.assertEqual(state[3], "rgb(255, 176, 0)")
                            self.shot(page, "sign", f["id"], f"{s['id']}-{i}-{face or 'dot'}", f"{s['label']} · {face or 'dot'}", notes)
            self.assertEqual(self.errors, [])

    def test_city_tools_and_tokyo_station(self):
        """🗼🎡🥖 open their city; 🚉 lists Tokyo Station's six exits (🛗 from another city: the floor's door, not the exits' 🎫), walks to each, and its arrows agree with Python."""
        tool = CITIES["tools"]["🚉"]
        tokyo = next(f for f in CITIES["floors"] if f["id"] == "tokyo")
        exits = [next(s for s in tokyo["spots"] if s["id"] == i) for i in tool["spots"]]
        panel = '.ui-world-head .ui-world-menu[data-menu="tool"] .ui-world-rows'        # 🚉 is the only tool menu of the cities (🗼🎡🥖 are floor labels)
        rows = panel + ' a'
        for size in SIZES:
            page = self.open(size)
            self.start(page)
            for emoji, fl in (("🎡", "london"), ("🥖", "paris"), ("🗼", "tokyo")):
                page.click(f'.ui-world-tools label[for="cities-floor-{fl}"]')
                page.wait_for_function(f"() => getComputedStyle(document.querySelector('{CITY_FLOOR.format(fl)}')).display !== 'none'")
                page.wait_for_function(f"() => document.querySelector('.ui-world-goto').value === '{fl}'")      # the pulldown follows within a frame
                self.assertEqual(page.text_content(f'.ui-world-tools label[for="cities-floor-{fl}"]'), emoji)
                page.wait_for_timeout(150)
                self.shot(page, "tool", fl, emoji, f"{emoji} {next(f['label'] for f in CITIES['floors'] if f['id'] == fl)}")
            self.show(page, "london")
            page.click('.ui-world-head .ui-world-menu[data-menu="tool"] > summary')
            self.assertEqual(page.eval_on_selector_all(rows, "els => els.map(a => a.querySelector('.ui-world-arrow').textContent)"), ["🛗"] * 6)
            self.shot(page, "tool", "london", "station-door", "🚉 from London: 🛗 ×6")
            page.keyboard.press("Escape")
            for s in exits:
                with self.subTest(size=size, exit=s["id"]):
                    page.click('.ui-world-head .ui-world-menu[data-menu="tool"] > summary')
                    page.click(f'{panel} a[href="#cities-spot-{s["id"]}"]')
                    page.evaluate(CITY_WALK, "tokyo")
                    self.assertEqual(page.input_value(".ui-world-goto"), "tokyo")
                    self.assertEqual(page.text_content(f"#cities-spot-{s['id']} h3"), s["label"])
                    here = page.evaluate(CITY_POS, "tokyo")
                    self.assertLess(abs(here[0] - s["x"]) + abs(here[1] - s["y"]), .05)          # Tokyo has no water: every exit is reached exactly
                    page.click(".ui-sheet-close:visible")
                    page.click('.ui-world-head .ui-world-menu[data-menu="tool"] > summary')
                    want = [W.world_direction(here, [e["x"], e["y"]], tokyo["tile"]) for e in exits]
                    page.wait_for_function("([sel, want]) => JSON.stringify([...document.querySelectorAll(sel)].map(a => a.querySelector('.ui-world-arrow').textContent)) === JSON.stringify(want)",
                                           arg=[rows, want], timeout=3000)
                    self.still(page)
                    self.shot(page, "tool", "tokyo", f"station-{s['id']}", f"🚉 at {s['label']}")
                    page.keyboard.press("Escape")
            self.assertEqual(self.errors, [])

    def test_keys_pad_and_water_at_the_real_speed(self):
        """Arrow keys (desktop) and the pad (phone) step one tile; a step into the Thames or the Seine is refused. Normal speed, no FAST."""
        for size in SIZES:
            page = self.open(size, path=self.page_path)
            self.start(page)
            for f in CITIES["floors"]:
                fl, tile = f["id"], f["tile"]
                blocked = W.world_blocked(f["width"], f["height"], tile, f["props"])
                self.show(page, fl)
                page.focus(".ui-world-view")                                                         # the 🛗 pulldown kept the focus: keys go to the map again
                steps = [((0, -1), "ArrowUp"), ((1, 0), "ArrowRight"), ((0, 1), "ArrowDown"), ((-1, 0), "ArrowLeft")]
                for (dx, dy), key in steps:
                    with self.subTest(size=size, floor=fl, key=key):
                        cx, cy = city_cell(page.evaluate(CITY_POS, fl), tile)
                        n = (cx + dx, cy + dy)
                        free = 0 <= n[0] < len(blocked[0]) and 0 <= n[1] < len(blocked) and blocked[n[1]][n[0]] == "0"
                        if page.touch:
                            page.dispatch_event(f'[data-step="{dx},{dy}"]', "pointerdown")
                            page.dispatch_event(f'[data-step="{dx},{dy}"]', "pointerup")
                        else:
                            page.keyboard.press(key)
                        page.wait_for_timeout(100)
                        page.evaluate(CITY_WALK, fl)
                        self.assertEqual(city_cell(page.evaluate(CITY_POS, fl), tile), n if free else (cx, cy))
                water = [c for c in W.world_reach(blocked, city_cell([f["player"]["x"], f["player"]["y"]], tile))
                         if c[1] + 1 < len(blocked) and blocked[c[1] + 1][c[0]] == "1"]                  # a free tile with water just below it
                if not water:
                    continue                                                                         # Tokyo has no water
                with self.subTest(size=size, floor=fl, shore=water[0]):
                    shore = water[len(water) // 2]
                    box = page.evaluate(f"() => {{ const r = document.querySelector('{CITY_FLOOR.format(fl)}').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }}")
                    self.tap(page, box[0] + (shore[0] + .5) * tile * box[2] / f["width"], box[1] + (shore[1] + .5) * tile * box[3] / f["height"])
                    page.wait_for_timeout(100)
                    seen = page.evaluate(CITY_WALK, fl)
                    self.assertEqual([p for p in seen if blocked[city_cell(p, tile)[1]][city_cell(p, tile)[0]] == "1"], [])
                    at = city_cell(page.evaluate(CITY_POS, fl), tile)
                    if blocked[at[1] + 1][at[0]] == "1":                                             # the tap landed on that shore: step into the river
                        if page.touch:
                            page.dispatch_event('[data-step="0,1"]', "pointerdown")
                            page.dispatch_event('[data-step="0,1"]', "pointerup")
                        else:
                            page.keyboard.press("ArrowDown")
                        page.wait_for_timeout(400)
                        self.assertEqual(city_cell(page.evaluate(CITY_POS, fl), tile), at)
                    self.shot(page, "key", fl, "shore", f"{f['label']}: 🌊 refused at {at}")
            self.assertEqual(self.errors, [])

    def test_categories_filter_the_list_and_the_map(self):
        for size in SIZES:
            page = self.open(size)
            self.start(page)
            for f in CITIES["floors"]:
                fl = f["id"]
                self.show(page, fl)
                for cat in ["", *sorted({s["category"] for s in f["spots"]})]:
                    with self.subTest(size=size, floor=fl, category=cat or "all"):
                        self.menu(page, "spots")
                        page.click(f'.ui-world-menu[data-menu="spots"] label[data-cat="{cat}"]')
                        want = sorted(s["id"] for s in f["spots"] if cat in ("", s["category"]))
                        rows = page.eval_on_selector_all(f'.ui-world-spots[data-floor="{fl}"] li', "els => els.filter(e => e.offsetParent).map(e => e.querySelector('a').getAttribute('href'))")
                        marks = page.eval_on_selector_all(f"{CITY_FLOOR.format(fl)} .ui-spot", "els => els.filter(e => getComputedStyle(e).display !== 'none').map(e => e.getAttribute('href'))")
                        self.assertEqual(sorted(h.split("-spot-")[1] for h in rows), want)
                        self.assertEqual(sorted(h.split("-spot-")[1] for h in marks), want)
                        self.shot(page, "category", fl, cat or "all", f"🏷️ {cat or 'all'} ({len(want)})")
                        page.keyboard.press("Escape")
                self.menu(page, "spots")
                page.click('.ui-world-menu[data-menu="spots"] label[data-cat=""]')
                page.keyboard.press("Escape")
            self.assertEqual(self.errors, [])

    def test_favorites_across_the_cities_and_home(self):
        page = self.open("phone")
        self.start(page)
        first = {f["id"]: f["spots"][0] for f in CITIES["floors"]}
        for fl, s in first.items():
            self.show(page, fl)
            self.menu(page, "spots")
            page.click(f'.ui-world-spots[data-floor="{fl}"] li:has(a[href="#cities-spot-{s["id"]}"]) .ui-world-star')
            page.keyboard.press("Escape")
        self.menu(page, "favorites")
        self.assertEqual(page.eval_on_selector_all(".ui-world-favs a", "els => els.map(e => e.lastChild.textContent)"), [s["label"] for s in first.values()])
        self.shot(page, "favorite", "paris", "panel", "⭐ ×3")
        page.click(f'.ui-world-favs a[href="#cities-spot-{first["london"]["id"]}"]')       # from Paris to London in one tap
        self.assertEqual(page.input_value(".ui-world-goto"), "london")
        self.assertTrue(page.is_visible(f"#cities-spot-{first['london']['id']}"))
        page.click(".ui-world-home")
        page.click('.ui-world-ask button[data-t="home"]')
        self.assertEqual(page.input_value(".ui-world-goto"), "tokyo")
        self.shot(page, "favorite", "tokyo", "home", "🏠 → Parallel Tokyo")
        self.assertEqual(self.errors, [])

    def test_shimbashi_sheet_keeps_the_player_visible_at_the_map_edge(self):
        for size in SIZES:
            page = self.open(size)
            self.start(page)
            for spot in CITIES["floors"][0]["spots"]:
                self.menu(page, "spots")
                page.click(f'.ui-world-spots[data-floor="tokyo"] a[href="#cities-spot-{spot["id"]}"]')
                page.evaluate(CITY_WALK, "tokyo")
                self.still(page)
                if spot["id"] == "tokyo-shimbashi":
                    notes = []
                    if page.evaluate(CITY_TOP, f"{CITY_FLOOR.format('tokyo')} .ui-player")["sheet"]:
                        notes.append("⚠️ シートが🧳を隠す")
                    self.shot(page, "sheet", "tokyo", spot["id"], spot["label"], notes)
                    with self.subTest(size=size):
                        self.assertEqual(notes, [])
                    break
                page.click(".ui-sheet-close:visible")
            self.assertEqual(self.errors, [])

    def test_every_width_fits_each_city(self):
        for size, (width, height, touch) in WIDTHS.items():
            page = self.open(size)
            self.start(page)
            for f in CITIES["floors"]:
                with self.subTest(size=size, floor=f["id"]):
                    self.show(page, f["id"])
                    self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth - innerWidth"), 0)
                    self.assertTrue(page.is_visible(f"{CITY_FLOOR.format(f['id'])} .ui-player"))
                    self.assertTrue(page.is_visible(".ui-world-dpad"))                                # every city is a grid
                    notes = []
                    tall = page.evaluate("document.documentElement.scrollHeight - innerHeight")
                    if tall > 0:
                        notes.append(f"⚠️ 縦に {tall}px はみ出す")
                    cut = page.evaluate("() => [...document.querySelectorAll('.ui-world-head .ui-board > strong, .ui-world-head .ui-board-clock')].filter(e => e.scrollWidth > e.clientWidth + 1 || e.getBoundingClientRect().right > e.closest('.ui-board').getBoundingClientRect().right + 1).map(e => e.textContent)")
                    if cut:
                        notes.append("⚠️ ヘッダーで切れる: " + " / ".join(cut))
                    out = page.evaluate("() => [...document.querySelectorAll('.ui-world-head .ui-world-tools > *, .ui-world-side summary, .ui-world-goto')].filter(e => { const r = e.getBoundingClientRect(); return r.width && (r.left < 0 || r.right > innerWidth + .5) }).map(e => e.textContent.trim().slice(0, 4))")
                    self.assertEqual(out, [], "a control sticks out of the window")
                    self.shot(page, "width", f["id"], f"{width}x{height}", f"{f['label']} {width}×{height}", notes)
                    self.assertEqual(notes, [], "layout must fit without visual warnings")
            self.assertEqual(self.errors, [])

    def test_every_language_labels_the_city_tools(self):
        page = self.open("phone")
        self.start(page)
        codes = [code for code, _ in W.CHROME_LANGS]
        for code in codes:
            with self.subTest(lang=code):
                self.menu(page, "settings")
                page.select_option(".ui-world-head [data-lang]", code)
                self.assertEqual(page.evaluate("document.querySelector('.ui-world').lang"), code)
                labels = page.eval_on_selector_all(".ui-world-head .ui-world-home, .ui-world-tools > label.ui-world-tool, .ui-world-head summary", "els => els.map(e => e.getAttribute('aria-label'))")
                self.assertTrue(all(labels), labels)
                if code == "en":
                    self.assertEqual(labels[1:4], ["Parallel Tokyo", "Reverse London", "Fake Paris"])
                if code != "ja":
                    self.assertNotEqual(labels[0], "ホーム")
                self.shot(page, "lang", "tokyo", code, f"🌐 {code}: {' · '.join(labels[:4])}")
                page.keyboard.press("Escape")
        self.assertEqual(self.errors, [])

    def test_every_language_leaves_no_japanese_label_but_a_name(self):
        """🌐 Every button, tooltip and placeholder of the village, the school and the cities reads in each of the eleven languages: a
        label still in Japanese is only the name of something the scene shows by that name (a place, a person, a thing), which the
        browser's own translate reads, never a button's. The text the shell writes for every scene (⭐ 🧰 📖) follows too."""
        kana = r"[぀-ヿ]"
        leftover = """re => { const shown = new Set(); const w = document.createTreeWalker(document.body, 4);
            for (let t; (t = w.nextNode());) shown.add(t.nodeValue.trim());
            const bare = s => s.replace(/^[^\\p{L}\\p{N}]+|[^\\p{L}\\p{N}]+$/gu, '');
            return [...document.querySelectorAll('[aria-label],[title],[placeholder]')].flatMap(n => ['aria-label', 'title', 'placeholder'].map(a => n.getAttribute(a)))
                .filter(v => v && new RegExp(re).test(v) && !shown.has(v) && ![...shown].some(s => bare(s) === bare(v))) }"""
        for name in ("overworld", "school", "cities"):
            path = Path(self.tmp.name) / f"{name}-lang.html"
            path.write_text(W.world_document(W.example_data(name)), encoding="utf-8")
            page = self.open("desktop", path=path)
            if page.locator("[data-emoji]").count():
                page.locator("[data-emoji]").first.click()
            for code, _ in W.CHROME_LANGS[1:]:
                with self.subTest(world=name, lang=code):
                    page.evaluate("c => { for (const s of document.querySelectorAll('[data-lang]')) { s.value = c; s.dispatchEvent(new Event('change', {bubbles: true})) } }", code)
                    self.assertEqual(page.evaluate(leftover, kana), [])
            page.evaluate("() => { for (const s of document.querySelectorAll('[data-lang]')) { s.value = 'ja'; s.dispatchEvent(new Event('change', {bubbles: true})) } }")
            self.assertEqual(page.evaluate("[...document.querySelectorAll('.ui-player')].map(p => p.getAttribute('aria-label'))")[:1], ["自分"])   # and back
        self.assertEqual(self.errors, [])

    def test_without_javascript_each_city_is_a_static_map(self):
        for size in SIZES:
            page = self.open(size, js=False)
            for f in CITIES["floors"]:
                with self.subTest(size=size, floor=f["id"]):
                    page.click(f'.ui-world-foot label[for="cities-floor-{f["id"]}"]')
                    self.assertTrue(page.is_visible(CITY_FLOOR.format(f["id"])))
                    self.assertEqual(page.eval_on_selector_all(f"{CITY_FLOOR.format(f['id'])} .ui-spot", "els => els.length"), len(f["spots"]))
                    self.assertFalse(page.is_visible(".ui-world-pick"))
                    s = f["spots"][0]
                    page.evaluate(f"location.hash = '#cities-spot-{s['id']}'")                     # a spot link without JS: the sheet is a :target
                    self.assertTrue(page.is_visible(f"#cities-spot-{s['id']}"))
                    self.shot(page, "nojs", f["id"], "static", f"🚫JS {f['label']} · {s['label']}")
                    page.click(f"#cities-spot-{s['id']} .ui-sheet-close")                         # ✖️ is a link to #cities-map: the sheet leaves the footer free
                    self.assertFalse(page.is_visible(f"#cities-spot-{s['id']}"))

    def test_the_picker_offers_every_avatar(self):
        page = self.open("phone")
        self.shot(page, "pick", "tokyo", "picker", "🙂 picker")
        self.start(page, CITIES["avatars"][0])
        for emoji in CITIES["avatars"][1:]:
            with self.subTest(avatar=emoji):
                self.menu(page, "settings")
                page.click("[data-pick-open]")
                page.click(f'[data-emoji="{emoji}"]')
                page.wait_for_function(W.PICKED)
                self.assertEqual(page.eval_on_selector_all(".ui-player span", "els => [...new Set(els.map(e => e.textContent))]"), [emoji])
        self.shot(page, "pick", "tokyo", "last", f"🙂 → {CITIES['avatars'][-1]}")
        self.assertEqual(self.errors, [])

    def test_reduced_motion_jumps_to_the_spot(self):
        page = self.open("desktop", path=self.page_path, reduced=True)
        self.start(page)
        for f in CITIES["floors"]:
            with self.subTest(floor=f["id"]):
                self.show(page, f["id"])
                s = max(f["spots"], key=lambda s: abs(s["x"] - f["player"]["x"]) + abs(s["y"] - f["player"]["y"]))   # the farthest spot
                self.menu(page, "spots")
                page.click(f'.ui-world-spots a[href="#cities-spot-{s["id"]}"]')
                page.wait_for_timeout(100)
                self.assertTrue(page.evaluate(W.SETTLED))                                  # no walk to wait for
                self.still(page)
                self.shot(page, "map", f["id"], f"reduced-{s['id']}", f"🐢→⚡ reduced motion: {s['label']}")
                page.click(".ui-sheet-close:visible")
        self.assertEqual(self.errors, [])

    def test_the_name_layer_switches_without_a_reload(self):
        """Cities open with dots (the name of the spot the player stands by, the one under the pointer and the focused one); 🏷️ in ⚙️ switches to names or off, kept across reloads."""
        px = lambda sel: page.eval_on_selector_all(sel, "els => els.map(e => getComputedStyle(e).fontSize)")   # noqa: E731
        for size in SIZES:
            page = self.open(size)
            self.start(page)
            self.show(page, "london")
            page.mouse.move(1, 1)                                                                   # the pointer left on the map would :hover a dot into its name
            plain = f'{CITY_FLOOR.format("london")} .ui-spot:not([data-sign])'
            self.assertEqual(page.get_attribute(".ui-world", "data-names"), "dots")
            london = next(f for f in CITIES["floors"] if f["id"] == "london")
            here, reach = london["player"], london["tile"] * 1.5
            near = [min((s for s in london["spots"] if not s.get("sign")), key=lambda s: max(abs(s["x"] - here["x"]), abs(s["y"] - here["y"])))["label"]]
            self.assertEqual(near, ["キングス・クロス"])
            self.assertLessEqual(max(abs(london["spots"][0]["x"] - here["x"]), abs(london["spots"][0]["y"] - here["y"])), reach)
            sizes = px(plain)
            self.assertEqual(sizes.count("0px"), len(sizes) - len(near), "only the spot the player stands by shows its name")
            self.assertEqual(sorted(page.eval_on_selector_all(f"{plain}[data-near]", "els => els.map(e => e.textContent)")), near)
            marks = page.eval_on_selector_all(plain, "els => els.map(e => [e.dataset.category, getComputedStyle(e, '::before').content, getComputedStyle(e, '::before').transform])")
            self.assertEqual({(c, m) for c, m, _ in marks}, {("terminus", '"🚆"'), ("station", '"🚉"')})   # the emoji, not the dot; London is its transport
            self.assertEqual({t for _, _, t in marks}, {"matrix(1.5, 0, 0, 1.5, 0, 0)"})                                                           # mark_scale [1.5, 1.5]
            marker = f'{CITY_FLOOR.format("london")} .ui-spot[href="#cities-spot-london-charing-cross"]'
            self.menu(page, "spots")
            page.click('.ui-world-spots[data-floor="london"] a[href="#cities-spot-london-charing-cross"]')
            page.evaluate(CITY_WALK, "london")
            page.click(".ui-sheet-close:visible")
            self.still(page)
            self.assertEqual(self.press(page, marker), [], "a dot is never covered by a neighbour's name")   # ⚠️ in the names layer: Embankment covered it
            page.click(".ui-sheet-close:visible")
            self.still(page)
            self.shot(page, "layer", "london", "dots", "● dots: names beside 🧳 only")
            for mode, want in (("names", 0), ("off", len(sizes)), ("dots", len(sizes) - len(near))):
                with self.subTest(size=size, names=mode):
                    self.menu(page, "settings")
                    page.select_option("[data-names-pick]", mode)
                    page.keyboard.press("Escape")
                    page.mouse.move(1, 1)
                    self.assertEqual(page.get_attribute(".ui-world", "data-names"), mode)
                    self.assertEqual(px(plain).count("0px"), want)
                    self.shot(page, "layer", "london", mode, {"names": "🏷️ names: every name", "off": "✖️ off: dots only", "dots": "● dots"}[mode])
            self.menu(page, "settings")
            page.select_option("[data-names-pick]", "names")
            page.reload()
            self.start(page)
            self.assertEqual(page.get_attribute(".ui-world", "data-names"), "names")   # kept with the language
            self.assertEqual(self.errors, [])

    def test_tokyo_exits_are_always_named_behind_the_marks(self):
        """Tokyo Station's six exits (always_named) keep their names in every 🏷️ mode, faint in the name layer behind the marks, with 🎫 on the point;
        丸の内 hangs to the left and 八重洲 to the right, so the two sides of the station never cover each other, even with the whole map in view."""
        named = f'{CITY_FLOOR.format("tokyo")} .ui-spot[data-named]'
        read = ("els => Object.fromEntries(els.map(e => { const r = e.getBoundingClientRect(), c = getComputedStyle(e); return [e.getAttribute('href').split('-spot-tokyo-')[1],"
                " {side: e.dataset.named, size: c.fontSize, layer: c.zIndex, near: e.hasAttribute('data-near'), mark: getComputedStyle(e, '::before').content, left: r.left, right: r.right}] }))")
        for size in SIZES:
            page = self.open(size)
            self.start(page)
            for mode in ("dots", "off", "names"):
                with self.subTest(size=size, names=mode):
                    self.menu(page, "settings")
                    page.select_option("[data-names-pick]", mode)
                    page.keyboard.press("Escape")
                    page.mouse.move(1, 1)
                    exits = page.eval_on_selector_all(named, read)
                    self.assertEqual(sorted(exits), ["marunouchi-c", "marunouchi-n", "marunouchi-s", "yaesu-c", "yaesu-n", "yaesu-s"])
                    self.assertNotIn("0px", {e["size"] for e in exits.values()}, "an exit never shrinks to a dot")
                    self.assertEqual({e["mark"] for e in exits.values()}, {'"🎫"'})
                    self.assertEqual({k: e["layer"] for k, e in exits.items() if not e["near"]}, {k: "1" for k, e in exits.items() if not e["near"]})   # the name layer, behind the marks
                    self.assertEqual({k: e["side"] for k, e in exits.items()}, {k: "left" if k.startswith("marunouchi") else "right" for k in exits})
                    for part in "ncs":
                        self.assertLessEqual(exits[f"marunouchi-{part}"]["right"], exits[f"yaesu-{part}"]["left"], "the two sides of the station do not cover each other")
                    self.shot(page, "layer", "tokyo", f"exits-{mode}", f"🎫 exits always named ({mode})")
            self.assertEqual(self.errors, [])

    def test_zoom_dial_and_overlay_opacity(self):
        """⚙️ 🔍 is a rotary dial (dial.js over a range): a drag around it zooms the camera, the wheel on the map turns it back, its keys step it.
        ⚙️ 🫥 is a slider: the controls over the map (the pad, data-overlay) take its opacity, kept across reloads."""
        Z = "() => [Number(document.querySelector('.ui-world-cam').style.getPropertyValue('--z')), Number(document.querySelector('.ui-world-zoom input').value), document.querySelector('.ui-world-zoom .ui-dial').style.getPropertyValue('--ui-dial-angle')]"
        for size in SIZES:
            page = self.open(size)
            self.start(page)
            self.menu(page, "settings")
            z0, v0, a0 = page.evaluate(Z)
            self.assertAlmostEqual(z0, v0, delta=.01)                                              # the dial shows the camera's zoom
            box = page.locator(".ui-world-zoom .ui-dial").bounding_box()
            cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            if page.touch:
                page.touchscreen.tap(cx + 20, cy)                                                 # a finger at 3 o'clock on the dial
            else:
                page.mouse.move(cx + 20, cy)
                page.mouse.down()
                page.mouse.move(cx + 20, cy + 1, steps=2)
                page.mouse.up()
            page.wait_for_timeout(100)
            z1, v1, a1 = page.evaluate(Z)
            self.assertAlmostEqual(v1, .1 + (CITIES["zoom_max"] - .1) * (90 + 135) / 270, delta=.06)   # 3 o'clock is 5/6 of the dial
            self.assertAlmostEqual(z1, v1, delta=.01)
            self.assertEqual(a1, "90deg" if abs(float(a1[:-3]) - 90) < 2 else a1)
            self.shot(page, "tool", "tokyo", "zoom-dial", f"🔍 dial → z {z1:.2f}")
            page.focus(".ui-world-zoom input")
            page.keyboard.press("ArrowLeft")
            page.wait_for_timeout(50)
            z2, v2, _ = page.evaluate(Z)
            self.assertAlmostEqual(v2, v1 - .05, delta=.001)                                       # the range's own keys
            self.assertAlmostEqual(z2, v2, delta=.01)
            page.keyboard.press("Escape")
            self.assertEqual(page.eval_on_selector(".ui-world-dpad", "e => getComputedStyle(e).opacity"), "0.9")
            self.menu(page, "settings")
            page.locator("[data-alpha]").fill("0.3")
            self.assertEqual(page.eval_on_selector(".ui-world-dpad", "e => getComputedStyle(e).opacity"), "0.3")
            page.keyboard.press("Escape")
            self.shot(page, "tool", "tokyo", "overlay-alpha", "🫥 .3: the pad lets the map through")
            page.reload()
            self.start(page)
            self.assertEqual(page.eval_on_selector(".ui-world-dpad", "e => getComputedStyle(e).opacity"), "0.3")   # kept with the language
            self.assertEqual(page.input_value("[data-alpha]"), "0.3")
            self.assertEqual(self.errors, [])

    def test_fires_rivers_and_bridges_are_drawn(self):
        page = self.open("desktop")
        self.start(page)
        for f in CITIES["floors"]:
            self.show(page, f["id"])
            blocked = W.world_blocked(f["width"], f["height"], f["tile"], f["props"])
            for kind in ("fire", "water", "bridge"):
                props = [p for p in f["props"] if p["kind"] == kind]
                with self.subTest(floor=f["id"], kind=kind):
                    images = page.eval_on_selector_all(f'{CITY_FLOOR.format(f["id"])} .ui-prop[data-kind="{kind}"]', "els => els.map(e => getComputedStyle(e).backgroundImage)")
                    self.assertEqual(len(images), len(props))
                    if kind != "bridge":
                        self.assertTrue(all("data:image/svg+xml" in i for i in images))
                    if kind == "fire":                                                                # a decoration: it stands on a free tile
                        self.assertEqual([p for p in props if blocked[p["y"] // f["tile"]][p["x"] // f["tile"]] == "1"], [])
            if f["id"] != "tokyo":
                self.shot(page, "fire", f["id"], "fit", f"{f['label']}: 🔥{sum(p['kind'] == 'fire' for p in f['props'])} 🌊{sum(p['kind'] == 'water' for p in f['props'])} 🌉{sum(p['kind'] == 'bridge' for p in f['props'])}")
        self.assertEqual(self.errors, [])


class ToolChromeTests(unittest.TestCase):
    """🧰 The chrome of a tool page (PySaiyanWeBoo's chrome, put on by add_part) on two pages of one site: the board's clock in seconds, ☰ this page's own
    (itself with 📍, its sections, the rows it gives, each with ☆), ⭐ and 🌐 that follow to the next tool, ⏯️, ⋯ ⬆️ ⬇️, the emoji a page
    adds, a phone, and no JavaScript.
    The star-and-language run is recorded to test-results/tools-chrome/tools-chrome-star-and-language-<UTC>.gif."""
    SPEC = {"board": {"title": "TOOLS", "items": [{"text": "🎞 GIF工房"}, {"text": "🌊 流れの実験室"}]}, "home": "../../index.html#tools",
            "places": [{"label": "🌊 流れの実験室へ", "href": "../flow/index.html"}],
            "tools": {"🗼": {"label": "パラレル都市", "label_en": "Parallel cities", "links": [{"label": "🗼 パラレル東京", "href": "../demos/cities.html"}]}}}

    @classmethod
    def setUpClass(cls):
        def tool(title, parts):
            body = f"<main><h1>{title}</h1>" + "".join(f'<h2>{part}</h2><p style="min-height:480px">{part}…</p>' for part in parts) + "</main>"
            return ui.add_part(W.render_document(trusted_html=body, title=title, css=W.bundled_css()), ui.component_parts("chrome", cls.SPEC), at="top")
        cls.pages = {"/tools/gif/": tool("🎞 GIF工房", ["えらぶ", "ならべる", "つくる"]), "/tools/flow/index.html": tool("🌊 流れの実験室", [])}
        cls.pw = sync_playwright().start()
        cls.browser = W.launch(cls.pw)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def open(self, path="/tools/gif/", width=1280, height=800, js=True):
        context = self.browser.new_context(viewport={"width": width, "height": height}, java_script_enabled=js)
        self.addCleanup(context.close)
        self.requests = []
        context.route("http://tools.test/**", lambda route: (self.requests.append(route.request.url), route.fulfill(
            content_type="text/html", body=self.pages.get(route.request.url.removeprefix("http://tools.test"), "<main>404</main>")))[1])
        page = context.new_page()
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.goto("http://tools.test" + path)
        return page

    def menu(self, page, kind):
        page.click(f'.ui-chrome [data-menu="{kind}"] > summary')
        return page.locator(f'.ui-chrome [data-menu="{kind}"] .ui-world-panel')

    def test_clock_counts_seconds_and_pauses_only_the_board(self):
        page = self.open()
        clock = page.locator(".ui-chrome [data-clock]")
        first = clock.inner_text()
        self.assertRegex(first, r"^\d\d:\d\d:\d\d$")
        page.wait_for_function("t => document.querySelector('.ui-chrome [data-clock]').textContent !== t", arg=first, timeout=3000)
        self.assertRegex(clock.inner_text(), r"^\d\d:\d\d:\d\d$")
        state = "() => getComputedStyle(document.querySelector('.ui-chrome .ui-board-run')).animationPlayState"
        self.assertEqual(page.evaluate(state), "running")
        self.menu(page, "settings").locator(".ui-world-pause").click()                       # ⏯️
        self.assertEqual(page.evaluate(state), "paused")
        self.assertEqual(page.locator(".ui-chrome .ui-world-pause").inner_text(), "▶️")
        stopped = clock.inner_text()
        page.wait_for_function("t => document.querySelector('.ui-chrome [data-clock]').textContent !== t", arg=stopped, timeout=3000)   # the clock goes on
        page.click(".ui-chrome .ui-world-pause")
        self.assertEqual(page.evaluate(state), "running")
        self.assertEqual(self.errors, [])

    def test_menus_open_one_at_a_time_and_the_list_is_this_page(self):
        page = self.open()
        for kind in ("favorites", "settings", "spots", "more", "tool"):
            self.assertTrue(page.locator(f'.ui-chrome [data-menu="{kind}"] > summary').is_visible(), kind)
        rows = self.menu(page, "spots")                                                                          # ☰ the page, its h2, the row it gave
        self.assertEqual([t.replace("\n", "") for t in rows.locator("a").all_inner_texts()], ["📍🎞 GIF工房", "えらぶ", "ならべる", "つくる", "🌊 流れの実験室へ"])
        self.assertEqual(rows.locator("a[aria-current=page]").count(), 1)
        self.assertEqual(rows.locator(".ui-world-star").all_inner_texts(), ["☆"] * 5)
        rows.locator("a").nth(3).click()                                                                         # a section: there, and ☰ closes
        self.assertEqual(page.evaluate("location.hash"), "#tools-chrome-part-3")
        self.assertEqual(page.locator(".ui-chrome .ui-world-menu[open]").count(), 0)
        self.assertLess(page.evaluate("document.querySelector('#tools-chrome-part-3').getBoundingClientRect().top"), 400)
        self.menu(page, "spots")
        links = self.menu(page, "tool")                                                                          # 🗼 opens, ☰ closes
        page.wait_for_function("() => document.querySelectorAll('.ui-chrome .ui-world-menu[open]').length === 1")
        self.assertEqual(page.evaluate("[...document.querySelectorAll('.ui-chrome .ui-world-menu[open]')].map(m => m.dataset.menu)"), ["tool"])
        self.assertEqual(links.locator("a").get_attribute("href"), "../demos/cities.html")
        page.keyboard.press("Escape")
        self.assertEqual(page.locator(".ui-chrome .ui-world-menu[open]").count(), 0)
        self.menu(page, "settings")
        page.mouse.click(320, 640)                                                                               # a tap on the page closes it
        self.assertEqual(page.locator(".ui-chrome .ui-world-menu[open]").count(), 0)
        self.assertEqual(page.get_attribute(".ui-chrome .ui-world-home", "href"), "../../index.html#tools")
        bare = self.open("/tools/flow/index.html")                                                               # a page without sections: itself, and the row
        self.assertEqual([t.replace("\n", "") for t in self.menu(bare, "spots").locator("a").all_inner_texts()], ["📍🌊 流れの実験室", "🌊 流れの実験室へ"])
        self.assertEqual(self.errors, [])

    def test_more_moves_this_screen_to_its_end_and_back(self):
        page = self.open(height=480)
        self.menu(page, "more").locator('[data-scroll="bottom"]').click()                                        # ⋯ ⬇️
        page.wait_for_function("() => scrollY + innerHeight >= document.documentElement.scrollHeight - 1")
        self.assertEqual(page.locator(".ui-chrome .ui-world-menu[open]").count(), 0)
        self.assertGreater(page.evaluate("scrollY"), 480)
        page.evaluate("document.querySelector('.ui-chrome').scrollIntoView()")                                   # the chrome is at the page's top
        self.menu(page, "more").locator('[data-scroll="top"]').click()                                           # ⋯ ⬆️
        page.wait_for_function("() => scrollY === 0")
        self.assertEqual(page.locator('.ui-chrome [data-scroll]').all_text_contents(), ["⬆️", "⬇️"])
        self.assertEqual(self.errors, [])

    def test_star_and_language_follow_to_the_next_tool_with_a_gif(self):
        page = self.open(width=560, height=480)
        cam = W.Camera(page)
        cam.hold(600)
        self.assertEqual(page.evaluate("Object.keys(localStorage)"), [])                                          # nothing is kept until asked
        rows = self.menu(page, "spots")
        cam.hold(700)
        rows.locator("li", has_text="つくる").locator(".ui-world-star").click()                                    # ☆ a section of this page
        rows.locator("li").first.locator(".ui-world-star").click()                                                # ☆ the page itself
        self.assertEqual(rows.locator(".ui-world-star").all_inner_texts(), ["★", "☆", "☆", "★", "☆"])
        cam.hold(700)
        favs = self.menu(page, "favorites")
        self.assertEqual([t.replace("\n", "") for t in favs.locator("a").all_inner_texts()], ["🎞 GIF工房 › つくる", "📍🎞 GIF工房"])
        cam.hold(900)
        self.menu(page, "settings")
        cam.hold(500)
        page.select_option(".ui-chrome [data-lang]", "en")
        self.assertEqual(page.get_attribute(".ui-chrome .ui-world-home", "aria-label"), "Home")
        self.assertEqual(page.get_attribute('.ui-chrome [data-menu="tool"] > summary', "title"), "Parallel cities")   # a page's own emoji, its own words
        self.assertEqual(page.get_attribute(".ui-chrome", "lang"), "en")
        cam.hold(700)
        self.menu(page, "spots").locator("a", has_text="流れの実験室へ").click()                                    # the row the page gave leads out
        page.wait_for_url("http://tools.test/tools/flow/index.html")
        page.wait_for_function("() => document.querySelector('.ui-chrome')?.hasAttribute('data-js')")
        cam.hold(600)
        self.assertEqual(page.get_attribute(".ui-chrome .ui-world-home", "aria-label"), "Home")                    # 🌐 followed
        self.assertEqual(page.get_attribute(".ui-chrome .ui-world-star >> nth=0", "aria-label"), "Favorite")       # and the rows the script made speak it
        favs = self.menu(page, "favorites")
        self.assertEqual(favs.locator("a").all_inner_texts(), ["🎞 GIF工房 › つくる", "🎞 GIF工房"])                   # ⭐ followed: places of another tool
        cam.hold(900)
        kept = page.evaluate("Object.fromEntries(Object.keys(localStorage).map(k => [k, JSON.parse(localStorage.getItem(k))]))")
        self.assertEqual(kept, {"ui-chrome:tools-chrome": {"lang": "en", "fav": [
            {"href": "/tools/gif/#tools-chrome-part-3", "label": "🎞 GIF工房 › つくる"}, {"href": "/tools/gif/", "label": "🎞 GIF工房"}]}})   # one key, two fields
        favs.locator("a").first.click()                                                                           # ⭐ leads to the starred section
        page.wait_for_url("http://tools.test/tools/gif/#tools-chrome-part-3")
        page.wait_for_function("() => document.querySelector('.ui-chrome')?.hasAttribute('data-js')")
        self.assertLess(page.evaluate("document.querySelector('#tools-chrome-part-3').getBoundingClientRect().top"), 240)
        cam.hold(700)
        self.menu(page, "favorites").locator(".ui-world-star").first.click()                                      # ★ again: gone, here and in ☰
        self.assertEqual(page.evaluate("JSON.parse(localStorage.getItem('ui-chrome:tools-chrome')).fav.map(f => f.href)"), ["/tools/gif/"])
        self.assertEqual(page.locator(".ui-chrome .ui-world-spots .ui-world-star").all_text_contents(), ["★", "☆", "☆", "☆", "☆"])
        cam.hold(600)
        self.assertEqual([url for url in self.requests if not url.startswith("http://tools.test/tools/")], [])    # the chrome asks for nothing
        self.assertEqual(self.errors, [])
        target = W.gif_targets(W.ROOT / "test-results" / "tools-chrome", ["tools-chrome-star-and-language"], run_details=["timestamp"])
        gif = W.encode(cam.shots, width=392)
        target["tools-chrome-star-and-language"].write_bytes(gif)
        self.assertEqual(gif[:6], b"GIF89a")

    def test_side_stands_at_the_edge_on_a_desktop_and_rides_the_header_on_a_phone(self):
        for width, height, position in ((1280, 800, "fixed"), (392, 848, "static"), (320, 568, "static")):
            with self.subTest(width=width):
                page = self.open(width=width, height=height)
                self.assertEqual(page.evaluate("getComputedStyle(document.querySelector('.ui-chrome .ui-world-side')).position"), position)
                self.assertEqual(page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"), 0)
                panel = self.menu(page, "spots")
                box, head = panel.bounding_box(), page.locator(".ui-chrome").bounding_box()
                self.assertGreaterEqual(box["x"], 0)
                self.assertLessEqual(box["x"] + box["width"], width)
                self.assertLessEqual(box["y"] + box["height"], height)
                self.assertLessEqual(head["height"], 96 if width > 600 else 136, head)                # the page keeps its height
                buttons = page.evaluate("[...document.querySelectorAll('.ui-chrome summary, .ui-chrome .ui-world-home')].map(b => { const r = b.getBoundingClientRect(); return [r.width, r.height] })")
                self.assertTrue(all(w >= 40 and h >= 40 for w, h in buttons), buttons)
                self.assertEqual(self.errors, [])

    def test_without_javascript_the_board_home_and_the_list_still_work(self):
        page = self.open(js=False)
        self.assertEqual(page.locator(".ui-chrome [data-clock]").inner_text(), "--:--:--")
        for kind in ("favorites", "settings", "more"):
            self.assertTrue(page.locator(f'.ui-chrome [data-menu="{kind}"]').is_hidden(), kind)
        rows = self.menu(page, "spots")                                                       # a <details> with a row of its own: it opens by itself
        self.assertEqual(rows.locator("a").all_inner_texts(), ["🌊 流れの実験室へ"])              # the page and its sections wait for the script
        self.assertTrue(rows.locator(".ui-world-star").first.is_hidden())                     # ☆ needs the script
        rows.locator("a").click()
        page.wait_for_url("http://tools.test/tools/flow/index.html")


class OverworldRpgTests(unittest.TestCase):
    """Overworld starting-village (meadow) RPG & gamification contract in Chromium."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.page_path = Path(cls.tmp.name) / "overworld.html"
        cls.page_path.write_text(W.world_document(W.example_data("overworld")), encoding="utf-8")
        cls.pw = sync_playwright().start()
        cls.browser = W.launch(cls.pw)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.tmp.cleanup()

    def open(self, width=1280, height=800, touch=False):
        context = self.browser.new_context(viewport={"width": width, "height": height}, has_touch=touch, is_mobile=touch)
        self.addCleanup(context.close)
        page = context.new_page()
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and self.errors.append(m.text))
        page.goto(self.page_path.as_uri())
        page.click('[data-emoji="🧙"]')
        page.wait_for_function(W.PICKED)
        page.wait_for_selector(".ui-rpg-hud", state="visible")
        return page

    def test_contact_npc_dialogue_and_fountain_heal(self):
        page = self.open()
        # Player starts at (12, 14); guide cat sits at (13, 13). Stepping Up then Right contacts it!
        page.keyboard.press("ArrowUp")
        page.wait_for_timeout(450)
        page.keyboard.press("ArrowRight")
        dialog = page.locator(".ui-rpg-card")
        dialog.wait_for(state="visible", timeout=5000)
        self.assertIn("案内猫ミョン", dialog.inner_text())
        dialog.get_by_role("button", name="つぎへ ▶").click()
        self.assertIn("[2/3]", dialog.inner_text())
        dialog.locator(".ui-rpg-close").click()
        dialog.wait_for(state="hidden")
        # Interact with healing fountain via spots menu & sheet action button
        page.click('.ui-world-menu[data-menu="spots"] > summary')
        page.click('.ui-world-spots a[href="#overworld-spot-meadow-npc-fountain"]')
        page.click('#overworld-spot-meadow-npc-fountain .ui-rpg-sheet-btn')
        dialog.wait_for(state="visible")
        dialog.get_by_role("button", name="💚 いやす（全回復）").click()
        self.assertIn("全回復した", dialog.inner_text())
        self.assertTrue(dialog.locator(".ui-rpg-orb").count() >= 1)
        self.assertEqual(self.errors, [])

    def test_drop_and_chest_collection_updates_bag_and_atk(self):
        page = self.open()
        # Collect ground drop 🌿 やくそう and open 🎁 はじまりの剣 chest via sheet buttons
        page.click('.ui-world-menu[data-menu="spots"] > summary')
        page.click('.ui-world-spots a[href="#overworld-spot-meadow-drop-herb"]')
        page.click('#overworld-spot-meadow-drop-herb .ui-rpg-sheet-btn')
        dialog = page.locator(".ui-rpg-card")
        dialog.wait_for(state="visible")
        self.assertIn("やくそう", dialog.inner_text())
        dialog.get_by_role("button", name="やったね！").click()
        dialog.wait_for(state="hidden")

        page.click('.ui-world-menu[data-menu="spots"] > summary')
        page.click('.ui-world-spots a[href="#overworld-spot-meadow-chest-sword"]')
        page.click('#overworld-spot-meadow-chest-sword .ui-rpg-sheet-btn')
        dialog.wait_for(state="visible")
        self.assertIn("宝箱をあけた", dialog.inner_text())
        dialog.get_by_role("button", name="やったね！").click()
        dialog.wait_for(state="hidden")

        # The sword adds four points to the shared starting attack.
        self.assertIn(f"⚔️ {W.PLAYER_BASE['atk'] + 4}", page.locator("[data-rpg-gear]").inner_text())
        self.assertEqual(page.get_attribute('.ui-spot[href="#overworld-spot-meadow-chest-sword"]', "data-rpg-opened"), "")
        self.assertIn("📭", page.inner_text('.ui-spot[href="#overworld-spot-meadow-chest-sword"]'))
        page.click('.ui-world-menu[data-menu="bag"] > summary')
        bag_text = page.locator(".ui-world-bag").inner_text()
        self.assertIn("やくそう", bag_text)
        self.assertIn("はじまりの剣", bag_text)
        self.assertEqual(self.errors, [])

    def test_turn_based_battle_orbs_skill_item_and_victory(self):
        page = self.open()
        page.click("[data-rpg-explore]")
        battle = page.locator(".ui-rpg-battle")
        battle.wait_for(state="visible")
        self.assertIn("バグスライム", battle.inner_text())
        battle.get_by_role("button", name="✨ とくぎ").click()
        battle.locator(".ui-rpg-subpanel button", has_text="バグバスター").click()
        self.assertGreaterEqual(battle.locator(".ui-rpg-orb").count(), 1)
        for _ in range(10):
            if battle.get_by_role("button", name="🏆 勝利！マップにもどる").count():
                break
            battle.get_by_role("button", name="⚔️ こうげき").click()
        battle.get_by_role("button", name="🏆 勝利！マップにもどる").click()
        battle.wait_for(state="hidden")
        # Gold and EXP increased from starting (25G, 0 EXP)
        self.assertNotEqual(page.locator("[data-rpg-gold]").inner_text(), "🪙 25G")
        self.assertFalse(page.locator("[data-rpg-exp]").inner_text().startswith("✨ 0/"))
        self.assertEqual(self.errors, [])

    def test_journal_quests_badges_and_responsive_layout(self):
        for width, height, touch in ((1280, 800, False), (390, 844, True)):
            with self.subTest(width=width):
                page = self.open(width=width, height=height, touch=touch)
                self.assertEqual(page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"), 0)
                if width == 1280:
                    # Talk to the meadow researcher
                    page.click('.ui-world-menu[data-menu="spots"] > summary')
                    page.click('.ui-world-spots a[href="#overworld-spot-meadow-npc-researcher"]')
                    page.click('#overworld-spot-meadow-npc-researcher .ui-rpg-sheet-btn')
                    dialog = page.locator(".ui-rpg-card")
                    dialog.wait_for(state="visible")
                    self.assertEqual(dialog.get_by_role("button", name="🎓 クイズに挑戦").count(), 0)
                    dialog.locator(".ui-rpg-close").click()
                    dialog.wait_for(state="hidden")
                    # Open 📜 Journal and inspect tabs
                    page.click("[data-rpg-journal-btn]")
                    journal = page.locator(".ui-rpg-journal-card")
                    journal.wait_for(state="visible")
                    self.assertIn("村の案内を聞こう", journal.inner_text())
                    journal.get_by_role("button", name="🏅 実績").click()
                    self.assertIn("はじめの挨拶", journal.inner_text())
                    journal.get_by_role("button", name="🧙 ステータス").click()
                    self.assertIn("冒険者", journal.inner_text())
                    journal.get_by_role("button", name="👾 図鑑").click()
                    self.assertIn("スパゲッティゴーレム", journal.inner_text())
                    page.keyboard.press("Escape")
                    journal.wait_for(state="hidden")
                self.assertEqual(self.errors, [])


class ReverseLondonRpgBrowserTests(unittest.TestCase):
    """Reverse London RPG, dialogue, dragon care and world relics contract in Chromium."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
        import functools
        import threading
        import shutil

        spec = importlib.util.spec_from_file_location("project_pages", ROOT / "scripts/project_pages.py")
        pages = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pages)
        cls.tmp_dir = Path(tempfile.mkdtemp(prefix="portfolio-london-"))
        pages.stage(cls.tmp_dir)

        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(cls.tmp_dir)))
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.server_url = f"http://127.0.0.1:{cls.server.server_port}"

        cls.pw = sync_playwright().start()
        cls.browser = W.launch(cls.pw)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()
        import shutil
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def test_discovery_care_and_bond_rewards_have_distinct_thresholds(self):
        import math

        dragons = W.example_data("cities")["rpg"]["dragons"]
        context = self.browser.new_context()
        self.addCleanup(context.close)
        page = context.new_page()
        page.goto(self.server_url + "/tools/#london")
        page.click('#cities-map [data-emoji="🧳"]')
        city = page.locator("#cities-map")
        dialog = city.get_by_role("dialog")

        def visit(sid):
            city.locator(f"#cities-spot-{sid} .ui-rpg-sheet-btn").dispatch_event("click")

        def check_journal(cared, mastered):
            dialog.get_by_role("button", name="またね！").click()
            city.locator("[data-rpg-journal-btn]").click()
            quest = dialog.locator("li").filter(has_text="龍とのふれあい")
            self.assertIn("1/1" if cared else "0/1", quest.inner_text())
            dialog.get_by_role("button", name="🏅 実績").click()
            for title, earned in (("龍の友愛", cared), ("龍の盟友", mastered)):
                badge = dialog.locator(".ui-rpg-badge").filter(has_text=title)
                self.assertEqual(badge.get_attribute("data-unlocked"), str(earned).lower())
            page.keyboard.press("Escape")

        first = next(iter(dragons))
        visit(first)
        check_journal(False, False)
        visit(first)
        dialog.get_by_role("button", name="🪮 ブラッシング").click()
        check_journal(True, False)
        for index, (sid, dragon) in enumerate(dragons.items()):
            visit(sid)
            remaining = dragon["bond_max"] - (6 if sid == first else 0)
            for _ in range(math.ceil(remaining / 6)):
                dialog.get_by_role("button", name="🪮 ブラッシング").click()
            check_journal(True, index + 1 == len(dragons))

    def test_reverse_london_dialogue_dragon_care_and_journal(self):
        context = self.browser.new_context(viewport={"width": 1280, "height": 800})
        self.addCleanup(context.close)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.goto(self.server_url + "/tools/#london", wait_until="networkidle")

        # 0. Pick avatar for cities
        page.click('#cities-map [data-emoji="🧳"]')
        page.wait_for_timeout(300)

        overlay = page.locator('#cities-map .ui-rpg-overlay')

        # 1. Contact Arthur & dialogue
        page.evaluate('() => document.querySelector("#cities-spot-london-rl-npc-arthur .ui-rpg-sheet-btn").click()')
        overlay.wait_for(state="visible")
        dialog = overlay.locator(".ui-rpg-card")
        self.assertIn("探偵アーサー", dialog.inner_text())
        page.click('#cities-map .ui-rpg-card [data-primary]')  # Next page
        self.assertIn("[2/4]", dialog.inner_text())
        page.click('#cities-map .ui-rpg-card button:has-text("とじる")')
        overlay.wait_for(state="hidden")

        # 2. Interact with Pythagoras Dragon and perform care actions
        page.evaluate('() => document.querySelector("#cities-spot-london-rl-dragon-pyth .ui-rpg-sheet-btn").click()')
        overlay.wait_for(state="visible")
        dialog = overlay.locator(".ui-rpg-card")
        self.assertIn("ピタゴラス龍", dialog.inner_text())
        self.assertIn("PythDRagoras", dialog.inner_text())

        # Care: brushing (+6 bond)
        page.click('#cities-map .ui-rpg-card button:has-text("ブラッシング")')
        self.assertIn("絆: 6/30", dialog.inner_text())

        # Care: resonance (+8 bond)
        page.click('#cities-map .ui-rpg-card button:has-text("共鳴・対話")')
        self.assertIn("絆: 14/30", dialog.inner_text())
        page.click('#cities-map .ui-rpg-card button:has-text("またね！")')
        overlay.wait_for(state="hidden")

        # 3. Open Journal and verify dragons tab
        page.click('#cities-map [data-rpg-journal-btn]')
        journal = page.locator("#cities-map .ui-rpg-journal-card")
        journal.wait_for(state="visible")
        dragons_tab = journal.get_by_role("button", name="🐉 竜の手帳")
        self.assertTrue(dragons_tab.is_visible())
        dragons_tab.click()
        self.assertIn("ピタゴラス龍", journal.inner_text())
        self.assertIn("未知の龍", journal.inner_text())
        page.keyboard.press("Escape")
        journal.wait_for(state="hidden")

        # 4. Header relics menu
        relics_btn = page.locator('#world-relics-btn')
        self.assertTrue(relics_btn.is_visible())
        relics_btn.click()
        self.assertTrue(page.locator('#world-relics-list').is_visible())

        self.assertEqual(errors, [])


class NagoyaRpgBrowserTests(unittest.TestCase):
    """Nagoya RPG, dialogues, deeds, fan fame gamification and world shell in Chromium."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
        import functools
        import threading
        import shutil

        spec = importlib.util.spec_from_file_location("project_pages", ROOT / "scripts/project_pages.py")
        pages = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pages)
        cls.tmp_dir = Path(tempfile.mkdtemp(prefix="portfolio-nagoya-"))
        pages.stage(cls.tmp_dir)

        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(cls.tmp_dir)))
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.server_url = f"http://127.0.0.1:{cls.server.server_port}"

        cls.pw = sync_playwright().start()
        cls.browser = W.launch(cls.pw)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()
        import shutil
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def test_nagoya_dialogues_deeds_fame_and_journal(self):
        context = self.browser.new_context(viewport={"width": 1280, "height": 800})
        self.addCleanup(context.close)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.goto(self.server_url + "/tools/#nagoya", wait_until="networkidle")

        # 0. Check world switcher recognizes nagoya
        self.assertEqual(page.locator("#world-space-name").inner_text().strip(), "🏯 聖地ナゴヤ")

        # Pick avatar for nagoya
        page.click('#nagoya-map [data-emoji="🧢"]')
        page.wait_for_timeout(300)

        overlay = page.locator('#nagoya-map .ui-rpg-overlay')

        # 1. Check HUD fame meter
        fame_btn = page.locator('#nagoya-map [data-rpg-fame-btn]')
        self.assertTrue(fame_btn.is_visible())
        self.assertIn("知名度 0pt", fame_btn.inner_text())

        # 2. Contact Ryuji & do cheer practice deed
        page.evaluate('() => document.querySelector("#nagoya-spot-nagoya-npc-ouendan .ui-rpg-sheet-btn").click()')
        overlay.wait_for(state="visible")
        dialog = overlay.locator(".ui-rpg-card")
        self.assertIn("応援団長リュウジ", dialog.inner_text())
        self.assertIn("ドラ魂", dialog.inner_text())

        # Action: cheer practice deed (+15 fame)
        help_btn = dialog.locator('[data-rpg-deed-btn]')
        self.assertTrue(help_btn.is_visible())
        help_btn.click()
        self.assertIn("知名度が 15pt 上昇した", dialog.inner_text())
        page.click('#nagoya-map .ui-rpg-card button:has-text("とじる")')
        overlay.wait_for(state="hidden")

        # Verify HUD fame updated
        self.assertIn("15pt", fame_btn.inner_text())

        # 3. Visit Vantelin Dome: Pay 30G for match ticket to cheer from stands (+25 fame)
        gold_el = page.locator('#nagoya-map [data-rpg-gold]')
        self.assertIn("125G", gold_el.inner_text())
        page.evaluate('() => document.querySelector("#nagoya-spot-nagoya-dome .ui-rpg-sheet-btn").click()')
        overlay.wait_for(state="visible")
        dome_dialog = overlay.locator(".ui-rpg-card")
        self.assertIn("バンテリンドーム ナゴヤ", dome_dialog.inner_text())
        self.assertIn("地鳴りのような大歓声", dome_dialog.inner_text())
        dome_deed_btn = dome_dialog.locator('[data-rpg-deed-btn]')
        self.assertTrue(dome_deed_btn.is_visible())
        self.assertIn("30G", dome_deed_btn.inner_text())
        self.assertIn("+25知名度", dome_deed_btn.inner_text())
        self.assertIn("観戦チケットを購入して入場する", dome_deed_btn.inner_text())
        self.assertIn("125G", gold_el.inner_text())
        dome_deed_btn.click()
        self.assertIn("観戦チケットを購入してスタンドへ入場した", dome_dialog.inner_text())
        page.click('#nagoya-map .ui-rpg-card button:has-text("とじる")')
        overlay.wait_for(state="hidden")

        # Fame is now 15 + 25 = 40pt; Gold is 125 + 40 (ticket quest) - 30 (cost) + 75 (fame*3) + 60 (fame starter quest) = 270G
        self.assertIn("40pt", fame_btn.inner_text())
        self.assertIn("270G", gold_el.inner_text())

        # 4. Visit Aeon Mall: Shop and buy cheer goods, do shopping deed (+15 fame)
        page.evaluate('() => document.querySelector("#nagoya-spot-nagoya-aeon-mall .ui-rpg-sheet-btn").click()')
        overlay.wait_for(state="visible")
        aeon_dialog = overlay.locator(".ui-rpg-card")
        self.assertIn("モール店員ナミ", aeon_dialog.inner_text())
        self.assertIn("イオンモール ナゴヤドーム前へようこそ", aeon_dialog.inner_text())

        self.assertIn("270G", gold_el.inner_text())
        self.assertEqual(aeon_dialog.locator("[data-rpg-deed-btn]").count(), 0)
        aeon_dialog.locator('button:has-text("🛒 おみせ")').click()
        shop_card = overlay.locator('.ui-rpg-card[aria-label="モール店員ナミのお店"]')
        shop_card.wait_for(state="visible")
        self.assertIn("ドーム観戦必勝弁当", shop_card.inner_text())
        self.assertIn("ナゴヤエナジースカッシュ", shop_card.inner_text())
        # Buying the drink completes the mall deed and the third-deed quest.
        shop_card.locator('.ui-rpg-row:has-text("ナゴヤエナジースカッシュ") button:has-text("かう")').click()
        page.wait_for_timeout(200)
        self.assertIn("410G", gold_el.inner_text())

        shop_card.locator('.ui-rpg-row:has-text("ナゴヤエナジースカッシュ") button:has-text("かう")').click()
        self.assertIn("395G", gold_el.inner_text())
        shop_card.get_by_role("button", name="とじる", exact=True).click()
        overlay.wait_for(state="hidden")

        # Fame is now 40 + 15 = 55pt (rank: 聖地ナゴヤの名物ファン)
        self.assertIn("55pt", fame_btn.inner_text())
        self.assertIn("395G", gold_el.inner_text())

        # 5. Open Journal and inspect Fan Fame tab & badges
        fame_btn.click()
        journal = page.locator('#nagoya-map .ui-rpg-journal-card')
        journal.wait_for(state="visible")
        self.assertIn("熱血コール＆レスポンス", journal.inner_text())
        self.assertIn("街の美化活動（ゴミ拾い）", journal.inner_text())
        self.assertIn("ドーム公式戦の現地観戦応援", journal.inner_text())
        self.assertIn("ドーム前商業施設で応援準備", journal.inner_text())

        # Inspect badges tab
        journal.locator('button:has-text("🏅 実績")').click()
        self.assertIn("熱血現地サポーター", journal.inner_text())
        self.assertIn("応援準備マスター", journal.inner_text())

        page.keyboard.press("Escape")
        journal.wait_for(state="hidden")

        # 6. Header relics menu reflects Nagoya relics
        relics_btn = page.locator('#world-relics-btn')
        self.assertTrue(relics_btn.is_visible())
        self.assertIn("/14", relics_btn.inner_text())
        relics_btn.click()
        self.assertTrue(page.locator('#world-relics-list').is_visible())

        self.assertEqual(errors, [])


class FakeParisHeroTests(unittest.TestCase):
    """Fake Paris Firefighting Hero & Gamification in Chromium."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.cities_path = Path(cls.tmp.name) / "cities.html"
        cls.cities_path.write_text(W.world_document(CITIES), encoding="utf-8")
        cls.pw = sync_playwright().start()
        cls.browser = W.launch(cls.pw)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.tmp.cleanup()

    def open(self, floor="paris", width=1280, height=800, touch=False):
        context = self.browser.new_context(viewport={"width": width, "height": height}, has_touch=touch, is_mobile=touch)
        self.addCleanup(context.close)
        page = context.new_page()
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and self.errors.append(m.text))
        page.goto(self.cities_path.as_uri())
        page.click('[data-emoji="🗼"]')
        page.wait_for_function(W.PICKED)
        # Switch to target floor via footer pulldown
        if floor:
            page.select_option(".ui-world-goto", floor)
            page.wait_for_selector(f'.ui-floor[data-floor="{floor}"]', state="visible")
        return page

    def test_paris_hud_scoped_visibility_and_captain_contact(self):
        page = self.open(floor="tokyo")
        # HUD hidden on Tokyo
        self.assertFalse(page.is_visible(".ui-rescue-hud"))
        # Switch to Paris
        page.select_option(".ui-world-goto", "paris")
        page.wait_for_selector(".ui-rescue-hud", state="visible")
        self.assertIn("見習い消防士", page.text_content("[data-rescue-hero]"))
        self.assertIn("48/48", page.text_content("[data-rescue-water]"))
        # Walk 1 step down from (24, 4) to (24, 5) to contact マルゴ隊長
        page.keyboard.press("ArrowDown")
        page.wait_for_selector(".ui-rpg-card", state="visible", timeout=6000)
        dialog = page.locator(".ui-rpg-card")
        self.assertIn("マルゴ隊長", dialog.inner_text())
        self.assertIn("[1/4]", dialog.inner_text())
        dialog.get_by_role("button", name="つぎへ ▶").click()
        self.assertIn("[2/4]", dialog.inner_text())
        dialog.locator(".ui-rpg-close").click()
        page.wait_for_selector(".ui-rpg-card", state="hidden")
        self.assertEqual(self.errors, [])

    def test_ground_drop_and_chest_and_bag_sync(self):
        page = self.open(floor="paris")
        # Collect drop-capsule via direct node click
        page.click('.ui-rescue-node[data-rescue-id="drop-capsule"]')
        page.wait_for_timeout(300)
        self.assertEqual(page.get_attribute('.ui-rescue-node[data-rescue-id="drop-capsule"]', "data-rescue-collected"), "true")
        self.assertIn("🪙 35", page.text_content("[data-rescue-medals]"))
        # Open 🎁 流体ターボノズル chest via direct click on the stage node
        page.click('.ui-rescue-node[data-rescue-id="chest-nozzle"]')
        page.wait_for_timeout(300)
        self.assertEqual(page.get_attribute('.ui-rescue-node[data-rescue-id="chest-nozzle"]', "data-rescue-opened"), "true")
        self.assertEqual(page.text_content('.ui-rescue-node[data-rescue-id="chest-nozzle"] .ui-rescue-glyph'), "📭")
        self.assertIn("🚿 13", page.text_content("[data-rescue-gear]"))
        self.assertIn("🛡️ 2", page.text_content("[data-rescue-gear]"))
        # Verify 🎒 Bag in header has both items
        page.click('.ui-world-menu[data-menu="bag"] > summary')
        bag_text = page.text_content(".ui-world-bag")
        self.assertIn("消火カプセル", bag_text)
        self.assertIn("流体ターボノズル", bag_text)
        self.assertEqual(self.errors, [])

    def test_extinguishing_fires_auto_splash_and_tactical_modal(self):
        page = self.open(floor="paris")
        # Open tactical modal by clicking fire at (20, 4)
        page.click('.ui-floor[data-floor="paris"] .ui-prop[data-kind="fire"][data-fire-id="fire-0"]')
        page.wait_for_selector(".ui-rpg-card", state="visible")
        self.assertIn("小火スパーク", page.text_content(".ui-rpg-card"))
        # Click 放水ジェット
        page.locator('.ui-rpg-card button:has-text("放水ジェット")').click()
        page.wait_for_timeout(400)
        if page.locator('.ui-rpg-card button:has-text("放水ジェット")').count() > 0:
            page.locator('.ui-rpg-card button:has-text("放水ジェット")').click()
            page.wait_for_timeout(400)
        # Victory button
        page.locator('.ui-rpg-card button:has-text("消火完了")').click()
        page.wait_for_selector(".ui-rpg-card", state="hidden")
        self.assertEqual(page.get_attribute('.ui-prop[data-fire-id="fire-0"]', "data-extinguished"), "true")
        self.assertIn("鎮火 1/25", page.text_content("[data-rescue-fires]"))
        # Open tactical modal on boss fire at (21, 31)
        page.click('.ui-floor[data-floor="paris"] .ui-prop[data-fire-tier="3"]')
        page.wait_for_selector(".ui-rpg-card", state="visible")
        self.assertIn("大火災インフェルノ", page.text_content(".ui-rpg-card"))
        page.locator('.ui-rpg-card button:has-text("退避")').click()
        page.wait_for_selector(".ui-rpg-card", state="hidden")
        self.assertEqual(self.errors, [])

    def test_restoring_village_water_preserves_earned_mission(self):
        page = self.open()
        fire = page.locator('[data-fire-id="fire-0"]')
        def restore(hidden):
            fire.evaluate("""(fire, hidden) => {
              fire.hidden = hidden;
              fire.closest('.ui-world').dispatchEvent(new Event('world-rescue-fires-changed'));
            }""", hidden)
        restore(True)
        medals = page.text_content('[data-rescue-medals]')
        restore(False)
        self.assertIn('鎮火 0/', page.text_content('[data-rescue-fires]'))
        page.click('[data-rescue-journal-btn]')
        row = page.locator('.ui-rpg-row').filter(has_text='初めての消火活動')
        self.assertIn('✅', row.inner_text())
        self.assertIn('1/1', row.inner_text())
        restore(True)
        self.assertEqual(page.text_content('[data-rescue-medals]'), medals)
        self.assertEqual(self.errors, [])

    def test_every_guide_fire_can_be_extinguished(self):
        graph = json.loads((ROOT / "docs/world-guide.json").read_text(encoding="utf-8"))
        fires = [n for n in graph["nodes"] if "heat" in n]
        page = self.open()
        data = CITIES["rescue"]
        def visit(uid):
            page.locator(f'[data-rescue-id="{uid}"]').dispatch_event("click")

        captain = next(q["target"] for q in data["quests"] if q["kind"] == "talk")
        visit(captain)
        page.locator(".ui-rpg-close").click()
        visit(next(n["id"] for n in data["nodes"] if n["kind"] == "drop"))
        hydrant = next(n["id"] for n in data["nodes"] if n["kind"] == "hydrant")
        chests = [n for n in data["nodes"] if n["kind"] == "chest"]
        for i, fire in enumerate(fires):
            for n in chests:
                visit(n["id"])
                opened = page.locator(f'[data-rescue-id="{n["id"]}"]').get_attribute("data-rescue-opened")
                self.assertEqual(opened == "true", i >= n.get("requires_fires", 0))
            visit(hydrant)
            marker = page.locator(f'[data-fire-id="{fire["id"].split("/")[-1]}"]')
            marker.dispatch_event("click")
            card = page.locator(".ui-rpg-card")
            self.assertIn(f'{fire["heat"]}/{fire["heat"]}', card.inner_text())
            for _ in range(fire["heat"]):
                card.get_by_role("button", name="放水ジェット", exact=False).click()
                if marker.get_attribute("data-extinguished") == "true":
                    break
            card.get_by_role("button", name="消火完了", exact=False).click()
        self.assertIn(f"{len(fires)}/{len(fires)}", page.text_content("[data-rescue-fires]"))
        page.click("[data-rescue-journal-btn]")
        self.assertEqual(page.locator(".ui-rpg-card").inner_text().count("✅"), len(data["quests"]))
        page.get_by_role("button", name="🏅 勲章バッジ").click()
        self.assertEqual(page.locator('.ui-rpg-badge[data-unlocked="true"]').count(), len(data["badges"]))
        self.assertEqual(self.errors, [])

    def test_cooling_gel_is_reserved_for_a_fire(self):
        page = self.open()
        page.locator('[data-rescue-id="drop-cryo"]').dispatch_event("click")
        page.click("[data-rescue-journal-btn]")
        page.locator(".ui-rpg-card").get_by_role("button", name="どうぐ", exact=False).click()
        self.assertTrue(page.get_by_role("button", name="火災現場専用").is_disabled())
        page.locator(".ui-rpg-card .ui-rpg-close").click()
        page.locator('[data-fire-id="fire-0"]').dispatch_event("click")
        page.get_by_role("button", name="🎒 どうぐを使う").click()
        page.locator(".ui-rpg-card").get_by_role("button", name="瞬間冷却ジェル弾", exact=False).click()
        self.assertEqual(page.locator('[data-fire-id="fire-0"]').get_attribute("data-extinguished"), "true")
        self.assertNotIn("瞬間冷却ジェル弾", page.locator(".ui-world-bag").text_content())
        self.assertEqual(self.errors, [])

    def test_shop_and_quiz_and_journal_tabs(self):
        page = self.open(floor="paris")
        # Open baker NPC dialogue via node click
        page.click('.ui-rescue-node[data-rescue-id="npc-baker"]')
        page.wait_for_selector(".ui-rpg-card", state="visible")
        self.assertIn("パン職人コレット", page.text_content(".ui-rpg-card"))
        page.locator('.ui-rpg-card button:has-text("補給ショップ")').click()
        page.wait_for_selector(".ui-rpg-card:has-text('補給ショップ')", state="visible")
        page.locator('.ui-rpg-card button:has-text("補給する")').first.click()
        page.wait_for_timeout(300)
        self.assertIn("🪙 10", page.text_content("[data-rescue-medals]"))
        page.locator('.ui-rpg-card button:has-text("会話にもどる")').click()
        page.wait_for_selector(".ui-rpg-card:has-text('パン職人コレット')", state="visible")
        page.locator(".ui-rpg-card .ui-rpg-close").click()
        page.wait_for_selector(".ui-rpg-card", state="hidden")
        # Open archivist NPC dialogue & quiz
        page.click('.ui-rescue-node[data-rescue-id="npc-archivist"]')
        page.wait_for_selector(".ui-rpg-card", state="visible")
        self.assertIn("記録官ルネ", page.locator(".ui-rpg-card").inner_text())
        page.locator(".ui-rpg-card .ui-rpg-close").click()
        page.wait_for_selector(".ui-rpg-card", state="hidden")
        # Open 📋 Hero Journal
        page.click("[data-rescue-journal-btn]")
        page.wait_for_selector(".ui-rpg-journal-card", state="visible")
        self.assertIn("消防ヒーロー手帳", page.text_content(".ui-rpg-journal-card"))
        page.locator('.ui-rpg-journal-card button:has-text("勲章バッジ")').click()
        self.assertIn("初動消火", page.text_content(".ui-rpg-journal-card"))
        page.locator('.ui-rpg-journal-card button:has-text("パリ緑化")').click()
        page.wait_for_timeout(200)
        self.assertTrue(page.locator(".ui-rescue-cell").count() == 64)
        page.locator(".ui-rpg-journal-card .ui-rpg-close").click()
        page.wait_for_selector(".ui-rpg-journal-card", state="hidden")
        self.assertEqual(self.errors, [])


class OsakaDetectiveBrowserTests(unittest.TestCase):
    """Seyakate Osaka Great Detective Investigation & Gamification in Chromium."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.cities_path = Path(cls.tmp.name) / "cities.html"
        cls.cities_path.write_text(W.world_document(CITIES), encoding="utf-8")
        cls.pw = sync_playwright().start()
        cls.browser = W.launch(cls.pw)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.tmp.cleanup()

    def open(self, floor="osaka", width=1280, height=800, touch=False, path=None):
        context = self.browser.new_context(viewport={"width": width, "height": height}, has_touch=touch, is_mobile=touch)
        self.addCleanup(context.close)
        page = context.new_page()
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and self.errors.append(m.text))
        page.goto((path or self.cities_path).as_uri())
        page.click('[data-emoji="🗼"]')
        page.wait_for_function(W.PICKED)
        if floor:
            page.select_option(".ui-world-goto", floor)
            page.wait_for_selector(f'.ui-floor[data-floor="{floor}"]', state="visible")
        return page

    def test_osaka_hud_scoped_visibility_and_heita_contact(self):
        page = self.open(floor="tokyo")
        # HUD hidden on Tokyo
        self.assertFalse(page.is_visible(".ui-detective-hud"))
        # Switch to Osaka
        page.select_option(".ui-world-goto", "osaka")
        page.wait_for_selector(".ui-detective-hud", state="visible")
        self.assertIn("見習い浪速調査員", page.text_content("[data-detective-hero]"))
        self.assertIn("48/48", page.text_content("[data-detective-stamina]"))
        # Walk one tile south from Osaka Station to contact 熱血探偵ヘイタ
        page.keyboard.press("ArrowDown")
        page.wait_for_selector(".ui-rpg-card", state="visible", timeout=6000)
        dialog = page.locator(".ui-rpg-card")
        self.assertIn("熱血探偵ヘイタ", dialog.inner_text())
        self.assertIn("[1/4]", dialog.inner_text())
        dialog.get_by_role("button", name="つぎへ ▶").click()
        self.assertIn("[2/4]", dialog.inner_text())
        dialog.locator(".ui-rpg-close").click()
        page.wait_for_selector(".ui-rpg-card", state="hidden")
        self.assertEqual(self.errors, [])

    def test_npcs_can_talk_when_no_quizzes_are_configured(self):
        spec = W.example_data("cities")
        for game in ("rescue", "detective"):
            spec[game]["quizzes"] = []
            next(n for n in spec[game]["nodes"] if n["id"] == "npc-archivist")["quiz"] = True
        path = Path(self.tmp.name) / "without-quizzes.html"
        path.write_text(W.world_document(spec), encoding="utf-8")
        page = self.open(path=path)
        for game in ("detective", "rescue"):
            data = spec[game]
            page.select_option(".ui-world-goto", data["floor"])
            npc = next(n for n in data["nodes"] if n.get("quiz"))
            page.locator(f'[data-{game}-id="{npc["id"]}"]').dispatch_event("click")
            card = page.locator(".ui-rpg-card")
            self.assertIn(npc["greeting"], card.inner_text())
            self.assertEqual(card.locator('button').filter(has_text="クイズ").count(), 0)
            card.locator(".ui-rpg-close").click()
        self.assertEqual(self.errors, [])

    def test_osaka_chief_briefs_the_player_at_osaka_station(self):
        page = self.open()
        page.get_by_role("button", name="👮 浪速署長", exact=True).click()
        dialog = page.get_by_role("dialog", name="浪速署長との対話")
        self.assertIn("ヘイタ", dialog.inner_text())
        self.assertEqual(self.errors, [])

    def test_compass_walks_past_contacts_and_checks_stamina_at_arrival(self):
        data = CITIES["detective"]
        cost = data["walk_cost"]
        tactic = next(t for t in data["tactics"] if t["kind"] == "logic_burst")
        for available in (cost, cost - 1):
            with self.subTest(available=available):
                spec = copy.deepcopy(CITIES)
                maximum = available + tactic["stamina"]
                spec["detective"]["hero"]["stamina"] = maximum
                # Keep first-clue rewards from refilling stamina via a rank-up.
                spec["detective"]["quests"] = []
                path = Path(self.tmp.name) / f"walk-{available}.html"
                path.write_text(W.world_document(spec), encoding="utf-8")
                page = self.open(path=path)
                page.locator('[data-shadow-boss="true"]').dispatch_event("click")
                page.locator(".ui-rpg-card").get_by_role("button", name=tactic["label"], exact=False).click()
                page.get_by_role("button", name="💨 一旦退避").click()
                self.assertEqual(page.text_content("[data-detective-stamina]"), f"⚡ {available}/{maximum}")
                self.assertIn("マス", page.text_content("[data-detective-radar]"))
                page.click("[data-detective-radar-btn]")
                if available == cost:
                    page.wait_for_selector('[data-shadow-tier="1"][data-cleared="true"]', timeout=5000)
                    self.assertIn("解決 1/", page.text_content("[data-detective-clues]"))
                    self.assertEqual(page.text_content("[data-detective-stamina]"), f"⚡ 0/{maximum}")
                    self.assertFalse(page.locator(".ui-rpg-card").is_visible())
                else:
                    page.get_by_role("dialog", name="街角の不審な痕跡現場検証").wait_for(timeout=5000)
                    self.assertIn("解決 0/", page.text_content("[data-detective-clues]"))
                    self.assertEqual(page.text_content("[data-detective-stamina]"), f"⚡ {available}/{maximum}")
                self.assertEqual(self.errors, [])

    def test_last_shop_portion_leaves_both_journal_and_bag(self):
        page = self.open()
        data = CITIES["detective"]
        food = next(item for item in data["shop"] if item["item_type"] == "heal")
        vendor = next(node for node in data["nodes"] if node.get("shop"))
        page.locator(f'[data-detective-id="{vendor["id"]}"]').click()
        page.get_by_role("button", name="🛒 船場どうぐ屋").click()
        row = page.locator(".ui-rpg-card .ui-rpg-row").filter(has_text=food["label"])
        buy = row.get_by_role("button")
        buy.click()
        buy.click()
        self.assertTrue(buy.is_disabled())
        page.locator(".ui-rpg-card .ui-rpg-close").click()
        page.click("[data-detective-journal-btn]")
        page.get_by_role("button", name="🕵️‍♂️ 装備・どうぐ").click()
        portion = page.locator(".ui-rpg-card .ui-rpg-row").filter(has_text=food["label"])
        bag = page.locator(".ui-world-bag li").filter(has_text=food["label"])
        for remaining in (2, 1):
            self.assertIn(f"×{remaining}", portion.inner_text())
            self.assertEqual(bag.count(), 1)
            portion.get_by_role("button", name="つかう").click()
        self.assertEqual(portion.count(), 0)
        self.assertEqual(bag.count(), 0)
        self.assertEqual(self.errors, [])

    def test_guide_conditions_in_a_complete_investigation(self):
        guide = json.loads((ROOT / "docs/osaka-guide.json").read_text(encoding="utf-8"))
        nodes = {n["id"]: n for n in guide["nodes"]}
        cases = [n for n in nodes.values() if n.get("section") == "現場一覧"]
        hat_guard, = [nodes[e["target"]] for e in guide["edges"]
                      if e["source"] == "task/chest-hat" and e["kind"] == "guarded_by"]
        data = CITIES["detective"]
        page = self.open()
        def visit(uid):
            page.locator(f'[data-detective-id="{uid}"]').dispatch_event("click")

        def close():
            page.locator(".ui-rpg-card .ui-rpg-close").click()

        visit("npc-trail-dog")
        self.assertIn("西の喫茶店", page.text_content(".ui-rpg-card"))
        close()
        visit("npc-ayaka")
        close()
        self.assertIn("0/", page.text_content("[data-detective-qcount]"))
        visit("npc-heita")
        close()
        self.assertIn("1/", page.text_content("[data-detective-qcount]"))
        for item in data["nodes"]:
            if item["kind"] == "drop":
                visit(item["id"])
        page.click("[data-detective-journal-btn]")
        page.get_by_role("button", name="🕵️‍♂️ 装備・どうぐ").click()
        self.assertTrue(page.get_by_role("button", name="現場専用").is_disabled())
        for item in data["nodes"]:
            if item["kind"] == "drop" and item["usage"] == "equipment":
                row = page.locator(".ui-rpg-card .ui-rpg-row").filter(has_text=item["item_label"])
                self.assertEqual(row.count(), 1)
                self.assertEqual(row.locator("button").count(), 0)
        close()
        for index, case in enumerate(cases):
            visit("chest-hat")
            opened = page.locator('[data-detective-id="chest-hat"]').get_attribute("data-detective-opened")
            self.assertEqual(opened == "true", index >= hat_guard["minimum"])
            visit("stand-umeda")
            sid = case["id"].removeprefix("task/")
            shadow = page.locator(f'[data-shadow-id="{sid}"]')
            shadow.dispatch_event("click")
            inspect = page.get_by_role("button", name="🔍 現場検証", exact=False)
            initial_rank = page.text_content("[data-detective-hero]")
            stamina = lambda: int(page.text_content("[data-detective-stamina]").split()[1].split("/")[0])
            initial_stamina = stamina()
            if index == 0:
                page.locator(".ui-rpg-card").get_by_role("button", name="🧪 鑑識試験紙", exact=False).click()
            used = 0
            while shadow.get_attribute("data-cleared") != "true" and used < initial_stamina:
                inspect.click()
                used += next(t["stamina"] for t in data["tactics"] if t["kind"] == "inspect")
            self.assertEqual(shadow.get_attribute("data-cleared"), "true", sid)
            if initial_rank == page.text_content("[data-detective-hero]"):
                self.assertEqual(stamina(), initial_stamina-used, sid)
        self.assertIn(f"{len(cases)}/{len(cases)}", page.text_content("[data-detective-clues]"))
        for item in data["nodes"]:
            if item["kind"] == "chest":
                visit(item["id"])
        visit("npc-chief")
        close()
        visit(next(n["id"] for n in data["nodes"] if n.get("quiz")))
        page.get_by_role("button", name="📝 証言を照合する").click()
        for quiz in data["quizzes"]:
            page.get_by_role("button", name=f'{quiz["correct"]+1}. {quiz["choices"][quiz["correct"]]}').click()
            page.get_by_role("button", name="もう一度照合").click()
        close()
        page.click("[data-detective-journal-btn]")
        self.assertEqual(page.locator(".ui-rpg-card").inner_text().count("✅"), len(data["quests"]))
        page.get_by_role("button", name="🏅 探偵バッジ").click()
        self.assertEqual(page.locator(".ui-rpg-card").inner_text().count("獲得済み"), len(data["badges"]))
        self.assertEqual(self.errors, [])

    def test_ground_drop_and_chest_and_bag_sync(self):
        page = self.open(floor="osaka")
        # Collect drop-takoyaki via direct node click
        page.click('.ui-detective-node[data-detective-id="drop-takoyaki"]')
        page.wait_for_timeout(300)
        self.assertEqual(page.get_attribute('.ui-detective-node[data-detective-id="drop-takoyaki"]', "data-detective-collected"), "true")
        self.assertIn("🪙 35", page.text_content("[data-detective-medals]"))
        # Open 🎁 浪速の調査靴 chest via direct click on the stage node
        page.click('.ui-detective-node[data-detective-id="chest-shoes"]')
        page.wait_for_timeout(300)
        self.assertEqual(page.get_attribute('.ui-detective-node[data-detective-id="chest-shoes"]', "data-detective-opened"), "true")
        self.assertEqual(page.text_content('.ui-detective-node[data-detective-id="chest-shoes"] .ui-detective-glyph'), "📭")
        self.assertIn("かしこさ 16", page.text_content("[data-detective-gear]"))
        # Verify 🎒 Bag in header has both items
        page.click('.ui-world-menu[data-menu="bag"] > summary')
        bag_text = page.text_content(".ui-world-bag")
        self.assertIn("アツアツたこ焼き", bag_text)
        self.assertIn("浪速の調査靴", bag_text)
        self.assertEqual(self.errors, [])

    def test_solving_shadows_auto_unravel_and_tactical_modal(self):
        page = self.open(floor="osaka")
        # Open tactical modal by clicking shadow prop
        first_shadow = page.locator('.ui-floor[data-floor="osaka"] .ui-prop[data-kind="shadow"]').first
        first_shadow.click()
        page.wait_for_selector(".ui-rpg-card", state="visible")
        self.assertIn("現場検証", page.text_content(".ui-rpg-card"))
        # Click 現場検証 tactic button
        page.locator('.ui-rpg-card button:has-text("現場検証")').click()
        page.wait_for_timeout(400)
        if page.locator('.ui-rpg-card button:has-text("現場検証")').count() > 0:
            page.locator('.ui-rpg-card button:has-text("現場検証")').click()
            page.wait_for_timeout(400)
        # Victory close
        if page.locator('.ui-rpg-card button:has-text("解決完了")').count() > 0:
            page.locator('.ui-rpg-card button:has-text("解決完了")').click()
        elif page.locator(".ui-rpg-card .ui-rpg-close").count() > 0:
            page.locator(".ui-rpg-card .ui-rpg-close").click()
        page.wait_for_selector(".ui-rpg-card", state="hidden")
        self.assertIn("解決", page.text_content("[data-detective-clues]"))
        # Open tactical modal on boss shadow
        boss = page.locator('.ui-floor[data-floor="osaka"] .ui-prop[data-shadow-boss="true"]')
        if boss.count() > 0:
            boss.first.click()
            page.wait_for_selector(".ui-rpg-card", state="visible")
            self.assertIn("怪盗黒幕シャドウ", page.text_content(".ui-rpg-card"))
            page.locator('.ui-rpg-card button:has-text("退避")').click()
            page.wait_for_selector(".ui-rpg-card", state="hidden")
        self.assertEqual(self.errors, [])

    def test_shop_and_quiz_and_journal_tabs(self):
        page = self.open(floor="osaka")
        # Open shop NPC dialogue via node click
        page.click('.ui-detective-node[data-detective-id="npc-semba"]')
        page.wait_for_selector(".ui-rpg-card", state="visible")
        self.assertIn("船場情報屋センバ", page.text_content(".ui-rpg-card"))
        page.locator('.ui-rpg-card button:has-text("船場どうぐ屋")').click()
        page.wait_for_selector(".ui-rpg-card:has-text('船場どうぐ屋')", state="visible")
        page.locator('.ui-rpg-card button:has-text("購入")').first.click()
        page.wait_for_timeout(300)
        self.assertIn("🪙 10", page.text_content("[data-detective-medals]"))
        page.locator('.ui-rpg-card button:has-text("会話にもどる")').click()
        page.wait_for_selector(".ui-rpg-card:has-text('船場情報屋センバ')", state="visible")
        page.locator(".ui-rpg-card .ui-rpg-close").click()
        page.wait_for_selector(".ui-rpg-card", state="hidden")
        # Open archivist NPC dialogue & quiz
        page.click('.ui-detective-node[data-detective-id="npc-archivist"]')
        page.wait_for_selector(".ui-rpg-card", state="visible")
        self.assertIn("暗号解読士", page.text_content(".ui-rpg-card"))
        page.get_by_role("button", name="📝 証言を照合する").click()
        self.assertEqual(page.get_by_role("dialog", name="証言照合").count(), 0)
        page.locator(".ui-rpg-card .ui-rpg-close").click()
        page.locator('[data-detective-id="npc-chief"]').dispatch_event("click")
        page.locator(".ui-rpg-card .ui-rpg-close").click()
        page.locator('[data-detective-id="npc-archivist"]').dispatch_event("click")
        page.get_by_role("button", name="📝 証言を照合する").click()
        page.get_by_role("button", name="2. 目撃通報は梅田だった").click()
        self.assertIn("正解！", page.text_content(".ui-rpg-card"))
        page.locator(".ui-rpg-card .ui-rpg-close").click()
        page.wait_for_selector(".ui-rpg-card", state="hidden")
        # Open 📋 Detective Journal
        page.click("[data-detective-journal-btn]")
        page.wait_for_selector(".ui-rpg-card", state="visible")
        self.assertIn("浪速探偵手帳", page.text_content(".ui-rpg-card"))
        page.locator('.ui-rpg-card button:has-text("探偵バッジ")').click()
        self.assertIn("初動解決", page.text_content(".ui-rpg-card"))
        page.locator('.ui-rpg-card button:has-text("浪速緑化")').click()
        page.wait_for_timeout(200)
        self.assertTrue(page.locator(".ui-detective-cell").count() == 64)
        page.locator(".ui-rpg-card .ui-rpg-close").click()
        page.wait_for_selector(".ui-rpg-card", state="hidden")
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main()
