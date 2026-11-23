"""🧬 The front page in a real browser: catalog, search and topics, display modes, colour themes, AI highlights, brand.

The page is built by scripts/front_page.py; its catalog rules and notations are checked without a browser in
tests/test_site.py. These tests drive Chromium (Python Playwright, the ``browser`` dependency group) against the staged
site, the source tree plus the generated files, exactly as Pages serves it.
"""

import functools
import importlib.util
import json
import re
import shutil
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect

ROOT = Path(__file__).resolve().parents[1]
MODES = ("modern", "github-like", "xml-like", "json", "markdown")
PROFILE = json.loads((ROOT / "profile.json").read_text(encoding="utf-8"))
CURATED = json.loads((ROOT / "projects.json").read_text(encoding="utf-8"))
ACTIVE = [repo for repo in json.loads((ROOT / "api/repos.json").read_text(encoding="utf-8"))["repos"] if not repo.get("archived")]
# 🐙 every repository · 🌐 its Pages (api/repos.json) · 📄 its portfolio page (a projects.json showcase)
LINKED = sorted({repo["url"] for repo in ACTIVE} | {repo["pages"] for repo in ACTIVE if repo.get("pages")}
                | {f"https://myon-bioinformatics.github.io/tools/projects/{project['name'].lower()}.html"
                   for project in json.loads((ROOT / "projects.json").read_text(encoding="utf-8"))
                   if "showcase" in project and project["name"] in {repo["name"] for repo in ACTIVE}})
COUNT = len(ACTIVE)                                     # only public, non-archived repositories are displayed
SHOWING_ALL = f"Showing all {COUNT} projects"
ONE_OF = f"Showing 1 of {COUNT} projects"
NO_MATCH = "No matching projects found."


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def site():
    """The staged site on a local port: (directory, origin)."""
    spec = importlib.util.spec_from_file_location("project_pages", ROOT / "scripts/project_pages.py")
    pages = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pages)
    directory = Path(tempfile.mkdtemp(prefix="portfolio-front-"))
    pages.stage(directory)
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(directory)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield directory, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as playwright:
        chromium = playwright.chromium.launch(channel="chromium")      # a missing browser fails here: these tests never skip quietly
        try:
            yield chromium
        finally:
            chromium.close()


def _png(width, height, rgb):
    """A solid-colour PNG (stdlib only) for the GIF tests."""
    import struct
    import zlib
    chunk = lambda kind, data: struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    rows = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


# ═══ 🎞 GIF工房 and 🎥 moving samples (PySaiyanWeBoo gif.js) ═══════════════════════════════════════════════════

def test_gif_workshop_turns_picked_images_into_one_gif(page, tmp_path):
    (tmp_path / "red.png").write_bytes(_png(64, 48, (229, 57, 53)))
    (tmp_path / "blue.png").write_bytes(_png(48, 64, (30, 136, 229)))
    requests = []
    page.on("request", lambda request: requests.append(request.url))
    page.goto("/tools/gif/")
    page.set_input_files("#gif-files", [str(tmp_path / "red.png"), str(tmp_path / "blue.png")])
    page.check("#gif-names")
    page.click("#gif-make")
    expect(page.locator("#gif-status")).to_contain_text("✅ 2枚")
    assert page.locator("#gif-save").get_attribute("href").startswith("blob:")
    head = page.evaluate("async () => [...new Uint8Array(await (await fetch(document.getElementById('gif-preview').src)).arrayBuffer()).slice(0, 6)]")
    assert bytes(head) == b"GIF89a"
    assert all(url.startswith(page.url.split("/tools/")[0]) or url.startswith("blob:") for url in requests)   # nothing leaves the site


def test_moving_sample_is_recorded_for_a_pages_url(site, browser, tmp_path):
    spec = importlib.util.spec_from_file_location("project_pages_samples", ROOT / "scripts/project_pages.py")
    pages = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pages)
    lines = pages.record_samples(tmp_path, {"Portfolio": site[1] + "/index.html", "Gone": site[1] + "/no-such-page/"}, browser=browser)
    gif = (tmp_path / "media/pages/portfolio.gif").read_bytes()
    assert gif[:6] == b"GIF89a" and lines[0].startswith("🎥 Portfolio: 2 frames")
    assert lines[1] == "⏸ Gone: RuntimeError: HTTP 404"                                   # an error page is not a sample
    assert pages.recorded_samples(tmp_path) == {"portfolio"}


def write_config(site, mode):
    site[0].joinpath("site.config.json").write_text(json.dumps({"defaultViewMode": mode}), encoding="utf-8")


@pytest.fixture
def page(site, browser):
    """A fresh visitor (empty localStorage) with the default config; third-party hosts are answered locally."""
    write_config(site, "modern")
    context = browser.new_context(base_url=site[1])
    tab = context.new_page()
    tab.route("https://img.shields.io/**", lambda route: route.fulfill(
        status=200, content_type="image/svg+xml", path=str(ROOT / "tests/fixtures/github-stars.svg")))
    tab.route("https://api.github.com/**", lambda route: route.fulfill(status=503, body="{}"))
    try:
        yield tab
    finally:
        context.close()
        write_config(site, "modern")


def open_front(page, site, config_mode="modern"):
    write_config(site, config_mode)
    page.goto("/")
    page.wait_for_load_state("networkidle")
    return page.locator("body").get_attribute("data-view-mode")


def select_mode(page, mode):
    page.select_option("#view-mode-select", mode)
    expect(page.locator("body")).to_have_attribute("data-view-mode", mode)


def count(page):
    return page.locator("#projects-count")


CARDS = "#projects-render-root .ui-card"


# ═══ 🧭 catalog: every active repository, in every display mode ═════════════════════════════════════════════════

def test_every_active_repository_is_reachable_in_every_display_mode(page):
    page.goto("/")
    for mode in MODES:
        page.select_option("#view-mode-select", mode)
        expect(count(page)).to_have_text(SHOWING_ALL)
        urls = page.locator("#projects-render-root a").evaluate_all(
            "links => [...new Set(links.map(link => link.getAttribute('href')))].sort()")
        assert urls == LINKED, mode


def test_only_active_repositories_are_displayed_and_curated_descriptions_survive(page):
    page.goto("/")
    expect(page.locator(CARDS)).to_have_count(COUNT)
    assert set(page.locator(CARDS + " h3").all_text_contents()) == {repo["name"] for repo in ACTIVE}
    expect(page.locator("#projects-render-root .project-status")).to_have_count(0)
    names = {repo["name"] for repo in ACTIVE}
    sample = next(project for project in CURATED if project["name"] in names)
    card = page.locator(CARDS).filter(has=page.get_by_role("link", name=sample["name"], exact=True))
    expect(card).to_contain_text(sample["desc"])


def test_topic_and_search_combine_and_survive_mode_changes(page):
    page.goto("/")
    page.locator(".project-topic-controls summary").click()
    page.locator('#project-tags-filter button[data-tag="nvd"]').click()
    page.locator("#project-search-input").fill("NVD_NIST")
    for mode in MODES:
        page.select_option("#view-mode-select", mode)
        expect(count(page)).to_have_text(ONE_OF)
        expect(page.locator("#projects-render-root")).to_contain_text("nvd_nist_known_vulns")
    page.locator("#project-search-input").fill("no-such-project-term")
    expect(count(page)).to_have_text(NO_MATCH)


def test_search_typed_while_the_page_starts_is_respected(page):
    # The page script waits for site.config.json before its first render; hold it so the search is typed first.
    held = []
    page.route("**/site.config.json", lambda route: held.append(route))
    page.goto("/")
    page.locator("#project-search-input").fill("nvd_nist")
    expect(page.locator("#profile-render-root")).to_be_empty()
    held[0].fulfill(json={"defaultViewMode": "modern"})
    expect(count(page)).to_have_text(ONE_OF)
    expect(page.locator("#projects-render-root")).to_contain_text("nvd_nist_known_vulns")
    expect(page.locator("#project-search-clear")).to_be_visible()


def test_the_full_catalog_and_expanded_topics_fit_a_phone(page):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto("/")
    page.locator(".project-topic-controls summary").click()
    for mode in MODES:
        page.select_option("#view-mode-select", mode)
        expect(count(page)).to_have_text(SHOWING_ALL)
        assert page.evaluate("document.documentElement.scrollWidth") <= 390, mode


def test_the_shared_collection_filter_is_loaded_before_projects_render(page):
    page.goto("/")
    names = page.evaluate("""() => window.WebUICollections.filterItems([
        { name: 'Aoi', topics: ['python'], archived: false },
        { name: 'Legacy', topics: ['python'], archived: true },
        { name: 'Other', topics: ['javascript'], archived: false },
      ], { query: 'PYTHON', text: item => [item.name, ...(item.topics || [])],
           facets: { archived: false, topic: 'python' }, facetValues: { topic: item => item.topics } }).map(item => item.name)""")
    assert names == ["Aoi"]


# ═══ 🏷️ search and topic filter ════════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def filters(page):
    page.goto("/")
    page.wait_for_load_state("networkidle")
    page.locator(".project-topic-controls summary").click()
    return page


def test_search_input_topic_buttons_and_count_are_shown(filters):
    expect(filters.locator("#project-search-input")).to_be_visible()
    expect(filters.locator("#project-tags-filter")).to_be_visible()
    expect(count(filters)).to_have_text(SHOWING_ALL)
    expect(filters.locator(CARDS)).to_have_count(COUNT)


def test_a_topic_button_filters_and_all_restores(filters):
    button = filters.locator('#project-tags-filter button[data-tag="nvd"]')
    button.click()
    expect(button).to_have_class(re.compile("active"))
    expect(count(filters)).to_have_text(ONE_OF)
    expect(filters.locator(CARDS)).to_have_count(1)
    expect(filters.locator(CARDS + " h3")).to_contain_text("nvd_nist_known_vulns")
    filters.locator('#project-tags-filter button[data-tag="all"]').click()
    expect(count(filters)).to_have_text(SHOWING_ALL)
    expect(filters.locator(CARDS)).to_have_count(COUNT)


def test_search_filters_and_the_clear_button_restores(filters):
    clear = filters.locator("#project-search-clear")
    filters.locator("#project-search-input").fill("nvd_nist")
    expect(clear).to_be_visible()
    expect(count(filters)).to_have_text(ONE_OF)
    expect(filters.locator(CARDS)).to_have_count(1)
    expect(filters.locator(CARDS + " h3")).to_contain_text("nvd_nist_known_vulns")
    clear.click()
    expect(clear).to_be_hidden()
    expect(count(filters)).to_have_text(SHOWING_ALL)
    expect(filters.locator(CARDS)).to_have_count(COUNT)


def test_no_match_shows_the_empty_state(filters):
    filters.locator("#project-search-input").fill("nonexistentterm12345")
    expect(count(filters)).to_have_text(NO_MATCH)
    expect(filters.locator(".empty-projects-msg")).to_be_visible()
    expect(filters.locator(".empty-projects-msg")).to_have_text("No projects match your filter.")


def test_a_topic_tag_on_a_card_filters_projects(filters):
    badge = filters.locator(".project-topics .ui-tag[data-topic]").first
    topic = badge.get_attribute("data-topic")
    curated = {project["name"]: project.get("topics") or [] for project in CURATED}
    expected = sorted(repo["name"] for repo in ACTIVE if topic in [*(repo.get("topics") or []), *curated.get(repo["name"], [])])
    assert expected
    badge.click()
    # Rendering after the card click collapses the controls; inspect their state even when hidden.
    expect(filters.locator(f"#project-tags-filter button[data-tag={json.dumps(topic)}]")).to_have_attribute("aria-pressed", "true")
    expect(count(filters)).to_have_text(SHOWING_ALL if len(expected) == COUNT else f"Showing {len(expected)} of {COUNT} projects")
    titles = filters.locator(CARDS + " h3")
    expect(titles).to_have_count(len(expected))
    assert sorted(titles.all_text_contents()) == expected


def test_copy_url_copies_and_says_so(filters):
    filters.context.grant_permissions(["clipboard-read", "clipboard-write"])
    button = filters.locator("#projects-render-root .project-copy").first
    button.click()
    expect(button).to_have_text("Copied!")
    expect(button).to_have_class(re.compile("copied"))


def test_combined_search_and_topic_persist_through_every_display_mode(filters):
    nvd = filters.locator('#project-tags-filter button[data-tag="nvd"]')
    nvd.click()
    filters.locator("#project-search-input").fill("SCAPY")
    expect(count(filters)).to_have_text(NO_MATCH)
    for mode in MODES:
        filters.select_option("#view-mode-select", mode)
        expect(count(filters)).to_have_text(NO_MATCH)
        filters.locator("#project-search-clear").click()
        expect(count(filters)).to_have_text(ONE_OF)
        expect(nvd).to_have_attribute("aria-pressed", "true")
        filters.locator("#project-search-input").fill("SCAPY")
    filters.locator('#project-tags-filter button[data-tag="all"]').click()
    expect(count(filters)).to_have_text(NO_MATCH)


# ═══ 🎨 shared UI and colour themes ════════════════════════════════════════════════════════════════════════════

def test_cards_and_controls_use_the_pinned_shared_ui(page):
    page.goto("/")
    expect(page.locator(CARDS).first).to_be_visible()
    for asset in ("tokens.css", "base.css", "components.css", "themes/modern.css"):
        sheet = page.locator(f'link[href="./tools/vendor/web-ui/css/{asset}"]')
        expect(sheet).to_have_count(1)
        assert sheet.evaluate("link => !!link.sheet") is True, asset
    expect(page.locator("body")).to_have_attribute("data-ui-theme", "modern")
    page.evaluate("document.body.style.setProperty('--ui-border', 'rgb(1, 2, 3)')")
    for selector in (CARDS, "#project-search-input", "#projects-render-root .project-copy"):
        expect(page.locator(selector).first).to_have_css("border-top-color", "rgb(1, 2, 3)")
    for mode in ("github-like", "xml-like", "json", "markdown", "modern"):
        page.select_option("#view-mode-select", mode)
        expect(page.locator("body")).to_have_attribute("data-ui-theme", mode if mode in ("modern", "github-like") else "plain")
    page.set_viewport_size({"width": 390, "height": 844})
    for selector in ("#project-search-input", "#projects-render-root .project-copy"):
        assert page.locator(selector).first.bounding_box()["height"] >= 44, selector


def test_a_colour_theme_recolours_every_display_mode_and_is_remembered(page, site):
    open_front(page, site)
    background = lambda: page.evaluate("getComputedStyle(document.body).backgroundColor")
    seen = {background()}
    for theme in ("purple", "green", "terminal"):
        page.select_option("#theme-select", theme)
        for mode in MODES:
            select_mode(page, mode)
            expect(page.locator("body")).to_have_attribute("data-ui-theme", theme)
        seen.add(background())
    assert len(seen) == 4                                   # the mode's own colours, then three different palettes
    page.reload()
    expect(page.locator("body")).to_have_attribute("data-ui-theme", "terminal")
    page.select_option("#theme-select", "")                 # back to the display mode's own colours
    select_mode(page, "github-like")
    expect(page.locator("body")).to_have_attribute("data-ui-theme", "github-like")
    expect(page.locator(CARDS)).to_have_count(COUNT)


# ═══ 👁️ display modes ══════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("config_mode", MODES)
def test_the_configured_default_mode_is_applied_on_a_first_visit(page, site, config_mode):
    assert open_front(page, site, config_mode) == config_mode


def test_the_dropdown_changes_mode_and_notation_at_once(page, site):
    open_front(page, site)
    expect(page.locator("#profile-render-root")).to_have_attribute("data-renderer", "web")
    select_mode(page, "markdown")
    expect(page.locator("#profile-render-root")).to_have_attribute("data-renderer", "markdown")
    select_mode(page, "json")
    expect(page.locator("#projects-render-root")).to_have_attribute("data-renderer", "json")


def test_the_chosen_mode_is_stored_and_restored(page, site):
    open_front(page, site)
    page.select_option("#view-mode-select", "json")
    assert page.evaluate("localStorage.getItem('site:view-mode')") == "json"
    assert page.evaluate("localStorage.getItem('site:view-mode-base')") == "modern"
    page.select_option("#view-mode-select", "github-like")
    page.reload()
    page.wait_for_load_state("networkidle")
    expect(page.locator("body")).to_have_attribute("data-view-mode", "github-like")


def test_a_changed_config_overrides_a_stale_choice(page, site):
    open_front(page, site)
    page.select_option("#view-mode-select", "xml-like")
    write_config(site, "json")
    page.reload()
    page.wait_for_load_state("networkidle")
    expect(page.locator("body")).to_have_attribute("data-view-mode", "json")


def test_an_invalid_configured_mode_falls_back_to_modern(page, site):
    assert open_front(page, site, "totally-invalid") == "modern"


def test_modern_keeps_the_web_notation_with_a_terminal_look(page, site):
    open_front(page, site)
    expect(page.locator('#profile-render-root[data-renderer="web"] .tabs')).to_be_visible()
    expect(page.locator(".skill-bar-fill")).to_have_count(sum(len(group["items"]) for group in PROFILE["skills"]))
    expect(page.locator(".timeline-item")).to_have_count(len(PROFILE["career"]))
    expect(page.locator('#projects-render-root[data-renderer="web"] .ui-card')).to_have_count(COUNT)
    style = page.evaluate("""() => { const body = getComputedStyle(document.body), card = getComputedStyle(document.querySelector('.card'));
        return { font: body.fontFamily, background: body.backgroundColor, radius: card.borderRadius }; }""")
    assert "monospace" in style["font"].lower() and style["radius"] == "0px"
    select_mode(page, "github-like")
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") != style["background"]
    expect(page.locator("#profile-render-root")).to_have_attribute("data-renderer", "web")
    expect(page.locator(CARDS)).to_have_count(COUNT)


@pytest.mark.parametrize("width", [390, 1280])
def test_the_career_matches_the_profile_in_every_mode(page, site, width):
    page.set_viewport_size({"width": width, "height": 844})
    open_front(page, site)
    current = next(entry for entry in PROFILE["career"] if entry["year"] == "2026–")
    root = page.locator("#profile-render-root")
    for mode in ("modern", "xml-like", "json", "markdown", "github-like"):
        select_mode(page, mode)
        if mode in ("modern", "github-like"):
            root.get_by_role("tab", name=re.compile("Career")).click()      # modern's CSS adds brackets to the accessible name
            items = root.locator(".timeline-item")
            expect(items).to_have_count(len(PROFILE["career"]))
            expect(items.locator(".tl-year")).to_have_text([entry["year"] for entry in PROFILE["career"]])
            expect(items.locator(".tl-body strong")).to_have_text([entry["title"] for entry in PROFILE["career"]])
            item = items.filter(has=page.locator(".tl-year", has_text=current["year"]))
            expect(item.locator(".tl-year")).to_be_visible()
            expect(item.locator(".tl-body strong")).to_be_visible()
        elif mode == "xml-like":
            expect(root.locator(".xml-tag").filter(has_text=re.compile(r"^<Entry year="))).to_have_count(len(PROFILE["career"]))
        elif mode == "markdown":
            expect(root.locator('h3:has-text("### Career") + ul > li')).to_have_count(len(PROFILE["career"]))
        else:
            assert json.loads(root.text_content())["career"] == PROFILE["career"]
        expect(root).to_contain_text(current["year"])
        expect(root).to_contain_text(current["title"])


def test_each_notation_draws_the_profile_and_projects_its_own_way(page, site):
    profile, projects = page.locator("#profile-render-root"), page.locator("#projects-render-root")
    link = re.compile(r"github\.com/myon-bioinformatics")
    open_front(page, site, "xml-like")
    expect(profile).to_have_attribute("data-renderer", "xml")
    for tag in ("<Profile>", "<About>", "<Skills>", "<Career>"):
        expect(profile).to_contain_text(tag)
    expect(projects).to_contain_text("<Projects>")
    expect(projects.locator("a").first).to_have_attribute("href", link)
    select_mode(page, "json")
    expect(profile).to_have_attribute("data-renderer", "json")
    expect(profile).to_contain_text('"about":')
    expect(profile).to_contain_text('"skills":')
    expect(projects).to_contain_text('"name":')
    expect(projects.locator("a").first).to_have_attribute("href", link)
    select_mode(page, "markdown")
    expect(profile).to_have_attribute("data-renderer", "markdown")
    expect(profile).to_contain_text("### About")
    expect(profile).to_contain_text("### Skills")
    expect(profile.locator("ul").first).to_be_visible()
    expect(projects.locator("h3 a").first).to_have_attribute("href", link)
    for mode in MODES:                                          # and every mode carries the same data
        select_mode(page, mode)
        expect(profile).to_contain_text("Bioinformatics")
        expect(projects).to_contain_text("nvd_nist_known_vulns")


def test_notation_colours_come_from_css_variables(page, site):
    open_front(page, site, "xml-like")
    names = ("--syntax-xml", "--syntax-json-punctuation", "--syntax-markdown-marker")
    values = page.evaluate("names => names.map(name => getComputedStyle(document.documentElement).getPropertyValue(name).trim())", list(names))
    assert all(values), dict(zip(names, values))
    colour = lambda selector: page.locator(selector).first.evaluate("node => getComputedStyle(node).color")
    assert colour(".xml-tag")
    select_mode(page, "json")
    assert colour(".json-punctuation")
    select_mode(page, "markdown")
    assert colour(".md-heading")


def test_reduced_motion_stops_card_movement(page, site):
    page.emulate_media(reduced_motion="reduce")
    open_front(page, site)
    duration = page.locator(".card").first.evaluate("node => getComputedStyle(node).transitionDuration")
    assert float(re.match(r"[\d.e+-]+", duration)[0]) <= 0.0001, duration


# ═══ 🤖 AI highlights: live GitHub data, or curated examples that say so ══════════════════════════════════════════

AI_SEARCH = "https://api.github.com/search/repositories?*"


def test_live_highlights_follow_every_mode_and_a_late_answer_keeps_the_current_one(page):
    held = []
    page.route(AI_SEARCH, lambda route: held.append(route))
    page.goto("/")
    expect(page.locator(CARDS)).to_have_count(COUNT)
    page.select_option("#view-mode-select", "json")
    held[0].fulfill(json={"items": [{"full_name": f"demo/model{i}", "html_url": f"https://github.com/demo/model{i}",
                                     "description": "Safe AI example", "stargazers_count": 1001 + i, "language": "Python"} for i in range(4)]})
    expect(page.locator("#ai-highlights-status")).to_contain_text("public GitHub API")
    expect(page.locator("body")).to_have_attribute("data-view-mode", "json")
    root = page.locator("#ai-highlights-render-root")
    for mode, notation in (("xml-like", "xml"), ("json", "json"), ("markdown", "markdown"), ("github-like", "web"), ("modern", "web")):
        page.select_option("#view-mode-select", mode)
        expect(root).to_have_attribute("data-renderer", notation)
        expect(root).to_contain_text("demo/model")
    page.locator("#ai-highlights-refresh").click()
    expect(root.locator(".card")).to_have_count(3)
    page.select_option("#view-mode-select", "json")             # the filled JSON notation is real JSON
    shown = json.loads(root.text_content())
    assert len(shown) == 3 and all(item["name"].startswith("demo/model") and item["stars"] > 1000 for item in shown)


@pytest.mark.parametrize("failure", ["http", "network", "unsafe-url"])
def test_curated_examples_are_named_as_such_when_live_data_fails(page, failure):
    page.route(AI_SEARCH, lambda route: route.abort() if failure == "network" else route.fulfill(
        status=403 if failure == "http" else 200, json={"items": [{"full_name": "evil/code", "html_url": "javascript:alert(1)"}]}))
    page.goto("/")
    expect(page.locator("#ai-highlights-status")).to_contain_text("Curated examples")
    expect(page.locator("#ai-highlights-render-root .card")).to_have_count(3)
    expect(page.locator('#ai-highlights-render-root a[href^="javascript:"]')).to_have_count(0)


# ═══ 🖼️ brand and reachability ═════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("width", [390, 1280])
def test_brand_icon_and_favicons_stay_intact_across_modes(page, width):
    page.set_viewport_size({"width": width, "height": 844})
    page.goto("/")
    for mode in MODES:
        select_mode(page, mode)
        avatar = page.get_by_role("button", name="Blink", exact=True)
        expect(avatar).to_be_visible()
        expect(avatar).to_have_attribute("data-gaze-bound", "")
        avatar_box = avatar.bounding_box()
        assert abs(avatar_box["x"] + avatar_box["width"] / 2 - page.evaluate("document.documentElement.clientWidth") / 2) <= 4  # JSON mode has an asymmetric gutter
        brand = page.locator(".site-header .brand-icon")
        expect(brand).to_be_visible()
        assert brand.evaluate("image => [image.complete, image.naturalWidth, image.naturalHeight]") == [True, 170, 170]
        expect(page.locator(".site-header h1")).to_have_text("myon-bioinformatics")
        header, heading = page.locator(".site-header .container").bounding_box(), page.locator(".site-header h1").bounding_box()
        assert heading["x"] + heading["width"] <= header["x"] + header["width"], mode
    icons = page.locator('link[rel="icon"]').evaluate_all("links => links.map(link => link.getAttribute('href'))")
    assert icons == ["./favicon.ico", "./assets/brand/favicon-32x32.png", "./assets/brand/favicon-16x16.png"]
    for href in icons:
        response = page.request.get(href)
        assert response.status == 200 and len(response.body()) > 100, href
    (ROOT / "test-results").mkdir(exist_ok=True)
    page.screenshot(path=str(ROOT / "test-results" / f"brand-{width}.png"))


def test_brand_assets_resolve_when_the_page_is_served_below_a_subpath(page, site):
    def strip_prefix(route):
        url = route.request.url.replace(site[1] + "/preview", site[1], 1)
        route.fulfill(response=page.request.get(url))
    page.route("**/preview/**", strip_prefix)
    page.goto("/preview/index.html")
    brand = page.locator(".site-header .brand-icon")
    expect(brand).to_be_visible()
    expect(brand).to_have_js_property("naturalWidth", 170)
    for href in page.locator('link[rel="icon"]').evaluate_all("links => links.map(link => link.href)"):
        assert href.startswith(site[1] + "/preview/"), href


@pytest.mark.parametrize("path", ["/", "/tools/html-import/", "/tools/mcp-toolcall-lab/#home", "/tools/mcp-toolcall-lab/#wiki",
                                  "/tools/mcp-toolcall-lab/#pixiv", "/tools/mcp-toolcall-lab/#niconico", "/tools/mcp-toolcall-lab/#pokemon",
                                  "/tools/mcp-toolcall-lab/repository-diagnostics.html"])
def test_each_hosted_page_loads_and_draws(page, path):
    response = page.goto(path)
    assert response.status == 200
    page.wait_for_load_state("networkidle")
    assert len(page.screenshot(type="png")) > 1000
