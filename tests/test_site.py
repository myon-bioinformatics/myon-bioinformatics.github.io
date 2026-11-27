"""🌐 The published site: portal links, HTML import and the lab publication (the set Dockerfile.html-import runs)."""

import hashlib
import importlib.util
import json
import re
import socket
import struct
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]


# The front page, the demos and the project pages are generated, not committed, so pages are read from the staged site:
# the public static and generated files (scripts/project_pages.py --stage).
def _staged_site() -> tuple:
    import atexit, shutil
    spec = importlib.util.spec_from_file_location('project_pages', ROOT / 'scripts/project_pages.py')
    pages = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pages)
    site = Path(tempfile.mkdtemp(prefix='portfolio-site-'))
    atexit.register(shutil.rmtree, site, ignore_errors=True)
    pages.stage(site)
    return site, pages


SITE, PAGES = _staged_site()
# 🧰 the tools stage() built from the pinned checkouts under .test-deps/ (CI checks out mcp-toolcall-lab there)
_RECEIPT = SITE / PAGES.TOOLS
MADE = json.loads(_RECEIPT.read_text(encoding='utf-8'))['made'] if _RECEIPT.is_file() else []
LAB_BUILT = 'mcp-toolcall-lab' in MADE
needs_lab = pytest.mark.skipif(not LAB_BUILT, reason='🔌 clone mcp-toolcall-lab (the CI pin) into .test-deps/mcp-toolcall-lab')


def test_stage_serves_published_static_files_verbatim():
    for name in ('api/repos.json', 'profile.json', 'projects.json', 'site.config.json',
                 'docs/html-import.md', 'docs/evidence/browser.gif', 'docs/evidence/browser.json',
                 'docs/evidence/chat.gif', 'docs/evidence/home-screen.gif',
                 'tools/niconico/search.js', 'tools/vendor/web-ui/LICENSE'):
        assert (SITE / name).read_bytes() == (ROOT / name).read_bytes(), name


# ═══ 🔗 portal links ══════════════════════════════════════════════════════════════════════════════════════

EXPECTED_PAGES = {
    "https://myon-bioinformatics.github.io/PySaiyanWeBoo/",
    "https://myon-bioinformatics.github.io/tools/image-studio/",
    "https://myon-bioinformatics.github.io/tools/browser-tools/",
    "https://myon-bioinformatics.github.io/tools/slide-studio/",
    # Other repositories' Pages (each checked to load on 2026-11-13): the operations dashboard, usage guides.
    "https://myon-bioinformatics.github.io/markdown/",
    "https://myon-bioinformatics.github.io/myon-bioinformatics/",
    *(f"https://myon-bioinformatics.github.io/{name}/" for name in
      ("Aoi", "NagoyAction", "FluidFullSpeedSimulation", "xprobe", "gh_identity", "yourself", "cli_args", "ascii_artist")),
}

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.links = []
    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            self.ids.add(values["id"])
        if tag == "a" and values.get("href"):
            self.links.append(values["href"])

def test_portal_exposes_expected_pages():
    parser = LinkParser()
    parser.feed((SITE / "index.html").read_text(encoding="utf-8"))
    assert "tools" in parser.ids
    assert EXPECTED_PAGES <= set(parser.links)


def test_tool_cards_and_door_follow_the_service_catalog(tmp_path, monkeypatch):
    from shutil import copyfile

    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    copyfile(ROOT / 'scripts/front_page.py', scripts / 'front_page.py')
    path = tmp_path / 'services.json'
    catalog = json.loads((ROOT / 'services.json').read_text(encoding='utf-8'))
    projects = catalog['services']['projects']
    projects['Ironmate']['pages']['url'] = 'https://myon-bioinformatics.github.io/tools/example-image/'
    projects['mcp-toolcall-lab']['execution']['url'] = 'https://myon-bioinformatics.github.io/tools/example-execution/'
    path.write_text(json.dumps(catalog), encoding='utf-8')
    front = PAGES.load_module('test_front_catalog', scripts / 'front_page.py')
    monkeypatch.setattr(PAGES, '_front_module', lambda: front)

    parser = LinkParser()
    parser.feed(front.portal_cards())
    assert 'https://myon-bioinformatics.github.io/tools/example-image/' in parser.links
    assert './tools/example-image/' in parser.links  # keep the heatmap-to-editor shortcut
    assert 'https://myon-bioinformatics.github.io/tools/example-execution/' in parser.links
    assert not any('/image-studio/' in href or '/mcp/execution/' in href for href in parser.links)
    doors = [place['href'] for place in PAGES.tools_places()]
    assert doors.count('../../tools/example-image/') == 1
    assert '../../tools/example-execution/' in doors


def test_every_active_repository_with_pages_is_one_tap_away():
    """🌐 api/repos.json (has_pages) owns the Pages roots: each project card links its repository's own Pages (🧰 Tools has no
    list of them, and no portfolio copy of a repository's page)."""
    catalog = json.loads((ROOT / "api/repos.json").read_text())
    pages = {repo["name"]: repo["pages"] for repo in catalog["repos"] if repo.get("pages") and not repo.get("archived")}
    assert len(pages) >= 20 and all(url.startswith("https://myon-bioinformatics.github.io/") and url.endswith("/") for url in pages.values())
    page = (SITE / "index.html").read_text(encoding="utf-8")
    assert page.count('class="ui-button project-pages"') == len(pages)                         # one 🌐 on each project card
    assert 'id="guides"' not in page and "tools/projects/" not in page and not (SITE / "tools/projects").exists()
    archived = [repo["name"] for repo in catalog["repos"] if repo.get("archived")]
    assert not any(f"github.io/{name}/" in page for name in archived)                          # archived repositories leave the portal


def test_front_page_shows_only_the_moving_samples_this_build_recorded(tmp_path):
    """🎥 A card carries its repository's sample only when the deploy recorded it (media/pages/<name>.gif), linked to its Pages."""
    front = _front()
    catalog = json.loads((ROOT / "api/repos.json").read_text())
    with_pages = [repo["name"] for repo in catalog["repos"] if repo.get("pages") and not repo.get("archived")]
    assert "media/pages/" not in (SITE / "index.html").read_text(encoding="utf-8")             # nothing recorded, nothing shown
    page = front.document(ROOT, samples=frozenset({with_pages[0].lower(), "no-such-repository"}))
    assert page.count('class="project-sample"') == 1
    assert f'<a class="project-sample" href="https://myon-bioinformatics.github.io/{with_pages[0]}/"><img src="./media/pages/{with_pages[0].lower()}.gif"' in page
    (tmp_path / "media/pages").mkdir(parents=True)
    (tmp_path / "media/pages" / f"{with_pages[1].lower()}.gif").write_bytes(b"GIF89a")
    assert PAGES.recorded_samples(tmp_path) == {with_pages[1].lower()}
    # 🧭 this portfolio's own card too (--record-samples records every Pages of api/repos.json, this one included)
    assert PAGES.pages_urls(ROOT)["myon-bioinformatics.github.io"] == "https://myon-bioinformatics.github.io/"
    own = front.document(ROOT, samples=frozenset({"myon-bioinformatics.github.io"}))
    assert ('<a class="project-sample" href="https://myon-bioinformatics.github.io/">'
            '<img src="./media/pages/myon-bioinformatics.github.io.gif"') in own
    (tmp_path / "media/pages/myon-bioinformatics.github.io.gif").write_bytes(b"GIF89a")           # the dots stay in the name
    assert "myon-bioinformatics.github.io" in PAGES.recorded_samples(tmp_path)


def test_a_tools_card_shows_its_moving_sample_and_the_picture_opens_the_tool(tmp_path):
    """🎥 A 🧰 Tools card carries its sample only when the deploy recorded it (media/pages/tools/<id>.gif); the picture is a link to
    the card's first page, as on a 🚀 Projects card. Every card has an id, so every card can have one (🧭 the dashboard on another
    repository's Pages too). With its picture, a card keeps its links in words only when it opens several pages of a kind."""
    from html import escape as html_escape
    front = _front()
    ids = [card["id"] for card in front.PORTAL]
    assert len(ids) == len(set(ids)) and all(re.fullmatch(r"[a-z][a-z0-9-]*", key) for key in ids)
    assert "project-sample" not in front.portal_cards() and "media/pages/tools/" not in (SITE / "index.html").read_text(encoding="utf-8")
    plain = front.portal_cards()
    assert all(f'<a href="{html_escape(href)}">{html_escape(label, quote=False)}</a>' in plain for card in front.PORTAL for label, href in card["links"])
    cards = front.portal_cards(frozenset({"tools/gif", "tools/operations", "tools/maps", "gif", "tools/no-such-tool"}))
    assert cards.count('class="project-sample"') == 3
    assert "GIF をつくる →" not in cards and "Open Dashboard →" not in cards and ">実験室へ →</a>" in cards        # one page: the picture; no picture: the words
    assert ('<a href="./tools/maps/">地図URLを作成 →</a><a href="./tools/demos/world.html#tokyo">パラレル東京 →</a>' in cards
            and '<a class="project-sample" href="./tools/maps/">' in cards)                                    # relatives stay side by side
    everything = front.portal_cards(frozenset(f"tools/{key}" for key in ids))
    several = [card for card in front.PORTAL if len(card["links"]) > 1]
    assert everything.count('class="project-sample"') == len(ids) and several
    assert everything.count("<a href=") == sum(len(card["links"]) for card in several)
    assert ('<h3 id="gif">🎞 GIF工房</h3><a class="project-sample" href="./tools/gif/"><img src="./media/pages/tools/gif.gif" '
            'alt="🎥 🎞 GIF工房" loading="lazy" width="240" height="456"></a><p>') in cards
    assert '<a class="project-sample" href="https://myon-bioinformatics.github.io/myon-bioinformatics/"><img src="./media/pages/tools/operations.gif"' in cards
    samples = PAGES.tools_samples()                                              # what --record-samples opens: the card's first link, on the site
    assert list(samples) == [f"tools/{key}" for key in ids] and samples["tools/gif"] == ("https://myon-bioinformatics.github.io/tools/gif/", "🎞 GIF工房")
    assert all(url.startswith("https://myon-bioinformatics.github.io/") for url, _ in samples.values())
    (tmp_path / "media/pages/tools").mkdir(parents=True)
    (tmp_path / "media/pages/tools/gif.gif").write_bytes(b"GIF89a")
    (tmp_path / "media/pages/aoi.gif").write_bytes(b"GIF89a")
    assert PAGES.recorded_samples(tmp_path) == {"tools/gif", "aoi"}
    page = PAGES.render_front(ROOT, PAGES.recorded_samples(tmp_path))["index.html"].decode("utf-8")
    assert page.count('<img src="./media/pages/tools/') == 1 and '<img src="./media/pages/tools/gif.gif"' in page


def test_flow_lab_shows_every_ffss_scene_and_every_dragowing_figure(tmp_path):
    """🌊 collect_flow keeps every demo FFSS lists (whose GIF was made) and every figure; render_flow puts each figure
    with its scene and the rest after the scenes, so nothing that was made is left out."""
    import pysaiyanweboo as ui
    ffss, dragowing = tmp_path / "ffss", tmp_path / "dragowing"
    ffss.mkdir(); dragowing.mkdir()
    listed = [{"id": "D01", "icon": "🏛️", "scene": "moniac-rig", "fluid": "water", "file": "D01_moniac-rig_water.gif"},
              {"id": "D13", "icon": "🍷", "scene": "pythagorean-cup", "fluid": "poison-water", "file": "D13_pythagorean-cup_poison-water.gif"},
              {"id": "D24", "icon": "🫀", "scene": "circulation", "fluid": "water", "file": "D24_circulation_water.gif"},
              {"id": "D99", "icon": "🫥", "scene": "missing", "fluid": "water", "file": "D99_missing_water.gif"}]   # not written
    (ffss / "fluidfullspeedsimulation.py").write_text(
        "import sys, pathlib, json\n"
        "a = sys.argv[1:]\n"
        "if a[0] == 'run': pathlib.Path(a[a.index('--jsonl') + 1]).write_text('{\"id\": \"%s\", \"run\": \"x\"}\\n' % a[1])\n"
        "else:\n"
        "    assert '--only' not in a                                   # every demo, none picked\n"
        "    out = pathlib.Path(a[a.index('--out-dir') + 1]); out.mkdir(parents=True)\n"
        f"    listed = {listed!r}\n"
        "    for d in listed[:3]: (out / d['file']).write_bytes(b'GIF89a' + d['id'].encode())\n"
        "    (out / 'demos.json').write_text(json.dumps({'schema': 'x', 'demos': listed}))\n", encoding="utf-8")
    (dragowing / "dragowing.py").write_text(
        "import sys, pathlib\n"
        "a = sys.argv[1:]\n"
        "assert pathlib.Path(a[a.index('--ffss') + 1]).read_text().count('\\n') == 3   # E30, E31 and E32 records\n"
        "svg = pathlib.Path(a[a.index('--out') + 1]) / 'svg'; svg.mkdir(parents=True)\n"
        "for f in ('F03_losses', 'F09_blood-flow'): (svg / (f + '.svg')).write_text('<svg/>')\n", encoding="utf-8")
    receipt = PAGES.collect_flow(tmp_path / "site", ffss, dragowing, {"ffss": "a" * 40, "dragowing": "b" * 40})
    assert [d["id"] for d in receipt["demos"]] == ["D01", "D13", "D24"] and receipt["figures"] == ["F03_losses", "F09_blood-flow"]
    assert (tmp_path / "site/media/flow/D13.gif").read_bytes() == b"GIF89aD13"
    page = PAGES.render_flow(ui, tmp_path / "site")[PAGES.FLOW_PAGE].decode()
    assert page.count('<img loading="lazy" src="../../media/flow/') == 3 + 2 and "⏸" not in page
    assert page.index("D24.gif") < page.index("F09_blood-flow.svg") < page.index("📊 ほかの図") < page.index("F03_losses.svg")
    assert "🍷 D13 pythagorean-cup · poison-water" in page and "🎞 3 場面" in page and "2 図" in page
    assert "FFSS aaaaaaa" in page and "/tree/" + "b" * 40 in page
    staged = (SITE / "tools/flow/index.html").read_text(encoding="utf-8")                # nothing recorded: one ⏸
    assert staged.count("⏸") == 1 and "media/flow/" not in staged


def test_repository_map_reads_each_lock_and_aois_subtrees(tmp_path):
    """🧠 Edges come from each repository's own vendor.lock.json rows and Aoi's child-heads.json; an unreadable one is ⏸."""
    import pysaiyanweboo as ui
    root = tmp_path / "root"
    (root / "api").mkdir(parents=True)
    (root / "api/repos.json").write_text(json.dumps({"repos": [{"name": n} for n in ("Aoi", "markdown", "xprobe", "Broken")]
                                                     + [{"name": "Old", "archived": True}]}))
    row = lambda repo, dest: {"repository": f"myon-bioinformatics/{repo}", "source": "x.py", "destination": dest}
    files = {("markdown", "vendor.lock.json"): {"files": [row("xprobe", "vendor/xprobe.py"), row("xprobe", "vendor/xprobe-LICENSE"),
                                                          row("markdown", "vendor/self.py")]},
             ("Aoi", "vendor.lock.json"): {"files": [row("markdown", "vendor/markdown.py")]},
             ("Aoi", "child-heads.json"): {"heads": {"myon-bioinformatics/QueRyu": {"optional": {"subtree_prefix": "queryu"}}}}}
    def head(repository):
        if repository.endswith("Broken"):
            raise OSError("unreachable")
        return "c" * 40
    raw = lambda repository, commit, path: (json.dumps(files[(repository.split("/")[1], path)]).encode()
                                            if (repository.split("/")[1], path) in files else None)
    lines = PAGES.record_map(tmp_path / "site", root, head=head, raw=raw)
    assert lines == ["🧠 3 repositories · 3 edges · 4 files", "⏸ Broken: OSError"]
    graph = json.loads((tmp_path / "site/media/map/graph.json").read_text())
    assert [(e["from"], e["to"], e["kind"], len(e["files"])) for e in graph["edges"]] == [
        ("Aoi", "QueRyu", "subtree", 1), ("markdown", "Aoi", "vendor", 1), ("xprobe", "markdown", "vendor", 2)]   # no self-edge
    svg = (tmp_path / "site/media/map/map.svg").read_text()
    assert svg.startswith("<svg") and svg.count("<path") == 3 and "Meiryo" in svg
    assert "🗄 Old" in PAGES.map_svg([{"from": "Old", "to": "Aoi", "kind": "vendor", "files": ["LICENSE"]}], {"Old"})   # archived is marked
    page = PAGES.render_map(ui, tmp_path / "site")[PAGES.MAP_PAGE].decode()
    assert 'src="../../media/map/map.svg"' in page and "📥 xprobe" in page and "⏸" not in page
    assert "⏸" in (SITE / "tools/repo-map/index.html").read_text(encoding="utf-8")        # nothing recorded in the staged site


def test_gif_workshop_page_keeps_images_in_the_browser():
    page = (SITE / "tools/gif/index.html").read_text(encoding="utf-8")
    assert 'id="gif-files"' in page and 'accept="image/*"' in page and "function bindMaker" in page   # PySaiyanWeBoo's gif_maker_document
    import pysaiyanweboo as ui
    tool, _, chrome = page.partition('<script type="module">' + ui.component_parts('chrome')['js'][:64])    # 🧰 the chrome's module, then 🚪 the door's
    assert "bindChrome();" in chrome and "bindDoor()" in chrome and "fetch(" not in page and "XMLHttpRequest" not in page   # nothing is sent
    assert "localStorage" not in tool                                                             # the tool keeps nothing: no image, no setting
    assert sorted(set(re.findall(r"save\(\{(\w+)", chrome))) == ["fav", "lang"]                     # the chrome keeps ⭐ and 🌐 only


def test_catalog_pages_come_from_has_pages():
    spec = importlib.util.spec_from_file_location("repos_catalog_pages", ROOT / "scripts" / "repos_catalog.py")
    catalog = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(catalog)
    owner = "myon-bioinformatics"
    assert catalog.pages_url(owner, {"name": "Aoi", "has_pages": True}) == "https://myon-bioinformatics.github.io/Aoi/"
    assert catalog.pages_url(owner, {"name": "myon-bioinformatics.github.io", "has_pages": True}) == "https://myon-bioinformatics.github.io/"
    assert catalog.pages_url(owner, {"name": "Aoi", "has_pages": False}) is None


def test_portal_pages_stay_under_owned_pages_host():
    for url in EXPECTED_PAGES:
        parsed = urlparse(url)
        assert parsed.scheme == "https"
        assert parsed.netloc == "myon-bioinformatics.github.io"
        assert parsed.path.startswith("/")


def test_ironmate_metadata_lives_with_the_portfolio():
    import json
    metadata = json.loads((ROOT / "project-ironmate.json").read_text())
    assert metadata["schema"] == "project-metadata/1"
    assert metadata["repository"] == "https://github.com/myon-bioinformatics/Ironmate"
    parser = LinkParser()
    page = (SITE / "index.html").read_text()
    tools = page[page.index('<section id="tools"'):]
    parser.feed(tools[:tools.index("</section>")])          # the 🧰 Tools cards; the project list links every repository
    assert parser.links and metadata["repository"] not in parser.links
    # The former repository fallback is removed; metadata remains machine-readable.
    assert "./project-ironmate.json" not in parser.links
    assert (ROOT / "project-ironmate.json").is_file()
    assert not any("/Ironmate/mcp-stub.html" in url for url in parser.links)


def test_ironmate_pptx_status_is_prototype_not_product_ready():
    import json

    metadata = json.loads((ROOT / "project-ironmate.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "prototype_implemented"
    assert metadata["pptx"]["status"] == "prototype"
    conversion = metadata["pptx"]["markdown_to_pptx"]
    editing = metadata["pptx"]["existing_pptx_editing"]
    assert conversion["cli"] == "pptx_pipeline.py"
    assert conversion["input_modes"] == ["Markdown file", "inline --text", "stdin -"]
    assert "preinstalled Marp CLI" in conversion["requires"]
    assert "Marp-generated slides may not have editable text" in conversion["limitations"]
    assert editing["cli"] == "pptx_replace.py"
    assert "text replacement within each text run" in editing["supported"]
    assert "explicit solid RGB slide background" in editing["supported"]
    assert "theme/inherited text colors and slide backgrounds" in editing["unsupported"]
    assert "arrow attributes and advanced formatting" in editing["unsupported"]

    html = (SITE / "index.html").read_text(encoding="utf-8")
    card_start = html.index('<h3 id="studios">🖼️ スライド・画像工房</h3>')
    card = html[card_start:html.index("</article>", card_start)]
    assert "PPTX対応は計画段階" not in card
    assert "Markdown→PPTX" in card
    assert "試作実装" in card
    assert "ブラウザでスライドを作成" in card
    assert "Open Repository" not in card
    assert "tools/slide-studio/" in card


def test_lab_pages_are_hosted_by_portfolio():
    parser = LinkParser()
    parser.feed((SITE / "index.html").read_text())
    assert "mcp" in parser.ids
    assert "./tools/mcp/" in parser.links
    assert (SITE / "tools/mcp/index.html").is_file() and (SITE / "tools/mcp/execution/index.html").is_file()


def test_tool_cards_are_named_for_what_they_do_not_for_a_repository():
    """🏷 A card built from other repositories is a tool, not those projects: its title, id and paths are not a repository
    name, and a 🧩 line names where it comes from (every ``from`` is a real repository)."""
    front = _front()
    names = {repo['name'].lower() for repo in json.loads((ROOT / 'api/repos.json').read_text(encoding='utf-8'))['repos']}
    page = (SITE / "index.html").read_text()
    for card in front.PORTAL:
        assert card['title'].lower() not in names and card.get('id', '').lower() not in names, card['title']
        for name in card.get('from', ()):
            assert name.lower() in names, name
        if 'from' in card:
            assert '🧩 出どころ: ' + ' · '.join(card['from']) in page, card['title']
        links = card['links'] if isinstance(card['links'], list) else []
        assert not any(f'/tools/{name}/' in href.lower() for _, href in links for name in names), card['title']


# PySaiyanWeBoo's tool documents (PSWB_TOOLS) and the 🌍 world pages (WORLD_PAGE, tools/demos/) come from scripts/project_pages.py; they are tool pages too.
TOOL_PAGES = ("tools/html-import/index.html",
              *(("tools/mcp/index.html", "tools/mcp/repository-diagnostics.html") if LAB_BUILT else ()),
              "tools/maps/index.html", "tools/gif/index.html", "tools/chat/index.html", "tools/flow/index.html",
              "tools/test-report/index.html", "tools/mcp-protocol/index.html",
              "tools/repo-map/index.html",
              PAGES.WORLD_PAGE)


def test_tools_built_from_other_repositories_never_404():
    """🧰 Without a recording (tests, a failed clone) every entry of a tool built from another repository is a ⏸ page with
    the way back at its own depth; a failed rebuild keeps what was there."""
    for key, (repository, folder, entries) in PAGES.TOOL_SOURCES.items():
        for entry in entries:
            name = f'{folder}/{entry}index.html'
            html = (SITE / name).read_text(encoding='utf-8')
            if key in MADE:                                   # built from a pinned checkout: the way back, no ⏸
                assert 'data-testid="portfolio-back"' in html and '⏸' not in html, name
                continue
            assert '⏸' in html and f'https://github.com/{repository}' in html, name
            assert f'<a href="{"../" * name.count("/")}index.html#tools">' in html, name
    front = LinkParser()
    front.feed((SITE / "index.html").read_text(encoding="utf-8"))
    assert "./tools/heatmap/" in front.links                                         # 🌡️ the 🧰 Tools card opens it
    with tempfile.TemporaryDirectory() as tmp:
        kept = Path(tmp) / 'tools/image-studio/index.html'
        kept.parent.mkdir(parents=True)
        kept.write_text('kept', encoding='utf-8')
        receipt = PAGES.collect_tools(Path(tmp), {'ironmate': Path(tmp) / 'no-checkout'}, {'ironmate': '0' * 40})
        assert receipt['made'] == [] and 'ironmate' in receipt['failed'] and kept.read_text(encoding='utf-8') == 'kept'


def test_ironmate_publication_relocates_cross_links_assets_and_manifest(tmp_path):
    checkout = tmp_path / 'checkout'
    checkout.mkdir()
    (checkout / 'image_studio.py').write_text(
        "import pathlib,sys\n"
        "root = pathlib.Path(sys.argv[2])\n"
        "pages = {'index.html': '<a href=\\\"slides/phone/\\\">phone</a><script src=\\\"studio.js\\\"></script>',\n"
        " 'tools/index.html': '<a href=\\\"../slides/#target\\\">slides</a>',\n"
        " 'slides/index.html': '<a href=\\\"../tools/\\\">tools</a>',\n"
        " 'slides/phone/index.html': '<a href=\\\"../../\\\">image</a><script src=\\\"../../studio.js\\\"></script>'}\n"
        "for name, text in pages.items():\n"
        " p = root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('<main>' + text + '</main>')\n"
        "(root / 'studio.js').write_text('shared')\n"
        "(root / 'brand').mkdir()\n"
        "(root / 'brand/manifest.webmanifest').write_text('{\\\"shortcuts\\\":[{\\\"url\\\":\\\"../slides/\\\"}]}')\n",
        encoding='utf-8',
    )
    out = tmp_path / 'site'
    receipt = PAGES.collect_tools(out, {'ironmate': checkout}, {'ironmate': '0' * 40})
    assert receipt['made'] == ['ironmate']
    assert not (out / 'tools/ironmate').exists()
    assert not (SITE / '_src/tools/studio_routes.py').exists()  # source is not a public artifact
    tools = out / 'tools'
    assert 'href="../slide-studio/phone/"' in (tools / 'image-studio/index.html').read_text()
    assert 'href="../slide-studio/#target"' in (tools / 'browser-tools/index.html').read_text()
    assert 'href="../browser-tools/"' in (tools / 'slide-studio/index.html').read_text()
    phone = (tools / 'slide-studio/phone/index.html').read_text()
    assert 'href="../../image-studio/"' in phone and 'src="../../image-studio/studio.js"' in phone
    assert 'href="../../../index.html#tools"' in phone
    assert (tools / 'image-studio/studio.js').read_text() == 'shared'
    manifest = json.loads((tools / 'image-studio/brand/manifest.webmanifest').read_text())
    assert manifest['scope'] == '../../'
    assert manifest['shortcuts'] == [{'url': '../../slide-studio/'}]


def test_every_tool_page_carries_the_same_chrome_and_a_world_page_adds_what_it_lacks():
    """🧰 tools_chrome + PySaiyanWeBoo's chrome: the board with the clock, 🏠, ⭐ ⚙️ and ☰ ⋯ for the page's own (☰ lists nothing
    of other pages); and 🚪 tools_door: PySaiyanWeBoo's Door-to-Door with 🏠 and every 🧰 Tools link, this page marked as the door you
    came in by. A 🌍 world page keeps its own header and side (the same parts) and gets what it lacks, 🫧 in that header and the
    foot; a page with nothing to say of itself says a line any page can (📟 a placeholder). Every door leads to a page of this site."""
    import html
    import re
    import pysaiyanweboo as ui
    module = ('<script type="module">' + ui.component_parts('chrome')['js'] + '</script><div class="ui-door-foot"><div class="ui-door ui-door-compact" id="door" data-ui-door ',
              '</span></p></div><script type="module">' + PAGES.tools_door(ui)['js'] + '</script></body>')
    assert PAGES.tools_door(ui)['js'] == ui.js_source('door.js') and 'addEventListener("pageshow",fill)' in module[1]   # PySaiyanWeBoo's door.js alone
    cards = [html.escape(card['title']) for card in PAGES.load_module('front_page', 'scripts/front_page.py').PORTAL]
    pages = {*TOOL_PAGES, *(f'{folder}/{entry}index.html' for _, folder, entries in PAGES.TOOL_SOURCES.values() for entry in entries)}
    assert len(pages) > len(TOOL_PAGES)
    for name in sorted(pages):
        page = (SITE / name).read_text(encoding='utf-8')
        prefix = '../' * name.count('/')
        body = re.search(r'<body[^>]*>', page)
        assert '<div class="ui-board"' in page and page.count('<button type="button" class="ui-gaze"') == page.count('<div class="ui-door-foot">') == 1, name   # 📟 🫧 🚪 on every page
        if '<header class="ui-world-head">' in page:                               # 🌍 its own header and side: 🫧 after its board, then the foot
            assert '<div class="ui-chrome ' not in page and '</div><button type="button" class="ui-gaze"' in page[:page.index('<nav class="ui-world-tools">')], name
            assert page.count(module[1]) == 1 and f'<option value="{prefix}index.html#tools">🏠 Tools</option>' in page, name
            continue
        assert page[body.end():].startswith('<div class="ui-chrome ui-world-head" id="tools-chrome" data-ui-chrome lang="ja">'), name
        assert page.count('<div class="ui-chrome') == 1 and '<span class="ui-board-clock" data-clock>--:--:--</span>' in page, name
        assert page.count(module[0]) == 1 and page.count(module[1]) == 1 and page.count('<div class="ui-door-foot">') == 1, name
        foot = re.search(r'<p class="ui-door-extras"><a href="https://twitter\.com/myonitbusiness"[^>]* target="_blank" rel="noopener noreferrer">🐦</a>'
                         r'<span class="ui-door-size"[^>]*>📦 (\d+) KB</span></p></div>', page)
        assert foot and abs(int(foot[1]) - len(page.encode('utf-8')) / 1024) <= 1, name                     # 🐦 X and 📦 this page's own size
        assert f'<a class="ui-world-home" href="{prefix}index.html#tools"' in page, name
        chrome = page[body.end():page.index('<div class="ui-world-side">', body.end())]          # the board and the header's tools; ☰ follows
        assert '<img' not in chrome and 'lab-execution-link' not in chrome, name   # 🔌 the lab's logo and links go to the lab's own <header>
        assert page.count('<button type="button" class="ui-gaze"') == 1 and '</div><button type="button" class="ui-gaze"' in chrome, name   # 🫧 after the board
        items = re.findall(r'<span class="ui-board-item"[^>]*>(.*?)</span>', chrome)
        half = len(items) // 2
        assert 1 <= half <= 12 and items[:half] == items[half:], name         # the board says its items (up to 12) twice (the loop)
        about = [item for item in items[:half] if item not in cards]          # 📝 what this page is: its card's text, a sentence per item
        here = next((place['text'] for place in PAGES.tools_places(prefix) if place['href'] == prefix + re.sub(r'index\.html$', '', name)), None)
        assert len(about) <= 3 and items[:half] == about + cards[:12 - len(about)], name
        assert (about and html.unescape(about[0]) in here) if here else True, name
        if not here and '<meta name="description"' not in page:                    # 📟 nothing of its own to say: the line any page can carry
            assert about[0].endswith('：myon-bioinformatics の道具のページ。') and about[1:] == ['🚪 でほかの道具へ、🏠 で一覧へ。'], (name, about)
        assert '<ul class="ui-world-rows ui-world-spots"></ul>' in page and 'data-fav' not in page, name   # ☰ this page's own: the script lists it
        assert page.count('data-scroll="top"') == page.count('data-scroll="bottom"') == 1, name            # ⋯ ⬆️ ⬇️
        rows = [(place['href'], place['id']) for place in PAGES.tools_places(prefix)]                      # 🚪 every tool
        assert len(rows) == len({fav for _, fav in rows}) >= len(cards), name
        for href, fav in rows:
            if href.startswith('https://'):
                assert href == 'https://myon-bioinformatics.github.io/myon-bioinformatics/', href      # 🧭 another repository's Pages
                continue
            path = urlparse(href).path
            target = (SITE / name).parent / path
            assert (target / 'index.html' if path.endswith('/') else target).resolve().is_file(), (name, href)
        doors = re.findall(r'<option value="([^"]+)"( selected disabled)?>([^<]+)</option>', page[page.index('<div class="ui-door-foot">'):page.index(module[1])])
        assert doors[0] == (f'{prefix}index.html#tools', '', '🏠 Tools') and [href for href, _, _ in doors[1:1 + len(rows)]] == [href for href, _ in rows], name   # 🚪 = 🏠 + the tools
        here = [(href, words) for href, mark, words in doors if mark]              # the door you came in by: this very page
        assert len(here) == 1 and ((SITE / name).parent / here[0][0]).resolve() in ((SITE / name).resolve(), (SITE / name).parent.resolve()), (name, here)
        assert len(doors) == 1 + len(rows) + (here[0][1].startswith('📌 ')), name   # 📌 a page that is no tool of the cards is its own door
        assert len({words.split(' ')[0] for _, _, words in doors}) == len(doors), name                    # one emoji, one page
    maps = (SITE / 'tools/maps/index.html').read_text(encoding='utf-8')            # 🗼 an emoji a page adds for its own use
    assert '<a class="ui-world-tool" href="../demos/world.html#tokyo" aria-label="パラレル都市"' in maps
    assert '>🗼</summary>' not in (SITE / 'tools/gif/index.html').read_text(encoding='utf-8')


def test_every_page_turns_modern_on_its_body_only():
    """🎨 add_site_chrome publishes every page in the shared modern look: only the <body>'s palette changes (a theme picker's
    previews keep theirs), and a page without data-ui-theme keeps its own look with the chrome's colours."""
    page = ('<!doctype html><html><head><title>t</title></head><body class="ui-elements" data-ui-theme="green" data-page="studio">'
            '<main><div data-ui-theme="purple">preview</div></main></body></html>')
    built = PAGES.add_site_chrome(page, 'tools/image-studio/index.html')
    assert '<body class="ui-elements" data-ui-theme="modern" data-page="studio">' in built and '<div data-ui-theme="purple">' in built
    plain = PAGES.add_site_chrome('<!doctype html><html><head><title>t</title></head><body><main>x</main></body></html>', 'tools/x/index.html')
    assert '<body>' in plain and '.ui-chrome{--ui-bg:#0d1117;' in plain                       # no palette of its own: the chrome brings its colours


def test_html_import_csp_names_the_face_chrome_and_door_modules_and_nothing_else():
    import pysaiyanweboo as ui
    html = (SITE / PAGES.HTML_IMPORT_PAGE).read_text(encoding='utf-8')
    chrome, doors = ui.module_csp_hash(ui.component_parts('chrome')['js']), ui.module_csp_hash(PAGES.tools_door(ui)['js'])
    face = ui.module_csp_hash(ui.component_parts('gaze-avatar')['js'])                    # 🫧 the header's round face is a module too
    assert f"script-src 'self' {face} {chrome} {doors}; style-src 'self' 'unsafe-inline';" in html
    assert html.count("'sha256-") == 3 and "'unsafe-inline'; img-src" in html and "connect-src 'none'" in html
    strict = ('<!doctype html><html><head><meta\n http-equiv="Content-Security-Policy"\n content="default-src \'none\'; script-src \'self\'; '
              'style-src \'self\'; img-src \'self\' data:"\n/><title>s</title></head><body data-ui-theme="green"><main><h1>s</h1></main></body></html>')
    built = PAGES.add_back_nav(strict, 'tools/image-studio/index.html')        # Ironmate's studios: neither inline scripts nor inline styles
    sheets = re.findall(r'<style>(.*?)</style>', built, re.S)
    assert sheets[0].startswith(ui.component_parts('gaze-avatar')['css']) and len(sheets) == 3
    assert '<body data-ui-theme="modern">' in built and 'data-ui-theme="green"' not in built           # 🎨 one look: the page turns modern,
    assert not any('--ui-bg:' in sheet for sheet in sheets)                                    # and the chrome takes its colours (none pinned)
    assert 'main>nav.ui-back{grid-column:1/-1}' in sheets[0]                                           # the way back spans a grid <main>
    assert (f"script-src 'self' {face} {chrome} {doors}; style-src 'self' {' '.join(ui.module_csp_hash(sheet) for sheet in sheets)}; "
            "img-src 'self' data:\"") in built
    assert built.count("'sha256-") == 6 and ' style="' not in built and PAGES.add_back_nav(built, 'tools/image-studio/index.html') == built   # no style attribute
    assert html.count('<script') == 4 and '<script type="module" src="./extract.mjs"></script>' in html


def test_door_to_door_in_chromium_with_a_gif():
    """🚪 PySaiyanWeBoo's Door-to-Door on the tool pages, in Chromium: only its pull-down is drawn, in a 56px row at the window's foot;
    it shows the page you are on, goes where you choose, follows the browser's own way back, and 🏠 leads to the cards. Nothing is kept.
    Frames go to test-results/door-to-door/door-to-door-pulldown-<UTC>.gif."""
    sync_api = pytest.importorskip('playwright.sync_api')
    ui = pytest.importorskip('pysaiyanweboo')
    import functools, threading
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    world = PAGES._world()
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(SITE)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base, errors = f'http://127.0.0.1:{server.server_port}/', []
    shown = "() => document.querySelector('.ui-door-foot [data-door-select]').selectedOptions[0].textContent"
    try:
        with sync_api.sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='chromium')
            try:
                for width, height in ((392, 848), (1280, 800)):                   # a phone and a desktop: one row at the window's foot
                    page = browser.new_page(viewport={'width': width, 'height': height})
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(base + 'tools/maps/')
                    page.wait_for_selector('#door[data-door_ready]')
                    foot, select = page.locator('.ui-door-foot').bounding_box(), page.locator('.ui-door-foot [data-door-select]')
                    assert (foot['x'], foot['width'], round(foot['y'] + foot['height'])) == (0, width, height) and foot['height'] <= 64, foot
                    assert select.bounding_box()['height'] == 40 and page.evaluate(shown) == '🗺️ 地図URLを作成 (current)'
                    visible = page.evaluate("[...document.querySelectorAll('.ui-door-foot .ui-door *')].filter(e => e.offsetParent && e.tagName !== 'OPTION' && e.getBoundingClientRect().width > 1).map(e => e.tagName)")
                    assert visible == ['LABEL', 'SPAN', 'SELECT'], visible                 # 🚪 and the pull-down (compact): no panel
                    assert page.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth') == 0
                    page.close()
                page = browser.new_page(viewport={'width': 560, 'height': 480})
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + 'tools/gif/')
                page.wait_for_selector('#door[data-door_ready]')
                cam = world.Camera(page)
                assert page.evaluate(shown) == '🎞 GIF工房 (current)'
                cam.hold(900)
                page.locator('.ui-door-foot [data-door-select]').select_option(label='🌊 流れの実験室')
                page.wait_for_url(base + 'tools/flow/')
                page.wait_for_selector('#door[data-door_ready]')
                assert page.evaluate(shown) == '🌊 流れの実験室 (current)'
                assert page.locator('.ui-chrome .ui-world-spots a').first.text_content().startswith('📍')   # the chrome's ☰ is this page's own
                assert not page.evaluate("[...document.querySelectorAll('.ui-chrome .ui-world-spots a')].some(a => a.pathname !== location.pathname)")
                cam.hold(900)
                page.go_back()                                                    # ← the browser's own way back: the pull-down follows
                page.wait_for_url(base + 'tools/gif/')
                page.wait_for_function(shown + " === '🎞 GIF工房 (current)'")
                cam.hold(700)
                page.locator('.ui-door-foot [data-door-select]').select_option(label='🌊 流れの実験室')       # the same door again still opens
                page.wait_for_url(base + 'tools/flow/')
                page.wait_for_selector('#door[data-door_ready]')
                cam.hold(600)
                page.locator('.ui-door-foot [data-door-select]').select_option(label='🏠 Tools')
                page.wait_for_url(base + 'index.html#tools')
                cam.hold(700)
                assert page.evaluate('[localStorage.length, sessionStorage.length]') == [0, 0]            # the door keeps nothing
                gif = world.encode(cam.shots, width=392)
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
    assert errors == [] and gif[:6] == b'GIF89a'
    target = ui.gif_targets(ROOT / 'test-results' / 'door-to-door', ['door-to-door-pulldown'], run_details=['timestamp'])
    target['door-to-door-pulldown'].write_bytes(gif)


def test_every_tool_page_has_the_same_back_link_first_in_main():
    import re
    for page in (SITE / name for name in TOOL_PAGES):
        html = page.read_text(encoding="utf-8")
        main = re.search(r"<main[^>]*>", html)
        assert main, page
        after = html[main.end():]
        assert after.startswith('<nav class="ui-back" aria-label="関連リンク" data-ui-back data-testid="portfolio-back">'
                                '<p class="ui-links"><a href="../../index.html#tools">← 🧰 Tools</a>'), page
        assert html.count('data-ui-back') == 1, page
        assert "Back to portfolio" not in html, page


# ═══ 🐍 front page (scripts/front_page.py) ═══════════════════════════════════════════════════════════════════════
# The catalog rules and the four notations are Python; the browser only switches, filters and fills AI highlights.

def _front():
    spec = importlib.util.spec_from_file_location('front_page', ROOT / 'scripts/front_page.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text, self.links, self.units = [], [], []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'a' and 'href' in values:
            self.links.append(values['href'])
        if 'data-project' in values:
            self.units.append(values['data-project'])

    def handle_data(self, data):
        self.text.append(data)


def _read(fragment):
    parser = _Text()
    parser.feed(fragment)
    return ''.join(parser.text), parser.links, parser.units


def test_front_page_catalog_shows_active_repositories_and_curation_cannot_override_them():
    front = _front()
    repo = lambda name, **more: {'name': name, 'url': f'https://github.com/myon-bioinformatics/{name}', **more}
    catalog = {'repos': [repo('Kept', description='From GitHub', topics=['python', 'cli']), repo('Legacy', archived=True, topics=['legacy-topic']),
                         repo('Future', description=None, readmeSummary='New README summary', topics=['future-topic']), repo('Bare')]}
    curated = [{'name': 'Kept', 'url': 'https://example.com/stale', 'desc': 'Curated text', 'topics': ['curated-topic', 'python']},
               {'name': 'Removed-repository', 'url': 'https://example.com/removed', 'desc': 'Stale entry'}]
    projects = {p['name']: p for p in front.project_catalog(catalog, curated)}
    assert list(projects) == ['Kept', 'Future', 'Bare']                                  # archived and stale curated entries never show
    assert projects['Kept'] == {'name': 'Kept', 'desc': 'Curated text', 'url': 'https://github.com/myon-bioinformatics/Kept',
                                'topics': ['curated-topic', 'python', 'cli'], 'archived': False}   # the catalog owns the URL
    assert projects['Future']['desc'] == 'New README summary'                            # a refreshed repository needs no curated card
    assert projects['Bare']['desc'] == 'Explore the source and README on GitHub.'
    assert [p['name'] for p in front.project_catalog(catalog, [])] == ['Kept', 'Future', 'Bare']   # no curation at all
    with pytest.raises(ValueError, match='Invalid repository catalog'):                  # a broken catalog fails the build
        front.project_catalog({}, curated)


def test_front_page_notations_carry_the_same_profile_and_projects():
    front = _front()
    profile = json.loads((ROOT / 'profile.json').read_text(encoding='utf-8'))
    projects = front.project_catalog(json.loads((ROOT / 'api/repos.json').read_text(encoding='utf-8')),
                                     json.loads((ROOT / 'projects.json').read_text(encoding='utf-8')))
    assert json.loads(_read(front.profile_html(profile, 'json'))[0]) == profile          # the JSON notation is the data itself
    names = [p['name'] for p in projects]
    urls = sorted({p[key] for p in projects for key in ('url', 'pages', 'page') if p.get(key)})   # 🐙 repository · 🌐 Pages · 📄 portfolio page
    for notation in ('web', 'xml', 'json', 'markdown'):
        text, links, units = _read(front.projects_html(projects, notation))
        assert units == names, notation                                                  # one removable unit per project
        assert sorted(set(links)) == urls, notation
        assert profile['career'][0]['title'] in _read(front.profile_html(profile, notation))[0], notation
    # Without the comma the page script drops after the last shown project, the JSON notation parses back to the catalog.
    listing = front.projects_html(projects, 'json')
    last = listing.rindex(front._LAST_COMMA)
    assert json.loads(_read(listing[:last] + listing[last + len(front._LAST_COMMA):])[0]) == projects
    text = _read(front.projects_html(projects, 'xml'))[0]
    assert text.startswith('<Projects>') and text.endswith('</Projects>') and text.count('<Project name=') == len(projects)
    assert '<script' not in front.profile_html({**profile, 'about': '<script>alert(1)</script>'}, 'web')   # data is escaped


def test_front_page_ai_highlight_templates_have_the_same_slots_in_every_notation():
    front = _front()
    for notation in ('web', 'xml', 'json', 'markdown'):
        frame = front.highlights_html(notation)
        assert frame.count('<template data-item>') == 1, notation
        fields = set(re.findall(r'data-field="(\w+)"', frame))
        assert {'name', 'desc', 'language'} <= fields and fields & {'stars', 'starsLabel'}, (notation, fields)
        assert 'data-href="url"' in frame and 'href="' not in frame.replace('data-href="', ''), notation   # links are filled, never written


def test_front_page_offers_the_shared_colour_themes_and_embeds_no_unsafe_json():
    front = _front()
    ui = pytest.importorskip('pysaiyanweboo')
    page = front.document()
    for name in ui.theme_palettes():
        assert f'<option value="{name}">' in page and f'body[data-ui-theme="{name}"]' in page, name
    assert set(front.MODES) == {'modern', 'xml-like', 'json', 'markdown', 'github-like'}
    data = page[page.index('id="projects-data">') + len('id="projects-data">'):]
    assert '<' not in data[:data.index('</script>')]                                     # nothing can close the script element early


# ═══ 🧭 canonical data (docs/ssot.md) ═══════════════════════════════════════════════════════════════════════
# One owner per fact: api/repos.json (repository facts), projects.json (curation), services.json (endpoints),
# profile.json (person). These are the relationships between them.

SERVICE_KINDS = {'external-profile', 'static-data', 'repository', 'pages', 'mcp-stub'}


def canonical_data_errors(profile: dict, projects: list, catalog: dict, registry: dict) -> list[str]:
    errors = []
    repos = {repo['name']: repo for repo in catalog['repos']}
    services = registry.get('services') or {}
    for project in projects:
        repo = repos.get(project['name'])
        if repo is None:
            errors.append(f"projects.json references unknown repository: {project['name']}")
        elif project.get('url') and project['url'] != repo['url']:  # url is a compatibility field only
            errors.append(f"project URL drift for {project['name']}: {project['url']} != {repo['url']}")

    def url(*path):
        entry = services
        for key in path:
            entry = (entry or {}).get(key)
        return (entry or {}).get('url')

    for path in (('account', 'github'), ('portfolio', 'pages'), ('portfolio', 'profileData'),
                 ('portfolio', 'projectsData'), ('portfolio', 'repositoryCatalog')):
        if not url(*path):
            errors.append(f"services.json is missing required service URL: {'.'.join(path)}")
    if url('portfolio', 'repositoryCatalog') != 'https://myon-bioinformatics.github.io/api/repos.json':
        errors.append('portfolio.repositoryCatalog must point to the canonical repos.json endpoint')
    links = profile.get('links') or {}
    if links.get('portfolio') != url('portfolio', 'pages'):
        errors.append('profile.links.portfolio must match services.portfolio.pages.url')
    if links.get('github') != url('account', 'github'):
        errors.append('profile.links.github must match services.account.github.url')

    def check_entry(path, entry):
        if not isinstance(entry, dict):
            return
        if 'kind' in entry or 'url' in entry:
            if entry.get('kind') not in SERVICE_KINDS:
                errors.append(f"unknown service kind at {path}: {entry.get('kind')}")
            if not entry.get('url'):
                errors.append(f'missing URL at {path}')
            return
        for key, value in entry.items():
            check_entry(f'{path}.{key}', value)

    check_entry('services', services)
    for name, group in (services.get('projects') or {}).items():
        if not isinstance(group, dict):
            errors.append(f'invalid project service group at services.projects.{name}')
            continue
        repo = repos.get(name)
        if repo is None:
            errors.append(f'services.json references unknown repository: {name}')
            continue
        repository_url = (group.get('repository') or {}).get('url') if isinstance(group.get('repository'), dict) else None
        if repository_url and repository_url != repo['url']:
            errors.append(f"repository service URL drift for {name}: {repository_url} != {repo['url']}")
        prefix = f'https://myon-bioinformatics.github.io/{name}/'
        # 🧰 a tool built here from this repository lives at its feature route (TOOL_SOURCES), not at the repository's name
        built_here = tuple(f'https://myon-bioinformatics.github.io/{folder}/{entry}' for repository, folder, entries
                           in PAGES.TOOL_SOURCES.values() if repository == f'myon-bioinformatics/{name}' for entry in entries)
        for service_name, service in group.items():
            if not isinstance(service, dict):
                errors.append(f'invalid service entry at services.projects.{name}.{service_name}')
            elif service.get('kind') in ('pages', 'mcp-stub') and service.get('url') and not service['url'].startswith((prefix, *built_here)):
                errors.append(f'{service_name} URL for {name} must be under {prefix}')
    return errors


def _canonical_data():
    return [json.loads((ROOT / name).read_text(encoding='utf-8'))
            for name in ('profile.json', 'projects.json', 'api/repos.json', 'services.json')]


def test_canonical_data_relationships_hold():
    assert canonical_data_errors(*_canonical_data()) == []


def test_canonical_data_check_reports_drift():
    profile, projects, catalog, registry = _canonical_data()
    name = next(iter(registry['services']['projects']))
    registry['services']['projects'][name]['pages'] = {'kind': 'pages', 'url': 'https://example.test/elsewhere/'}
    projects = projects + [{'name': 'no-such-repository'}]
    registry['services']['portfolio']['broken'] = {'kind': 'unknown-kind', 'url': ''}
    errors = canonical_data_errors(profile, projects, catalog, registry)
    assert 'projects.json references unknown repository: no-such-repository' in errors
    assert f'pages URL for {name} must be under https://myon-bioinformatics.github.io/{name}/' in errors
    assert 'unknown service kind at services.portfolio.broken: unknown-kind' in errors
    assert 'missing URL at services.portfolio.broken' in errors


# ═══ 📱 home screen ═══════════════════════════════════════════════════════════════════════════════════════
# A shortcut or home-screen icon of the portfolio opens index.html with its label and icon (manifest.webmanifest);
# a shortcut of a tool page opens that page. Every local link and asset of these pages resolves.

class PageParser(HTMLParser):
    """<title>, <link> attributes, named <meta> contents, ids, and every href/src of one page."""
    def __init__(self):
        super().__init__()
        self.title, self.links, self.metas, self.ids, self.refs, self._in_title = "", [], {}, set(), [], False
    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        self.ids.update([values["id"]] if "id" in values else [])
        self.links += [values] if tag == "link" else []
        self.metas.update({values["name"]: values.get("content")} if tag == "meta" and "name" in values else {})
        self.refs += [values[key] for key in ("href", "src") if values.get(key)]
        self._in_title = tag == "title"
    def handle_endtag(self, tag):
        self._in_title = False
    def handle_data(self, data):
        self.title += data if self._in_title else ""


def parse_page(path):
    parser = PageParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


def rel_links(page, rel):
    return [link for link in page.links if rel in (link.get("rel") or "").split()]


def png_size(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path
    return "{}x{}".format(*struct.unpack(">II", data[16:24]))


def home_manifest():
    return json.loads((SITE / "manifest.webmanifest").read_text(encoding="utf-8"))


def largest_icon(manifest):
    return max(manifest["icons"], key=lambda icon: int(icon["sizes"].split("x")[0]))


def test_home_screen_shortcut_opens_the_portfolio_with_its_label_and_real_icons():
    manifest = home_manifest()
    # 🏠 The icon opens index.html, the whole site is in scope, and it opens in the browser ("browser"), so the
    # other repositories' Pages it links to keep their back button.
    assert (manifest["id"], manifest["start_url"], manifest["scope"], manifest["display"]) == ("./", "./", "./", "browser")
    page = parse_page(SITE / "index.html")
    assert manifest["name"] == page.title
    assert len(manifest["short_name"]) <= 12                       # longer home-screen labels are cut off
    for icon in manifest["icons"]:
        assert icon["type"] == "image/png" and icon["sizes"] == png_size(SITE / icon["src"]), icon
    assert int(largest_icon(manifest)["sizes"].split("x")[0]) >= 144   # Chromium's smallest home-screen icon


def test_home_screen_index_head_matches_the_manifest():
    page, manifest = parse_page(SITE / "index.html"), home_manifest()
    assert [link["href"] for link in rel_links(page, "manifest")] == ["./manifest.webmanifest"]
    largest = largest_icon(manifest)
    [touch] = rel_links(page, "apple-touch-icon")                  # 🍎 iOS: icon and label come from the page itself
    assert (touch["href"], touch["sizes"]) == ("./" + largest["src"], largest["sizes"])
    assert page.metas["apple-mobile-web-app-title"] == page.metas["application-name"] == manifest["short_name"]
    for icon in rel_links(page, "icon"):
        assert (SITE / icon["href"]).is_file(), icon
        assert icon.get("type") != "image/png" or icon["sizes"] == png_size(SITE / icon["href"]), icon


def test_home_screen_tool_page_shortcuts_open_that_page_and_show_an_icon():
    for name in TOOL_PAGES:
        page = parse_page(SITE / name)
        # 🔗 With the portfolio manifest linked, Android would open index.html instead of this page.
        assert not rel_links(page, "manifest"), name
        label = page.metas["apple-mobile-web-app-title"]         # 🏷️ the <title> would be cut off under the icon
        assert label == page.metas["application-name"] and len(label) <= 12, (name, label)
        for rel in ("icon", "apple-touch-icon"):
            [icon] = rel_links(page, rel)
            if icon["href"].startswith("/tools/mcp/execution/"):   # the lab artwork, built here at deploy time (--record-tools)
                continue
            png_size((SITE / name).parent / icon["href"])
    assert "img-src 'self'" in (SITE / TOOL_PAGES[0]).read_text(encoding="utf-8")   # its CSP lets the icons load


def test_home_screen_every_local_link_and_asset_resolves():
    for name in ("index.html", *TOOL_PAGES):
        page = parse_page(SITE / name)
        for ref in page.refs:
            url = urlparse(ref)
            if url.scheme or ref.startswith("/"):                   # 🌐 other sites, or the lab's Pages on this host
                assert url.scheme == "https" or ref.startswith("/tools/mcp/execution/"), (name, ref)
                continue
            target = ((SITE / name).parent / url.path).resolve() if url.path else SITE / name
            target = target / "index.html" if target.is_dir() else target
            assert target.is_file(), (name, ref)
            if url.fragment and target.suffix == ".html":
                assert url.fragment in parse_page(target).ids, (name, ref)


def test_home_screen_in_chromium_with_a_gif():
    """Chromium reads the manifest, loads every icon, opens start_url, and a tool page keeps its own shortcut.

    The frames, with a sketch of the home-screen tiles, go to test-results/home-screen/home-screen-shortcut-<UTC>.gif.
    """
    sync_api = pytest.importorskip("playwright.sync_api")
    ui = pytest.importorskip("pysaiyanweboo")
    import base64, functools, threading
    from html import escape
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(SITE)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base, manifest, frames = f"http://127.0.0.1:{server.server_port}/", home_manifest(), []
    load = """hrefs => Promise.all(hrefs.map(href => new Promise(done => { const image = new Image();
        image.onload = () => done(image.naturalWidth + "x" + image.naturalHeight); image.onerror = () => done("error"); image.src = href; })))"""
    try:
        with sync_api.sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(channel="chromium")
            except Exception as exc:  # noqa: BLE001 - no browser on this machine
                pytest.skip(f"Chromium is not installed: {exc}")
            page = browser.new_page(viewport={"width": 392, "height": 840}, is_mobile=True, has_touch=True)
            page.route("https://**", lambda route: route.abort())  # no external data or avatars
            page.goto(base + "index.html")
            cdp = page.context.new_cdp_session(page)
            read = cdp.send("Page.getAppManifest")
            assert read["errors"] == [] and read["url"] == base + "manifest.webmanifest"
            app = read["manifest"]
            assert (app["id"], app["startUrl"], app["scope"], app["name"]) == (base, base, base, manifest["name"])
            assert [icon["url"] for icon in app["icons"]] == [base + icon["src"] for icon in manifest["icons"]]
            assert json.loads(read["data"])["short_name"] == manifest["short_name"]
            # Chromium finds nothing missing. It only notes that this is a shortcut rather than an app window
            # ("browser" display, chosen above), and that a test context is incognito.
            reasons = {error["errorId"] for error in cdp.send("Page.getInstallabilityErrors")["installabilityErrors"]}
            assert reasons <= {"manifest-display-not-supported", "in-incognito"}, reasons
            head = page.evaluate("""() => [...document.querySelectorAll('link[rel~="icon"], link[rel="apple-touch-icon"]')]
                .map(link => [link.href, link.sizes.value])""")
            # Icons load in a page of their own: with any route in place, Chromium refuses favicon.ico to new Image().
            probe = browser.new_page()
            probe.goto(base + "manifest.webmanifest")
            sizes = probe.evaluate(load, [base + icon["src"] for icon in manifest["icons"]] + [href for href, _ in head])
            assert sizes[:len(manifest["icons"])] == [icon["sizes"] for icon in manifest["icons"]]
            for (href, declared), actual in zip(head, sizes[len(manifest["icons"]):]):
                assert actual != "error" and (actual in declared.split() if declared else True), (href, declared, actual)
            frames.append((page.screenshot(), "🧬 index.html · manifest ✅ · icons " + " ".join(sizes)))

            # 📱 How the tiles look (a sketch: 64px icon, 80px label): the portfolio on iOS and Android, then each tool page.
            #    An icon served by another repository's Pages shows as 🌐; every label has to fit without "…".
            tiles = [("🍎 iOS", base + largest_icon(manifest)["src"], manifest["short_name"]),
                     ("🤖 Android", base + largest_icon(manifest)["src"], manifest["short_name"])]
            for name in TOOL_PAGES:
                tool = parse_page(SITE / name)
                [touch] = rel_links(tool, "apple-touch-icon")
                local = not touch["href"].startswith("/")
                tiles.append(("📄 " + name.split("/")[1], base + str(Path(name).parent / touch["href"]) if local else None,
                              tool.metas["apple-mobile-web-app-title"]))
            tile_html = "".join(f'<figure><figcaption>{escape(kind)}</figcaption>'
                                + (f'<img src="{src}" alt="" width="64" height="64">' if src else '<b>🌐</b>')
                                + f'<span>{escape(label)}</span></figure>' for kind, src, label in tiles)
            page.set_content(ui.render_document(title="home screen", trusted_html=f"<main>{tile_html}</main>", css=(
                "main{display:flex;flex-wrap:wrap;gap:24px;padding:32px;background:#1e2a3a;min-height:100vh;align-content:flex-start;"
                "font-family:Meiryo,'メイリオ',sans-serif}"
                "figure{margin:0;width:80px;text-align:center;color:#fff;font-size:12px}figcaption{margin-bottom:8px;opacity:.8}"
                "img,b{border-radius:16px;display:block;margin:0 auto 8px;width:64px;height:64px}b{font-size:40px;line-height:64px;background:#2e3e52}"
                "span{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}")))
            page.wait_for_function("() => [...document.images].every(image => image.complete && image.naturalWidth > 0)")
            cut = page.evaluate("() => [...document.querySelectorAll('figure span')].filter(s => s.scrollWidth > s.clientWidth).map(s => s.textContent)")
            assert cut == [], cut
            frames.append((page.screenshot(), "📱 tiles (sketch) · " + " · ".join(label for _, _, label in tiles)))

            page.goto(app["startUrl"])                               # 👆 tapping the shortcut
            assert page.title() == manifest["name"]
            frames.append((page.screenshot(), "👆 start_url → " + page.title()))

            probe.goto(base + "tools/html-import/")                  # no external requests: its CSP allows none
            assert probe.context.new_cdp_session(probe).send("Page.getAppManifest")["url"] == ""   # its shortcut opens this page
            icons = probe.evaluate("""() => [...document.querySelectorAll('link[rel~="icon"], link[rel="apple-touch-icon"]')].map(l => l.href)""")
            assert probe.evaluate(load, icons) == ["32x32", "170x170"]  # the CSP (img-src 'self') lets both load
            page.goto(base + "tools/html-import/")
            frames.append((page.screenshot(), "📄 " + page.title() + " · no manifest · icons 32x32 170x170"))
            page.get_by_test_id("portfolio-back").get_by_role("link").click()
            page.wait_for_url(base + "index.html#tools")
            frames.append((page.screenshot(), "↩️ ← 🧰 Tools → index.html#tools"))

            # 🧰📚 Every demo and project page opens without a script error, keeps its own shortcut, shows the portfolio icons and has the way back.
            demos = browser.new_page(viewport={"width": 392, "height": 840}, is_mobile=True, has_touch=True)
            errors = []
            demos.on("pageerror", lambda error: errors.append(str(error)))
            demo_cdp = demos.context.new_cdp_session(demos)
            for name in [n for n in TOOL_PAGES if n.startswith("tools/demos/")]:
                demos.goto(base + name)
                assert demo_cdp.send("Page.getAppManifest")["url"] == "", name
                icons = demos.evaluate("""() => [...document.querySelectorAll('link[rel~="icon"], link[rel="apple-touch-icon"]')].map(l => l.href)""")
                assert demos.evaluate(load, icons) == ["32x32", "170x170"], name
                assert demos.get_by_test_id("portfolio-back").get_by_role("link").get_attribute("href") == "../../index.html#tools", name
                assert errors == [], (name, errors)
                frames.append((demos.screenshot(), f"🧰 {demos.title()} · {parse_page(SITE / name).metas['apple-mobile-web-app-title']}"))
                run = demos.get_by_role("heading", name="▶ 実行例")
                if run.count():                                     # ▶ the recorded run, on a frame of its own
                    run.evaluate("heading => heading.scrollIntoView({block: 'start'})")
                    frames.append((demos.screenshot(), f"▶ {demos.title()} · {demos.locator('.ui-kv dd').nth(1).text_content()}"[:120]))

            recorder = browser.new_page()
            recorder.set_content(ui.gif_recorder_document())
            recorder.evaluate("o => { window.rec = new UiGif.Recorder(o); }", {"width": 392, "height": 840, "caption": 32})
            recorder.evaluate("items => rec.add(items)", [{"png": base64.b64encode(png).decode("ascii"), "caption": caption,
                                                           "ok": True, "delay": 1200} for png, caption in frames])
            gif = base64.b64decode(recorder.evaluate("() => rec.encodeBase64({})")["gif"])
            browser.close()
    finally:
        server.shutdown()
    target = ui.gif_targets(ROOT / "test-results" / "home-screen", ["home-screen-shortcut"], run_details=["timestamp"])
    target["home-screen-shortcut"].write_bytes(gif)
    assert gif[:6] == b"GIF89a"


# ═══ 📥 HTML import ═══════════════════════════════════════════════════════════════════════════════════════

extractor = PAGES.load_module('html_snapshot', 'tools/vendor/lab/html_snapshot.py')
CASES = json.loads((ROOT / 'tests/fixtures/html-import/cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['name'])
def test_shared_contract(case, monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('fixture extraction must be offline')

    monkeypatch.setattr(socket.socket, 'connect', deny)
    if 'error' in case:
        with pytest.raises(ValueError) as caught:
            extractor.extract(case['html'], case['url'], case['profile'], case['selector'])
        assert str(caught.value) == case['error']
    else:
        result = extractor.extract(case['html'], case['url'], case['profile'], case['selector'])
        result.pop('tag_counts')
        assert result == case['expected']


def test_generated_page_is_current():
    # Built by the site builder and hash-locked (web-ui-assets.lock.json), not kept in git.
    import pysaiyanweboo as ui
    lock = json.loads((ROOT / 'web-ui-assets.lock.json').read_text(encoding='utf-8'))
    served = (SITE / PAGES.HTML_IMPORT_PAGE).read_bytes()
    assert served == PAGES.render_html_import(ui)[PAGES.HTML_IMPORT_PAGE]
    assert hashlib.sha256(served).hexdigest() == lock['pages'][PAGES.HTML_IMPORT_PAGE]
    assert PAGES.HTML_IMPORT_PAGE in (ROOT / '.gitignore').read_text(encoding='utf-8').splitlines()


def test_fixture_oracles_are_explicit():
    # Independent checks of the contract: not just regeneration from Python.
    by_name = {c['name']: c for c in CASES}
    assert by_name['article']['expected']['text'] == 'A Hello world ! Link'
    assert by_name['multiple']['expected']['text'] == 'A nested B'
    assert by_name['multiple']['expected']['scope_count'] == 2
    assert by_name['main']['expected']['text'] == 'Main a b 日'
    assert by_name['links']['expected']['links'] == [
        {'text': 'R', 'url': 'https://example.test/r'},
        {'text': 'X', 'url': 'https://example.test/dir/page#x'},
        {'text': 'A', 'url': 'https://other.test/a'},
        {'text': 'B', 'url': 'https://other.test/b'},
    ]
    assert by_name['whitespace']['expected']['text'] == 'A B C'


# ═══ 🧪 lab publication ═══════════════════════════════════════════════════════════════════════════════════

spec = importlib.util.spec_from_file_location('mcp_lab', ROOT / '_src/tools/mcp_lab.py')
module = importlib.util.module_from_spec(spec)
sys.modules['mcp_lab'] = module  # the tests below import names from it
spec.loader.exec_module(module)
PUBLIC = SITE / 'tools/mcp'      # 🔌 built from the pinned lab checkout (.test-deps/mcp-toolcall-lab) when it is there


@needs_lab
def test_lab_tools_are_built_from_the_lab_commit_with_actions_as_the_report():
    commit = json.loads(_RECEIPT.read_text(encoding='utf-8'))['commits']['mcp-toolcall-lab']
    page = (PUBLIC / 'index.html').read_text()
    for control in ('pages-wiki-form', 'pages-pixiv-source-form', 'pages-pixiv-extract-submit'):
        assert control in page
    assert f'mcp-toolcall-lab/commit/{commit}' in page and f'mcp-toolcall-lab@{commit[:7]}' in page
    assert page.count(module.ACTIONS) >= 2 and 'data-testid="lab-actions-report"' in page   # 🧪 the banner and the report
    assert 'Last Actions summary' not in page and '"verdict"' not in page
    assert (PUBLIC / 'LICENSE').is_file()
    published = {path.name for path in PUBLIC.iterdir() if path.is_file()}
    assert published == {*module.FILES, *module.OPTIONAL, 'LICENSE', 'pixiv-markup.js', 'pixiv-panel.js', 'shared-navigation.mjs'}
    assert not (ROOT / 'tools/mcp').exists()          # nothing of the lab is kept in git; the wrapper is _src/tools/mcp/


def test_lab_pin_is_one_commit_across_workflows():
    """🔌 ci.yml (static, browser) and html-import.yml (Docker) check out the same lab commit for --stage."""
    refs = [ref for name in ('ci.yml', 'html-import.yml') for ref in re.findall(
        r'repository: myon-bioinformatics/mcp-toolcall-lab\n\s+ref: ([0-9a-f]{40})', (ROOT / '.github/workflows' / name).read_text())]
    assert len(refs) == 3 and len(set(refs)) == 1, refs


def test_lab_rebuild_keeps_the_execution_lab_inside_it(tmp_path):
    """🧮 The Tool Lab replaces tools/mcp/ but keeps tools/mcp/execution/ (its own tool, built or ⏸) as it was."""
    package = tmp_path / 'lab/src/mcp_toolcall_lab'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('')
    (package / 'stub_front.py').write_text(
        "import pathlib, sys\nout = pathlib.Path(sys.argv[3]); out.mkdir(parents=True, exist_ok=True)\n"
        "for name in ('pages-hash.js', 'pages-pixiv.js', 'source.js', 'build_meta.json', 'summary.json'): (out / name).write_text('{}')\n"
        "(out / 'pages-wiki.js').write_text('var DEFAULT_TITLE = \"\";')\n"
        "(out / 'index.html').write_text('<html><head></head><body><header>Lab</header><main></main></body></html>')\n")
    (package / 'mcp_toolcall_lab_repository_diagnostics.py').write_text('')
    (tmp_path / 'lab/LICENSE').write_text('MIT')
    site = tmp_path / 'site'
    kept = site / 'tools/mcp/execution/index.html'
    kept.parent.mkdir(parents=True)
    kept.write_text('execution')
    receipt = PAGES.collect_tools(site, {'mcp-toolcall-lab': tmp_path / 'lab'}, {'mcp-toolcall-lab': '0' * 40})
    assert receipt['made'] == ['mcp-toolcall-lab'], receipt
    assert kept.read_text() == 'execution' and not (site / 'tools/mcp/summary.json').exists()
    page = (site / 'tools/mcp/index.html').read_text()
    assert page.count('data-testid="portfolio-back"') == 1 and 'mcp-toolcall-lab@0000000' in page and '🧪 MCP Lab' in page


def test_lab_stage_checks_everything_before_writing(tmp_path):
    built = tmp_path / 'built'; built.mkdir()
    (built / 'index.html').write_text('<html><head></head><body><header>Lab</header></body></html>')
    for name in module.FILES[1:]:
        (built / name).write_text('var DEFAULT_TITLE = "x";' if name == 'pages-wiki.js' else '{}')
    (built / 'mcp-toolcalls.jsonl').write_text('private log')
    (tmp_path / 'LICENSE').write_text('MIT')
    keep = lambda page, path: page
    before = {path.name: path.read_bytes() for path in built.iterdir()}
    with pytest.raises(ValueError):
        module.stage_lab_tools(built, 'main', tmp_path, keep, lambda page, label: page)
    assert {path.name: path.read_bytes() for path in built.iterdir()} == before
    module.stage_lab_tools(built, '0' * 40, tmp_path, keep, lambda page, label: page)
    assert not (built / 'mcp-toolcalls.jsonl').exists() and (built / 'LICENSE').read_text() == 'MIT'


@needs_lab
def test_transferred_javascript_extracts_source_and_preserves_view_routes():
    import subprocess
    js = r'''
const assert = require('node:assert/strict');
const pixiv = require(process.argv[1] + '/pages-pixiv.js');
const route = require(process.argv[1] + '/pages-hash.js');
const result = pixiv.extractSource({title:'Demo',sourceText:'Example original source text'});
assert.equal(result.ok,true);
assert.equal(result.title,'Demo');
assert.ok(result.body.includes('Example original source text'));
assert.equal(pixiv.extractSource({title:'Demo',sourceText:''}).ok,false);
assert.equal(pixiv.parseSourceUrl('https://evil.example/history/Demo/1/source').ok,false);
assert.equal(route.viewFromLocation('#wiki',''),'wiki');
assert.equal(route.viewFromLocation('#pixiv',''),'pixiv');
assert.equal(route.viewFromLocation('#pokemon',''),'pokemon');
assert.equal(route.viewFromLocation('',''),'home');
'''
    subprocess.run(['node', '-e', js, str(PUBLIC)], cwd=ROOT, check=True)


@needs_lab
def test_shared_presentation_replaces_the_lab_styling():
    page = (PUBLIC / 'index.html').read_text()
    assert 'data-ui-theme="modern"' in page
    assert 'href="terminal.css' not in page and not (PUBLIC / 'terminal.css').exists()
    assert 'src="pages-hash.js' not in page
    assert 'data-shared-ui="web-ui"' in page
    assert 'font-family: inherit;' in page
    assert 'generated into the local <code>terminal.css</code>' not in page and 'modern theme' in page


def test_stage_reapplies_shared_runtime(tmp_path):
    built = tmp_path / 'built'; built.mkdir()
    (built / 'index.html').write_text('<html><head><link rel="stylesheet" href="terminal.css?v=1"></head><body><header>Demo</header>'
                                      '<main class="term-page"><pre>Original report</pre></main><script src="pages-hash.js"></script></body></html>')
    for name in module.FILES[1:]:
        (built / name).write_text('var DEFAULT_TITLE = "";' if name == 'pages-wiki.js' else '{}')
    (tmp_path / 'LICENSE').write_text('MIT')
    module.stage_lab_tools(built, '0' * 40, tmp_path, lambda page, path: page, lambda page, label: page)
    page = (built / 'index.html').read_text()
    assert 'data-ui-theme="modern"' in page
    assert '<pre class="ui-output">Original report</pre>' in page
    assert (built / 'shared-navigation.mjs').is_file()


def test_stage_preserves_consumer_niconico_panel_and_routes():
    from mcp_lab import apply_shared_ui, NAVIGATION_BINDING
    source = '''<html><head></head><body><header>Lab</header>
    <a href="#pixiv" data-pages-nav="pixiv">Pixiv</a>
    <section data-pages-view="pixiv"></section></body></html>'''
    page = apply_shared_ui(source)
    assert 'data-pages-nav="niconico"' in page
    assert 'id="pages-niconico-results"' in page
    assert '../niconico/search.js' in page
    assert apply_shared_ui(page).count('data-pages-view="niconico"') == 1
    assert b"niconico:'niconico'" in NAVIGATION_BINDING


@needs_lab
def test_built_lab_keeps_pokemon_panel_and_routes():
    from mcp_lab import NAVIGATION_BINDING
    page = (PUBLIC / 'index.html').read_text()
    assert 'data-pages-nav="pokemon"' in page
    assert 'data-pages-view="pokemon"' in page
    assert 'data-source-fetch' in page
    assert 'data-source-extract' in page
    assert 'source.js' in page
    assert (PUBLIC / 'source.js').is_file()
    assert b"pokemon:'pokemon'" in NAVIGATION_BINDING


def test_execution_is_linked_from_the_card_readme_and_services():
    for path in (SITE / 'index.html', ROOT / 'README.md'):
        assert module.EXECUTION_URL in path.read_text()
    services = json.loads((ROOT / 'services.json').read_text())
    assert services['services']['projects']['mcp-toolcall-lab']['execution']['url'] == module.EXECUTION_URL


@needs_lab
def test_built_lab_example_defaults_are_blank_and_execution_is_linked():
    import subprocess

    class Inputs(HTMLParser):
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'input' and attrs.get('id') == 'pages-wiki-title':
                assert attrs.get('value') == ''

    Inputs().feed((PUBLIC / 'index.html').read_text())
    assert module.EXECUTION_URL in (PUBLIC / 'index.html').read_text()
    subprocess.run(['node', '-e', "require('node:assert/strict').equal(require(process.argv[1]).DEFAULT_TITLE, '')",
                    str(PUBLIC / 'pages-wiki.js')], cwd=ROOT, check=True)


def test_stage_clears_only_example_controls_and_preserves_original_evidence():
    original = b'<header>Demo</header><input id="pages-wiki-title" value="Example City"><p>Article about Example City</p>'
    payload = {'index.html': original, 'pages-wiki.js': b'var DEFAULT_TITLE = "Example City";\nvar content = "Example City";'}
    module.apply_public_examples(payload)
    assert b'value=""' in payload['index.html']
    assert b'Article about Example City' in payload['index.html']
    assert b'var DEFAULT_TITLE = "";' in payload['pages-wiki.js']
    assert b'var content = "Example City";' in payload['pages-wiki.js']
    before = dict(payload)
    module.apply_public_examples(payload)
    assert payload == before


def test_actions_report_replaces_only_the_empty_summary():
    page = ('<p>the actual round-trip is the "Last Actions summary" below.</p><h2>Last Actions summary</h2><p>Allowlisted.</p>'
            '<pre><code class="language-json">{"verdict": null}</code></pre><ul><li>Local: docker</li></ul>')
    report = module.apply_actions_report(page)
    assert 'Last Actions summary' not in report and 'verdict' not in report
    assert module.ACTIONS in report and '<li>Local: docker</li>' in report and 'Test results below' in report
    assert module.apply_actions_report(report) == report
    with pytest.raises(ValueError):
        module.apply_actions_report('<h2>Last Actions summary</h2><table></table>')


@needs_lab
def test_lab_branding_is_idempotent_and_uses_published_absolute_paths():
    from mcp_lab import apply_lab_branding, FAVICON, LOGO
    from urllib.parse import urljoin
    for name in ('index.html', 'repository-diagnostics.html'):
        page = (PUBLIC / name).read_text()
        assert apply_lab_branding(page) == page
        assert page.count('data-lab-brand="favicon"') == 1
        assert page.count('rel="apple-touch-icon"') == 1
        assert page.count('mcp-toolcall-lab-logo.png') == 1
        for asset in (FAVICON, LOGO):
            assert asset in page
            assert urljoin('https://myon-bioinformatics.github.io/tools/mcp/' + name, asset) == 'https://myon-bioinformatics.github.io' + asset
    upstream = '<html><head><link rel="icon" href="assets/old.png"></head><body><header><img src="assets/mcp-toolcall-lab-logo.png"></header></body></html>'
    branded = apply_lab_branding(upstream)
    assert apply_lab_branding(branded) == branded
    assert branded.count('rel="icon"') == 1
    assert 'assets/old.png' not in branded
    assert LOGO in branded


def test_prose_extract_adapter_preserves_whitespace_hooks_and_code_blocks():
    from mcp_lab import apply_prose_extracts, apply_shared_ui
    source = ('<html><head></head><body>'
              '<pre data-testid="pages-pixiv-extract" hidden class="ui-output">A\nB &lt;C&gt;</pre>'
              '<pre class="ui-output" data-testid="pages-wiki-extract">Wiki\ntext</pre>'
              '<pre class="ui-output"><code>print(1)</code></pre></body></html>')
    converted = apply_prose_extracts(source)
    assert '<div data-testid="pages-pixiv-extract" hidden class="ui-output">A\nB &lt;C&gt;</div>' in converted
    assert '<div class="ui-output" data-testid="pages-wiki-extract">Wiki\ntext</div>' in converted
    assert '<pre class="ui-output"><code>print(1)</code></pre>' in converted
    assert apply_prose_extracts(converted) == converted
    assert apply_shared_ui(source) == apply_shared_ui(converted)
    if LAB_BUILT:
        published = (PUBLIC / 'index.html').read_text()
        assert '<div data-testid="pages-pixiv-extract" hidden class="ui-output"></div>' in published
        assert '<div data-testid="pages-wiki-extract" hidden class="ui-output"></div>' in published


# ═══ 💬 cross-repo chat (scripts/chat.py; the page runs it in Pyodide) ═══════════════════════════════════════

CHAT = PAGES._chat()
CHAT_INDEX = {'schema': 'chat-index/1', 'owner': 'myon-bioinformatics',
              'commits': {'onto': 'a' * 40, 'Aoi': 'b' * 40, 'TaxOntOy': 'c' * 40, 'OnTautoLogy': 'd' * 40},
              'files': [['onto', 'docs/graph.json', 120], ['Aoi', 'cycles/c001/outputs/allocation.jsonl', 80],
                        ['Aoi', 'cycles/c003/units.jsonl', 40 * 1024 ** 2], ['TaxOntOy', 'package.json', 30],
                        ['TaxOntOy', 'otl-relations.json', 64], ['OnTautoLogy', 'examples/concepts-20261115.json', 900]],
              'scan_errors': {},
              'tools': [{'name': 'find_municipalities', 'description': 'Find mock municipalities.',
                         'parameters': {'type': 'object', 'properties': {'query': {'type': 'string'}}, 'required': ['query'],
                                        'additionalProperties': False}}],
              'repos': {'onto': 'ONTO: an index linking ontology-related repositories', 'Aoi': 'Hypothesis-driven baseball analytics.',
                        'TaxOntOy': 'TaxOntOy: Taxonomy × Ontology', 'OnTautoLogy': 'Stdlib-only Python graphlib knowledge graph.'}}
CHAT_CONCEPTS = {'schema': 'ontautology-concepts/1',                    # 🧬 a small ledger in OnTautoLogy's shape (both entry forms)
                 'concepts': {'ギター': {'id': 'C001-guitar', 'elements': ['楽器', '弦楽器', '撥弦', 'フレット', '6弦標準']},
                              'ベース': ['楽器', '弦楽器', '撥弦', 'フレット', '4弦標準', '低音主体'],
                              'ウクレレ': ['楽器', '弦楽器', '撥弦', 'フレット', '4弦標準', '小型'],
                              'バイオリン': ['楽器', '弦楽器', '擦弦', '4弦標準', '弓で弾く'],
                              'マリオ': ['ゲームキャラクター', '帽子', '赤色', '兄'], 'ルイージ': ['ゲームキャラクター', '帽子', '緑色', '弟']},
                 'similar': [['ギター', 'ベース'], ['ギター', 'ウクレレ'], ['ギター', 'バイオリン'], ['マリオ', 'ルイージ']],
                 'names': {'ギター': ['英名:Guitar', '略称:ギタ'],      # 🎩 ties; 👻 is ルイージ's (同じ beats 代用), so マリオ's face is 🍄
                           'マリオ': ['英名:Mario', '主役シリーズ:スーパーマリオ', '絵文字略称/似たもの:🍄', '絵文字略称/代用:👻', '絵文字略称:🎩'],
                           'ルイージ': ['同音語:類似', '絵文字略称/同じ:👻', '絵文字略称:🎩', '別名:マリオ']},   # マリオ stays マリオ
                 'name_basis': {'絵文字略称': ['同じ', '代用', '似たもの']}}
CHAT_RAW = {'onto/docs/graph.json': json.dumps({'schema': 'graph/1', 'nodes': [{'id': 'a'}, {'id': 'b'}], 'edges': [['a', 'b']]}),
            'OnTautoLogy/examples/concepts-20261115.json': json.dumps(CHAT_CONCEPTS, ensure_ascii=False),
            'Aoi/cycles/c001/outputs/allocation.jsonl': '{"team": "d", "z": -0.7}\n{"team": "s", "z": 0.2}\n'}


def _chat_fetch(url):
    path = url.split('raw.githubusercontent.com/myon-bioinformatics/', 1)[1]
    name, _, rest = path.partition('/')
    return CHAT_RAW[f'{name}/{rest.split("/", 1)[1]}']


def test_chat_answers_every_command_from_the_fleets_modules():
    """💬 Each command is one Markdown reply built by markdown.py, ascii_artist or cli_args; /help lists them all."""
    say = lambda text: CHAT.respond(text, index={})
    assert all(f'`/{name}' in say('/help') for name in CHAT.COMMANDS)
    assert say('こんにちは') == say('/help')
    flow = say('/flow 入力, 履歴 > 圧縮 > 出力')
    assert '入力 + 履歴\n ↓\n圧縮' in flow and '```mermaid' in flow and 'S1 --> T0' in flow
    table = say('/table 道具,行数;markdown,7284')
    assert '| markdown | 7284 |' in table and '╭' in table
    assert '#   #' in say('/ascii HI') and '╭────╮' in say('/box hi')
    assert '🧭 見出し 1 · 🔗 リンク 1' in say('/md # A\n\n[x](https://example.com)')
    asked = CHAT.ask_html('<think>台帳を探す</think>**TaxOntOy**', 8, 2.0)        # 🤖 reasoning, when there is any, is quoted as 💭
    assert '<blockquote>' in asked and '💭 台帳を探す' in asked and '<strong>TaxOntOy</strong>' in asked and '4.0 tok/s' in asked
    html = CHAT.reply_html('/md <img src=x onerror=alert(1)> **b**')
    assert '<img' not in html and '&lt;img' in html and '<strong>b</strong>' in html


def test_chat_typos_get_what_cli_args_suggests():
    """⌨️ A mistyped command, option or --kind gets "maybe you meant" from cli_args, shown as what to type."""
    assert '⌨️ もしかして `/flow`' in CHAT.respond('/flwo a > b', index={})
    assert '⌨️ もしかして `--kind`' in CHAT.respond('/find --kidn onto', index={})
    assert '⌨️ もしかして `--kind onto`' in CHAT.respond('/find --kind ont', index={})


def test_chat_finds_and_shows_json_and_jsonl_across_repositories():
    """🔎👀 /find (and plain words) search every recorded repository; /show reads the file at its commit into tables."""
    found = CHAT.respond('onto', index=CHAT_INDEX)
    assert 'docs/graph.json' in found and 'otl-relations.json' in found and '/blob/' + 'a' * 40 in found
    assert CHAT.kinds_of('TaxOntOy', 'package.json') == ['onto', 'config'] and CHAT.kinds_of('Aoi', 'x/units.jsonl') == ['jsonl']
    assert [path for _, path, _ in CHAT.find(CHAT_INDEX, kind='jsonl')] == ['cycles/c003/units.jsonl', 'cycles/c001/outputs/allocation.jsonl']
    assert 'Aoi' in CHAT.respond('Aoi jsonl', index=CHAT_INDEX) and 'onto' not in CHAT.respond('/find --repo Aoi', index=CHAT_INDEX).split('|', 5)[-1]
    graph = CHAT.respond('/show onto/docs/graph.json', index=CHAT_INDEX, fetch=_chat_fetch)
    assert '🧬 nodes **2**' in graph and '🧬 edges **1**' in graph and '`schema`' in graph
    jsonl = CHAT.respond('/show Aoi/cycles/c001/outputs/allocation.jsonl', index=CHAT_INDEX, fetch=_chat_fetch)
    assert '🧾 行 **2**' in jsonl and '| team | z |' in jsonl
    assert '🐘' in CHAT.respond('/show Aoi/cycles/c003/units.jsonl', index=CHAT_INDEX, fetch=lambda url: pytest.fail(url))
    assert '❓ 記録にない' in CHAT.respond('/show Aoi/nope.json', index=CHAT_INDEX)
    assert '⏸' in CHAT.respond('onto', index={}) and '⏸' in CHAT.respond('/mcp', index={})


def test_chat_onto_defines_concepts_and_looks_them_up_with_ontautology():
    """🧬 /onto: genus + differentia and the table against what is similar (OnTautoLogy's define_concepts), + for a reverse
    lookup (roundtrip_elements) with the element that would tell the rest apart, and "maybe" for a name the ledger lacks."""
    say = lambda text: CHAT.respond(text, index=CHAT_INDEX, fetch=_chat_fetch)
    listing = say('/onto')
    assert '🧬 **6** 概念' in listing and 'ギター · ベース' in listing and 'OnTautoLogy/examples/concepts-20261115.json@ddddddd' in listing
    guitar = say('/onto ギター')
    assert '### 🧬 ギター' in guitar and '**6弦標準** のもの' in guitar and '✅ これだけ' in guitar
    assert '| 🤝 ベース |' in guitar and '🔑 決め手（それだけで ギター）: 6弦標準' in guitar
    assert '⚠️ 3 つ（ウクレレ・ギター・ベース）' in say('/onto 撥弦 + フレット') and '`/onto 撥弦 + フレット + 4弦標準`' in say('/onto 撥弦 + フレット')
    assert '✅ **ギター** だけ' in say('/onto 撥弦 + 6弦標準')
    assert '⌨️ もしかして: `/onto バイオリン`' in say('/onto バイオリ') and '🫥' in say('/onto 楽器 + 赤色')
    assert '🏷 guitar → **ギター**' in say('/onto guitar') and '### 🧬 ギター' in say('/onto ギタ')      # 🏷 the ledger's names
    assert '### 🧬 🍄 マリオ' in say('/onto Mario') and '❓ 台帳にない' in say('/onto スーパーマリオ') and '❓' in say('/onto 類似')
    assert '→ **ルイージ**' in say('/onto 👻\ufe0f') and '### 🧬 👻 ルイージ' in say('/onto 👻')      # 🏷 絵文字略称, the strongest wins
    assert '🏷 👻 → **ルイージ**（同じ） · ほかに `/onto マリオ`（代用）' in say('/onto 👻')
    assert '🏷 **🎩** は 2 つ: `/onto マリオ` · `/onto ルイージ`' in say('/onto 🎩') and '### 🧬 🍄 マリオ' in say('/onto マリオ')
    assert '⏸' in CHAT.respond('/onto ギター', index={})


def test_chat_guess_finds_every_concept_by_yes_and_no():
    say = lambda text: CHAT.respond(text, index=CHAT_INDEX, fetch=_chat_fetch)
    for target, body in CHAT_CONCEPTS['concepts'].items():
        elements = body['elements'] if isinstance(body, dict) else body
        reply = say('/guess')
        for _ in range(10):
            element = re.search(r'『\*\*(.+?)\*\*』', reply)
            if element is None:
                break
            reply = say('y' if element.group(1) in elements else 'n')
        face = {'マリオ': '🍄 ', 'ルイージ': '👻 '}.get(target, '')
        assert f'候補は **{face}{target}**' in reply and '🎯 それは' not in reply
        assert f'🎯 それは **{face}{target}**' in say('y')
    assert '🔎' in say('y')
    first = say('/guess')
    assert '❔' in say('?') and '`y`（はい）' in say('/guess maybe') and 'おしまい' in say('/guess stop')
    assert 'Q1' in first and '🔎' in say('n')


@pytest.mark.parametrize('final_answer', ['n', '?'])
def test_chat_guess_rejects_an_unknown_with_identical_features(final_answer):
    corpus = {'schema': CHAT_CONCEPTS['schema'], 'concepts': {'うどん': ['麺']},
              'broader': {'麺': ['食品']}, 'maybe': {'うどん': ['小麦']}}

    def fetch(_):
        return json.dumps(corpus)

    say = lambda text: CHAT.respond(text, index=CHAT_INDEX, fetch=fetch)
    assert CHAT.concepts(CHAT_INDEX, fetch)['maybe'] == {'うどん': ['小麦']}
    assert '食品' in say('/guess')
    assert '麺' in say('?')
    prompt = say('y')
    assert '候補は **うどん**' in prompt and '🎯 それは' not in prompt
    assert '確認できなかった' in say(final_answer)
    assert '🔎' in say('y')


def test_chat_runs_olnm_to_list_read_and_calculate():
    """🧷 /olnm runs olnm.py itself: sections, search, "maybe you meant", a one-liner's definition and the calculator; running
    a one-liner stays in the terminal, with the one-line install."""
    say = lambda text: CHAT.respond(text, index={})
    first = say('/olnm')
    assert '🧷 **OLNM**' in first and '`git`' in first and 'OneLaunchNumerousModules/HEAD/olnm.py' in first
    assert 'uvtest' in say('/olnm like uvtets') and 'git push' in say('/olnm show gp') and 'git push' in say('/olnm gp')
    assert '= **42**' in say('/olnm calc 6 mul 7') and '⚠️ ZeroDivisionError' in say('/olnm calc 1/0')
    assert '🌿 gs' in say('/olnm ls git') and 'jsonf' in say('/olnm grep json')
    assert '❓ そのワンライナーはない' in say('/olnm show gpp') and 'gp' in say('/olnm show gpp')
    assert 'git push' in say('/olnm run gp') and '▶️ `olnm doctor` は端末で' in say('/olnm doctor')


def test_chat_ask_stands_on_readme_summaries_concepts_and_files():
    """🤖 /ask's system message carries what the question names: repositories (by name, capitals or summary words, with their
    README summary), the ledger's concepts (by name or 🏷 alias, as genus + differentia) and the recorded files — and stays short."""
    ask = lambda text: json.loads(CHAT.ask_messages(text, CHAT_INDEX, _chat_fetch))
    system, user = ask('/ask OTL と baseball の Guitar は？')
    assert user == {'role': 'user', 'content': 'OTL と baseball の Guitar は？'}
    content = system['content']
    assert ('関係しそうなリポジトリ（README の要約）:\n- OnTautoLogy（OTL）: Stdlib-only Python graphlib knowledge graph.\n'
            '- Aoi: Hypothesis-driven baseball analytics.\n- TaxOntOy（TOO）: TaxOntOy: Taxonomy × Ontology\n') in content   # OTL is in its file
    assert '- ギター: 弦楽器・楽器 のうち、6弦標準 のもの（似たもの: ウクレレ・バイオリン・ベース）' in content
    assert 'リポジトリ: Aoi, OnTautoLogy, onto, TaxOntOy' in content and '記録にあるファイル: TaxOntOy/otl-relations.json' in content
    found = CHAT.grounding('マリオとルイージの違い、オントロジーの台帳はどこ？', CHAT_INDEX, _chat_fetch)
    assert found['concepts'] == ['🍄 マリオ: ゲームキャラクター・帽子 のうち、兄 のもの（似たもの: ルイージ）',
                                 '👻 ルイージ: ゲームキャラクター・帽子 のうち、弟 のもの（似たもの: マリオ）']
    assert [c.split(':')[0] for c in CHAT.grounding('🎩 って誰？', CHAT_INDEX, _chat_fetch)['concepts']] == ['🍄 マリオ', '👻 ルイージ']
    assert 'onto/docs/graph.json' in found['files'] and [r.split('（')[0].split(':')[0] for r in found['repos']] == ['TaxOntOy', 'onto']
    quiet = CHAT.grounding('MAIN の話', CHAT_INDEX, _chat_fetch)                 # AI is not in MAIN, nothing is named
    assert quiet['repos'] == [] and quiet['concepts'] == [] and quiet['files'] == []
    assert CHAT.abbr('PySaiyanWeBoo') == 'PSWB' and CHAT.abbr('Aoi') == '' and CHAT.abbr('CaChereCyCle') == 'CCCC'
    assert len(CHAT.ask_messages('/ask ' + ' '.join(['ギター マリオ ルイージ ベース OTL onto Aoi'] * 3), CHAT_INDEX, _chat_fetch)) < 2400
    assert 'リポジトリ' not in json.loads(CHAT.ask_messages('/ask', {}))[0]['content'].split('。')[-1]


@pytest.mark.parametrize(('errors', 'note'), [({}, ''), ({'Aoi': 'truncated_tree'}, '部分取得 1 件'),
                                            ({'Broken': 'unavailable'}, '取得不可 1 件'), (None, '取得範囲は未記録')])
def test_chat_empty_search_distinguishes_index_coverage(errors, note):
    index = {'commits': {} if errors == {'Broken': 'unavailable'} else {'Aoi': 'b' * 40}, 'files': []}
    if errors is not None:
        index['scan_errors'] = errors
    for query in ('/find never-matches', 'never-matches'):
        reply = CHAT.respond(query, index=index)
        assert '0 件（索引内）' in reply
        assert ('⚠️' in reply) is bool(note)
        assert note in reply
    assert '索引を記録していない' in CHAT.respond('/find', index={})


def test_chat_checks_mcp_tool_calls_against_what_the_lab_advertises():
    """🔌 Only an advertised tool with arguments that fit its schema becomes a tools/call; anything else is refused."""
    say = lambda text: CHAT.respond(text, index=CHAT_INDEX)
    assert '`find_municipalities`' in say('/mcp')
    ok = say('/mcp find_municipalities {"query": "Exampleville"}')
    assert ok.startswith('✅') and '"method": "tools/call"' in ok
    assert '❌' in say('/mcp find_municipalities {"query": 3, "x": 1}') and 'arguments.x' in say('/mcp find_municipalities {"x": 1}')
    refused = say('/mcp find_municipalitis {}')
    assert refused.startswith('❌') and '`find_municipalities`' in refused
    assert 'JSON ではない' in say('/mcp find_municipalities {query}')


def test_chat_compresses_with_talkcompress_and_markdown(monkeypatch):
    """🗂 TalkCompress's compressor (fetched once, here a stand-in) and markdown.py's compact_llm_output."""
    import types
    monkeypatch.setitem(CHAT._STATE, 'talkcompress', types.SimpleNamespace(compress=lambda text: text.replace('As soon as possible', 'ASAP')))
    reply = CHAT.respond('/compress As soon as possible, please.', index={'commits': {'TalkCompress': 'd' * 40}})
    assert 'ASAP, please.' in reply and 'ShorthandSessionEdge @ ddddddd' in reply and '📏 **' in reply
    monkeypatch.setitem(CHAT._STATE, 'talkcompress', None)
    monkeypatch.setitem(CHAT._STATE, 'fetch', lambda url: (_ for _ in ()).throw(OSError(url)))
    monkeypatch.setitem(sys.modules, 'shorthand_session_edge', None)          # not importable here
    assert '⏸ TalkCompress を読めない（OSError）' in CHAT.respond('/compress a\n\n\n\nb', index={})


def test_chat_record_indexes_every_repository_and_the_page_runs_the_pinned_modules(tmp_path, monkeypatch):
    """💬 --record-chat records observed paths and scan errors, the lab's advertised tools and TalkCompress's files;
    the page carries chat.py and exactly the installed markdown / ascii_artist / cli_args, and an index of every example."""
    from io import BytesIO
    from urllib.error import HTTPError

    root = tmp_path / 'root'
    (root / 'api').mkdir(parents=True)
    names = ('TalkCompress', 'mcp-toolcall-lab', 'onto', 'Empty', 'BrokenHead', 'BrokenTree', 'InvalidTree')
    (root / 'api/repos.json').write_text(json.dumps({'repos': [{'name': n, **({'description': '', 'readmeSummary': '📘 [Guide](https://x.test/)  for  ' + 'x' * 200} if n == 'onto' else {})} for n in names] + [{'name': 'Old', 'archived': True}]}))
    trees = {'onto': [('docs/graph.json', 120), ('README.md', 9)], 'TalkCompress': [('x.jsonl', 3)],
             'mcp-toolcall-lab': [('fixtures/prompt_experiments/a.json', 50), ('fixtures/other.json', 2)], 'Empty': []}
    fixture = {'openai': {'request': {'tools': [{'type': 'function', 'function': CHAT_INDEX['tools'][0]}]}}}
    requests = []

    def head(repository):
        if repository.endswith('BrokenHead'):
            raise OSError('unreachable')
        return 'e' * 40

    def open_tree(request, *, timeout):
        name = request.full_url.split('/')[5]
        assert request.full_url == f'https://api.github.com/repos/{PAGES.OWNER}/{name}/git/trees/{"e" * 40}?recursive=1'
        requests.append(name)
        if name == 'BrokenTree':
            raise HTTPError(request.full_url, 503, 'unavailable', None, None)
        if name == 'InvalidTree':
            return BytesIO(b'{"tree": []}')
        return BytesIO(json.dumps({'tree': [{'type': 'blob', 'path': path, 'size': size} for path, size in trees[name]],
                                   'truncated': name == 'onto'}).encode())

    monkeypatch.setattr('urllib.request.urlopen', open_tree)
    raw = lambda repository, commit, path: json.dumps(fixture).encode() if path.endswith('a.json') else f'# {path}'.encode()
    lines = PAGES.record_chat(tmp_path / 'site', root, head=head, raw=raw)
    assert requests == [name for name in names if name != 'BrokenHead']
    assert lines == ['💬 4 repositories · 4 JSON/JSONL · 🔌 1 tools · 🗂 TalkCompress ✅ eeeeeee', '⚠️ onto: truncated_tree',
                     '⏸ BrokenHead: OSError', '⏸ BrokenTree: HTTPError', '⏸ InvalidTree: ValueError']
    index = json.loads((tmp_path / 'site/media/chat/index.json').read_text())
    assert [row[:2] for row in index['files']] == [['TalkCompress', 'x.jsonl'], ['mcp-toolcall-lab', 'fixtures/prompt_experiments/a.json'],
                                                   ['mcp-toolcall-lab', 'fixtures/other.json'], ['onto', 'docs/graph.json']]
    assert [tool['name'] for tool in index['tools']] == ['find_municipalities'] and set(index['commits']) == set(names[:4])
    assert index['repos'] == {'onto': ('📘 Guide for ' + 'x' * 200)[:159] + '…'}           # 🤖 README summaries for /ask, links as their text
    assert index['scan_errors'] == {'onto': 'truncated_tree', 'BrokenHead': 'unavailable', 'BrokenTree': 'unavailable',
                                    'InvalidTree': 'unavailable'}
    say = lambda query: CHAT.respond(query, index=index, fetch=lambda url: pytest.fail(url))
    assert '部分取得 1 件・取得不可 3 件' in say('/find graph') and 'docs/graph.json' in say('/find graph')
    assert '部分取得 1 件' in say('/find missing --repo ONTO') and '取得不可' not in say('/find missing --repo ONTO')
    assert '取得不可 1 件' in say('/find --repo brokentree')
    assert say('/find --repo Empty') == '🔎 📦 Empty: 0 件（索引内）'
    assert '索引の対象外' in say('/find --repo Old')
    assert '部分取得 1 件' in say('/show onto/missing.json')
    assert '取得不可 1 件' in say('/show BrokenTree/missing.json')
    assert '⚠️' not in say('/show Empty/missing.json')
    assert all((tmp_path / 'site/media/chat/talkcompress' / name).is_file() for name in CHAT.TALKCOMPRESS)

    page = (SITE / 'tools/chat/index.html').read_text(encoding='utf-8')
    sources = json.loads(re.search(r'<script type="application/json" id="chat-sources">(.*?)</script>', page, re.S).group(1))
    import importlib.util as util
    assert sources == {'chat.py': (ROOT / 'scripts/chat.py').read_text(encoding='utf-8'),
                       **{f'{n}.py': Path(util.find_spec(n).origin).read_text(encoding='utf-8') for n in CHAT.MODULES}}
    config = json.loads(re.search(r'id="chat-config">(.*?)</script>', page).group(1))
    assert config == {'runtime': CHAT.RUNTIME, 'index': '../../media/chat/index.json', 'base': '../../media/chat/'}
    assert all(html_escape(example) in page for _, _, _, examples in CHAT.COMMANDS.values() for example in examples)
    assert page.count('class="ui-card ui-step"') == sum(len(c[3]) for c in CHAT.COMMANDS.values()) + len(CHAT.TYPOS)
    assert 'data-testid="portfolio-back"' in page and '💬chat-slot' not in page
    front = (SITE / 'index.html').read_text(encoding='utf-8')
    assert 'id="chat"' in front and './tools/chat/' in front and 'Markdown 道具箱' not in front
    assert not (SITE / 'tools/demos/chat.html').exists() and not (SITE / 'tools/demos/index.html').exists()   # 💬 one card, one address; no 🤖 stubs list


def html_escape(text):
    from html import escape
    return escape(text)


STORIES = 'https://huggingface.co/ggml-org/models/resolve/main/tinyllamas/stories260K.gguf'   # 🤖 1.2 MB, for /ask in tests


def test_chat_in_chromium_with_pyodide_and_a_gif():
    """💬 In Chromium, Pyodide runs chat.py: typed and tapped commands, a typo, MCP, the cross-repo index, /show, the 📇 index's
    💬 button, raw HTML stays text, and 🤖 /ask runs llama.cpp (wllama) in the page — on a 1.2 MB model in place of the real one.
    Pyodide and wllama come from jsDelivr; CHAT_MIRROR=DIR serves them from DIR/pyodide/ and DIR/wllama/ (the esm folder), the model
    from DIR/model.gguf and TalkCompress's files from DIR/talkcompress/ (then /compress runs it). Frames go to
    test-results/chat/chat-conversation-<UTC>.gif."""
    sync_api = pytest.importorskip('playwright.sync_api')
    ui = pytest.importorskip('pysaiyanweboo')
    import base64, functools, os, threading
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    mirror = Path(os.environ['CHAT_MIRROR']) if os.environ.get('CHAT_MIRROR') else None
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(SITE)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base, frames, errors = f'http://127.0.0.1:{server.server_port}/', [], []
    cors = {'access-control-allow-origin': '*', 'access-control-expose-headers': 'content-length, content-range, etag'}
    kinds = {'.mjs': 'text/javascript', '.js': 'text/javascript', '.wasm': 'application/wasm', '.json': 'application/json'}

    def route(r):
        url = r.request.url
        for key in ('pyodide', 'wllama'):
            if url.startswith(CHAT.RUNTIME[key]):
                if not mirror:
                    return r.continue_()
                name = url[len(CHAT.RUNTIME[key]):].split('?')[0]
                return r.fulfill(path=str(mirror / key / name), headers={'content-type': kinds.get(Path(name).suffix, 'application/octet-stream'), **cors})
        if url.startswith(CHAT.RUNTIME['model']):
            if mirror:
                return r.fulfill(path=str(mirror / 'model.gguf'), headers={'content-type': 'application/octet-stream', **cors})
            response = r.fetch(url=STORIES)
            return r.fulfill(response=response, headers={**response.headers, **cors})
        if url.startswith('https://raw.githubusercontent.com/'):
            return r.fulfill(body=_chat_fetch(url), headers=cors)
        return r.abort()

    def local_media(r):
        name = r.request.url.split('/media/chat/', 1)[1]
        if name == 'index.json':
            index = CHAT_INDEX | {'scan_errors': {'onto': 'truncated_tree', 'Broken': 'unavailable'}}
            return r.fulfill(body=json.dumps(index), content_type='application/json')
        if mirror and name.startswith('talkcompress/') and (mirror / name).is_file():
            return r.fulfill(path=str(mirror / name))
        return r.fulfill(status=404, body='')

    try:
        with sync_api.sync_playwright() as playwright:
            try:
                browser = ui.launch_chromium(playwright)
            except Exception as exc:  # noqa: BLE001 - no browser on this machine
                pytest.skip(f'Chromium is not installed: {exc}')
            context = browser.new_context(viewport={'width': 640, 'height': 800})
            context.route(lambda url: url.startswith('https://'), route)      # (a 'https://**' glob misses the dynamic import)
            context.route(lambda url: '/media/chat/' in url, local_media)      # the context's routes reach wllama's workers too
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base + 'tools/chat/')
            page.wait_for_function('() => document.documentElement.dataset.chatReady === "true"', timeout=180_000)
            status = page.locator('[data-chat-status]').text_content()
            assert status.startswith('✅ 🐍 3.') and '🔎 6 files' in status, status
            frames.append((page.screenshot(), '💬 ' + status))
            bot = page.locator('[data-chat-who="bot"]')

            def say(text, expect, *, tap=None, done=None):
                count = bot.count()
                if tap:
                    page.locator(tap).click()
                else:
                    page.fill('[data-chat-input]', text)
                    page.press('[data-chat-input]', 'Enter')
                # 💬 PySaiyanWeBoo's chat shows ⏳ at once and turns ➤ back on when the answer is in
                page.wait_for_function('n => document.querySelectorAll("[data-chat-who=bot]").length > n'
                                       ' && !document.querySelector("[data-chat-send]").disabled', arg=count, timeout=300_000)
                if done:
                    page.wait_for_function('t => document.querySelector("[data-chat-who=bot]:last-child").textContent.includes(t)',
                                           arg=done, timeout=300_000)
                reply = bot.last.inner_text()
                assert expect in reply, (text, reply)
                frames.append((page.screenshot(), f'💬 {text or tap}'[:120]))
                return reply

            say('/flow 入力 > 圧縮 > 出力', 'flowchart TB')
            say('/flwo a', 'もしかして /flow')
            say('', 'find_municipalities', tap='.ui-chat-chips [data-chat-say="/mcp"]')
            say('/mcp find_municipalities {"query": "Exampleville"}', 'tools/call')
            assert '部分取得 1 件・取得不可 1 件' in say('onto', 'docs/graph.json')
            assert '部分取得 1 件' in say('/find missing --repo onto', '0 件（索引内）')
            assert '取得不可 1 件' in say('/find --repo Broken', '0 件（索引内）')
            assert '⚠️' not in say('/find missing --repo Aoi', '0 件（索引内）')
            say('/show onto/docs/graph.json', '🧬 nodes 2')
            say('/onto ギター', '6弦標準')                                     # 🧬 OnTautoLogy (ontautology.py) in Pyodide
            for final_answer, expected in [('n', '確認できなかった'), ('y', '🎯 それは ギター')]:
                question = say('/guess', 'Q1')
                for _ in range(10):
                    if '候補は ギター' in question:
                        break
                    element = re.search(r'『(.+?)』', question).group(1)
                    question = say('y' if element in CHAT_CONCEPTS['concepts']['ギター']['elements'] else 'n', 'Q')
                assert '候補は ギター' in question and '🎯 それは' not in question
                say(final_answer, expected)
            say('/olnm calc 6 mul 7', '42')                                  # 🧷 OLNM (olnm.py) in Pyodide
            say('/olnm show gp', 'git push')
            compress = mirror and (mirror / 'talkcompress').is_dir()
            say('/compress As soon as possible, please send me the report.', 'ASAP' if compress else '⏸ TalkCompress')
            say('/md <img src=x onerror="window.pwned=1"> **ok**', '<img src=x')
            assert page.evaluate('() => window.pwned') is None and bot.last.locator('img').count() == 0
            asked = say('/ask TaxOntOy って何？', 'tok/s', done='tok/s')                 # 🤖 llama.cpp answered in the page
            assert '🤖 ' + CHAT.RUNTIME['model'].rsplit('/', 1)[-1] in asked and ' tokens · ' in asked, asked
            page.click('label[for="ui-tabs-chat-1"]')                      # 📇 index: a step's 💬 button sends it
            page.select_option('select[data-ui-choice]', '1')               # 🎨 ASCII art
            frames.append((page.screenshot(), '📇 索引 · 🎨 ASCII art'))
            say('', '╭', tap='.ui-step [data-chat-say^="/box"]')
            assert page.locator('#ui-tabs-chat-0').is_checked() and errors == [], errors
            recorder = browser.new_page()
            recorder.set_content(ui.gif_recorder_document())
            recorder.evaluate('o => { window.rec = new UiGif.Recorder(o); }', {'width': 640, 'height': 800, 'caption': 32})
            recorder.evaluate('items => rec.add(items)', [{'png': base64.b64encode(png).decode('ascii'), 'caption': caption,
                                                           'ok': True, 'delay': 1200} for png, caption in frames])
            gif = base64.b64decode(recorder.evaluate('() => rec.encodeBase64({})')['gif'])
            browser.close()
    finally:
        server.shutdown()
    target = ui.gif_targets(ROOT / 'test-results' / 'chat', ['chat-conversation'], run_details=['timestamp'])
    target['chat-conversation'].write_bytes(gif)
    assert gif[:6] == b'GIF89a'

def test_documents_of_the_site_config_become_sections_of_the_front_page():
    """📄 site.config.json ``documents``: each reviewed .md is a section at ``#id`` (☰ lists it); a new document is a new row, not a new page."""
    front = _front()
    page = front.document()
    assert '<section id="weekly" class="container document" aria-label="🗓️ 週次ノート">' in page and '<h2>🗓️ 週次ノート</h2>' in page
    assert '<h2>📊 日ごと</h2>' in page and '@@DOCUMENTS@@' not in page and 'weekly-markdown' not in page
    two = front.documents_html(ROOT, [{'id': 'weekly', 'title': '🗓️ 週次ノート', 'source': 'docs/weekly-view.md'},
                                      {'id': 'ssot', 'title': '📚 SSOT', 'source': 'docs/ssot.md', 'note': 'a <note>'}])
    assert two.count('<article class="document-markdown">') == 2 and '<section id="ssot" class="container document"' in two
    assert '<p class="section-sub">a &lt;note&gt;</p>' in two and two.count('section-sub') == 1
    assert front.documents_html(ROOT, []) == ''
    for bad in ({'id': 'weekly'}, [{'id': 'Weekly', 'title': 't', 'source': 'docs/ssot.md'}], [{'id': 'a', 'title': 't', 'source': 'docs/ssot.md', 'url': 'x'}],
                [{'id': 'a', 'title': 't', 'source': 'docs/ssot.md'}] * 2, [{'id': 'a', 'title': '', 'source': 'docs/ssot.md'}]):
        with pytest.raises(ValueError):
            front.documents_html(ROOT, bad)


def test_the_front_page_carries_the_shared_header_side_and_foot():
    """🧰 The front page has the parts every tool page has (add_site_chrome): the board reads its description, 🔗 its links, no 🏠
    (it is the home), ☰ ⋯ at the side, and the foot with 🚪 every tool, 🐦 X and 📦 its own size; its old nav, contact and footer are gone."""
    import re
    page = (SITE / 'index.html').read_text(encoding='utf-8')
    body = re.search(r'<body[^>]*>', page)
    assert page[body.end():].startswith('<div class="ui-chrome ui-world-head" id="tools-chrome" data-ui-chrome lang="ja">')
    assert page.count('<div class="ui-chrome') == 1 and page.count('<div class="ui-door-foot">') == 1 and 'class="ui-world-home"' not in page
    board = page[body.end():page.index('<nav class="ui-world-tools">')]
    assert '>MYON<' in board and 'Bioinformatics → Security/Backend engineer.' in board and 'Practical CLI and browser tools in Python' in board
    assert all(href in page for href in ('https://github.com/myon-bioinformatics', 'https://lit.link/myon123', 'https://linktr.ee/myon123'))
    size = re.search(r'<span class="ui-door-size"[^>]*>📦 (\d+) KB</span>', page)
    assert size and abs(int(size[1]) - len(page.encode('utf-8')) / 1024) <= 1 and 'href="https://twitter.com/myonitbusiness"' in page
    assert '<nav class="nav">' not in page and 'site-footer"' not in page and '📬 Contact' not in page
    assert page.count('class="ui-gaze"') == 1 and 'class="ui-gaze"' in page[body.end():page.index('<nav class="ui-world-tools">')]   # 🫧 in the shared header
    assert 'value="./tools/chat/"' in page or './tools/chat/' in page                       # 🚪 the doors lead from the root


def test_a_tool_page_board_reads_its_card():
    """🧰 The board of a tool page starts with what its 🧰 Tools card says (a sentence per item, up to three, 120 characters each)."""
    chrome = PAGES.tools_chrome('../../', description='一つ目。二つ目！ Third one. markdown.py は切らない。五つ目。')
    assert [item['text'] for item in chrome['board']['items'][:4]] == ['一つ目。', '二つ目！', 'Third one.', PAGES.load_module('front_page', 'scripts/front_page.py').PORTAL[0]['title']]
    assert len(chrome['board']['items']) <= 12 and chrome['home'] == '../../index.html#tools'
    assert 'home' not in PAGES.tools_chrome('./', home=False) and PAGES.tools_chrome('./', title='MYON')['board']['title'] == 'MYON'
    assert PAGES.tools_chrome(description='x' * 200)['board']['items'][0]['text'] == 'x' * 119 + '…'
    card = next(card for card in PAGES.load_module('front_page', 'scripts/front_page.py').PORTAL if card.get('id') == 'gif')
    gif = (SITE / 'tools/gif/index.html').read_text(encoding='utf-8')
    assert card['text'].split('。')[0] + '。' in gif[:gif.index('<nav class="ui-world-tools">')]


def test_a_document_table_draws_its_number_columns_as_bars():
    """📊 table_bars: a column of numbers gets a bar per row against the column's largest; the .md itself is an ordinary table, and
    the weekly note's counts add up to what its text says."""
    import markdown as md_market
    front = _front()
    source = (ROOT / 'docs/weekly-view.md').read_text(encoding='utf-8')
    counts = [int(row['PR']) for row in md_market.markdown_table_to_records(source)]           # the first table: a day a row
    assert len(counts) == 7 and sum(counts) == int(re.search(r'マージした PR は (\d+) 本', source)[1]) and 'class=' not in source
    weekly = front.documents_html(ROOT, [{'id': 'weekly', 'title': 't', 'source': 'docs/weekly-view.md'}])
    levels = [int(level) for level in re.findall(r'<td class="document-number">\d+<span class="skill-bar-track" aria-hidden="true">'
                                                 r'<span class="skill-bar-fill" style="--level:(\d+)%"></span></span></td>', weekly)]
    assert levels[:7] == [round(count / max(counts) * 100) for count in counts] and levels.count(100) == weekly.count('<table>') == 2
    assert weekly.count('document-number') == len(levels) and '<td>11-' in weekly                # the dates and labels keep their cells
    body = '<table><tbody>\n<tr><td>a</td><td>1,200</td><td>x</td></tr>\n<tr><td>b</td><td>300</td><td>2</td></tr>\n</tbody></table>'
    drawn = front.table_bars(body)
    assert re.findall(r'--level:(\d+)%', drawn) == ['100', '25'] and '<td>x</td>' in drawn and '<td>2</td>' in drawn   # every cell a number, or none
    for kept in ('<p>no table</p>', '<table><tbody>\n<tr><td>a</td><td>b</td></tr>\n</tbody></table>',
                 '<table><tbody>\n<tr><td>0</td></tr>\n</tbody></table>', '<table><tbody>\n<tr><td align="right">3</td></tr>\n</tbody></table>'):
        assert front.table_bars(kept) == kept


def test_weekly_markdown_fragment_rejects_invalid_paths():
    front = _front()
    with pytest.raises(ValueError):
        front.markdown_fragment(ROOT, '../README.md')
    with pytest.raises(ValueError):
        front.markdown_fragment(ROOT, 'docs/not-found.md')


def test_portfolio_worlds_share_one_engine_and_standalone_stays_self_contained():
    import pysaiyanweboo as ui
    world = PAGES._world()
    css, js = PAGES.WORLD_ASSETS
    lock = json.loads((ROOT / 'web-ui-assets.lock.json').read_text(encoding='utf-8'))
    for asset in (css, js):
        assert hashlib.sha256((SITE / asset).read_bytes()).hexdigest() == lock['outputs'][asset]
    assert (SITE / js).read_text(encoding='utf-8') == world.WORLD_JS
    assert (SITE / css).read_text(encoding='utf-8') == '@layer components{' + world.world_base_css() + '}'
    css_link = '<link rel="stylesheet" href="../world-assets/world.css">'
    js_link = '<script type="module" src="../world-assets/world.js"></script>'
    page = (SITE / PAGES.WORLD_PAGE).read_text(encoding='utf-8')
    files = {str(p.relative_to(SITE)) for p in (SITE / 'tools/demos').glob('*.html')}
    assert files == {PAGES.WORLD_PAGE, *PAGES.WORLD_REDIRECTS}
    for path, fragment in PAGES.WORLD_REDIRECTS.items():
        alias = (SITE / path).read_text(encoding='utf-8')
        assert f'href="world.html#{fragment}"' in alias and 'location.replace(url)' in alias
        assert 'data-world-shell' not in alias and len(alias.encode('utf-8')) < 600
    assert page.count(css_link) == page.count(js_link) == 1
    assert page.index('css/bundle.css') < page.index(css_link)
    assert world.world_base_css() not in page and world.WORLD_JS not in page
    assert page.index(js_link) < page.index('export function bindRpgWorlds') < page.index('js/coordinates.js')
    assert page.index('js/coordinates.js') < page.index("getElementById('tokyo-range')")
    assert page.count('class="ui-button map-point-link"') == 21
    assert page.count('id="world-switcher"') == page.count('id="world-favorites"') == 1
    for route in ('world', 'school', 'tokyo', 'london', 'paris', 'camera'):
        assert f'href="#{route}"' in page and f'id="{route}"' in page
    standalone = world.world_document(world.example_data('school'))
    assert world.world_base_css() in standalone and ui.module_script(world.WORLD_JS) in standalone
    assert 'world-assets/' not in standalone
