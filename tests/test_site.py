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
# the source tree plus the generated files (scripts/project_pages.py --stage).
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

def test_every_active_repository_with_pages_is_one_tap_away():
    """🌐 api/repos.json (has_pages) owns the Pages roots: the 🌐 Pages card and each project card link every one."""
    catalog = json.loads((ROOT / "api/repos.json").read_text())
    pages = {repo["name"]: repo["pages"] for repo in catalog["repos"] if repo.get("pages") and not repo.get("archived")}
    assert len(pages) >= 20 and all(url.startswith("https://myon-bioinformatics.github.io/") and url.endswith("/") for url in pages.values())
    page = (SITE / "index.html").read_text(encoding="utf-8")
    portal = page[page.index('<h3 id="guides">'):]
    parser = LinkParser()
    parser.feed(portal[:portal.index("</article>")])
    assert set(parser.links) == set(pages.values()) - {"https://myon-bioinformatics.github.io/"}   # the portfolio does not link itself
    assert page.count('class="ui-button project-pages"') == len(pages)                         # one 🌐 on each project card
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
    assert 'id="gif-files"' in page and 'accept="image/*"' in page and "UiGif.Recorder" in page
    assert "fetch(" not in page and "XMLHttpRequest" not in page and "localStorage" not in page   # nothing is sent or kept


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
    parser.feed(tools[:tools.index("</section>")])          # the Tools & Demos cards; the project list links every repository
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
    card_start = html.index('<h3 id="ironmate">Ironmate</h3>')
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
    assert "mcp-toolcall-lab" in parser.ids
    assert "./tools/mcp-toolcall-lab/" in parser.links
    assert (ROOT / "tools/mcp-toolcall-lab/index.html").is_file()


# The demos (DEMOS) and project pages (projects.json showcases) come from scripts/project_pages.py; they are tool pages too.
TOOL_PAGES = ("tools/html-import/index.html", "tools/mcp-toolcall-lab/index.html", "tools/mcp-toolcall-lab/repository-diagnostics.html",
              "tools/maps/index.html", "tools/maps/tokyo.html", "tools/gif/index.html", "tools/flow/index.html",
              "tools/repo-map/index.html",
              *sorted(str(path.relative_to(SITE)) for folder in ("demos", "projects") for path in (SITE / "tools" / folder).glob("*.html")))


def test_tools_built_from_other_repositories_never_404():
    """🧰 Without a recording (tests, a failed clone) every entry of a tool built from another repository is a ⏸ page with
    the way back at its own depth; a failed rebuild keeps what was there."""
    for key, (repository, folder, entries) in PAGES.TOOL_SOURCES.items():
        for entry in entries:
            name = f'{folder}/{entry}index.html'
            html = (SITE / name).read_text(encoding='utf-8')
            assert '⏸' in html and f'https://github.com/{repository}' in html, name
            assert f'<a href="{"../" * name.count("/")}index.html#tools">' in html, name
    front = LinkParser()
    front.feed((SITE / "index.html").read_text(encoding="utf-8"))
    assert "./tools/heatmap/" in front.links                                         # 🌡️ the Tools & Demos card opens it
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


def test_every_tool_page_has_the_same_back_link_first_in_main():
    import re
    for page in (SITE / name for name in TOOL_PAGES):
        html = page.read_text(encoding="utf-8")
        main = re.search(r"<main[^>]*>", html)
        assert main, page
        after = html[main.end():]
        assert after.startswith('<nav class="ui-back" aria-label="関連リンク" data-ui-back data-testid="portfolio-back">'
                                '<p class="ui-links"><a href="../../index.html#tools">← 🧭 Tools &amp; Demos</a>'), page
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
        routes = (('tools/' + route for route in PAGES.TOOL_SOURCES['ironmate'][2])
                  if name == 'Ironmate' else (f'tools/{name.lower()}/',))
        built_here = tuple('https://myon-bioinformatics.github.io/' + route for route in routes)
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
            if icon["href"].startswith("/tools/mcp-toolcall-lab/execution/"):   # the lab artwork, built here at deploy time (--record-tools)
                continue
            png_size((SITE / name).parent / icon["href"])
    assert "img-src 'self'" in (SITE / TOOL_PAGES[0]).read_text(encoding="utf-8")   # its CSP lets the icons load


def test_home_screen_every_local_link_and_asset_resolves():
    for name in ("index.html", *TOOL_PAGES):
        page = parse_page(SITE / name)
        for ref in page.refs:
            url = urlparse(ref)
            if url.scheme or ref.startswith("/"):                   # 🌐 other sites, or the lab's Pages on this host
                assert url.scheme == "https" or ref.startswith("/tools/mcp-toolcall-lab/execution/"), (name, ref)
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
            frames.append((page.screenshot(), "↩️ ← 🧭 Tools & Demos → index.html#tools"))

            # 🧰📚 Every demo and project page opens without a script error, keeps its own shortcut, shows the portfolio icons and has the way back.
            demos = browser.new_page(viewport={"width": 392, "height": 840}, is_mobile=True, has_touch=True)
            errors = []
            demos.on("pageerror", lambda error: errors.append(str(error)))
            demo_cdp = demos.context.new_cdp_session(demos)
            for name in [n for n in TOOL_PAGES if n.startswith(("tools/demos/", "tools/projects/"))]:
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

spec = importlib.util.spec_from_file_location('lab_import', ROOT / 'scripts/lab_import.py')
module = importlib.util.module_from_spec(spec)
sys.modules['lab_import'] = module  # the tests below import names from it; loading it leaves sys.path alone
spec.loader.exec_module(module)
PUBLIC = ROOT / 'tools/mcp-toolcall-lab'


def test_published_identity_assets_and_real_tool_controls():
    meta = json.loads((PUBLIC / 'publication.json').read_text())
    assert meta['report_status'] == 'imported_snapshot'
    assert len(meta['source_sha']) == 40
    for name, digest in meta['published_sha256'].items():
        assert hashlib.sha256((PUBLIC / name).read_bytes()).hexdigest() == digest
    page = (PUBLIC / 'index.html').read_text()
    for control in ('pages-wiki-form', 'pages-pixiv-source-form', 'pages-pixiv-extract-submit'):
        assert control in page
    assert 'not a live run' in page
    assert 'mcp-toolcalls.jsonl' not in meta['published_sha256']
    assert 'antipatterns.jsonl' not in meta['published_sha256']


def test_import_is_allowlisted_and_rejects_incomplete_source_before_writing():
    import pytest
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / 'source'; source.mkdir()
        destination = Path(directory) / 'destination'
        for name in module.FILES:
            content = (PUBLIC / name).read_bytes()
            if name == 'index.html':
                content = b'<html><head></head><body><header>Demo</header></body></html>'
            (source / name).write_bytes(content)
        (source / 'mcp-toolcalls.jsonl').write_text('private log')
        (source / 'antipatterns.jsonl').write_text('private log')
        module.import_export(source, destination)
        assert not (destination / 'mcp-toolcalls.jsonl').exists()
        assert not (destination / 'antipatterns.jsonl').exists()
        before = (destination / 'index.html').read_bytes()
        (source / 'build_meta.json').write_text('{"sha":"main"}')
        with pytest.raises(ValueError):
            module.import_export(source, destination)
        assert (destination / 'index.html').read_bytes() == before


def test_transferred_javascript_extracts_source_and_preserves_view_routes():
    import subprocess
    js = r'''
const assert = require('node:assert/strict');
const pixiv = require('./tools/mcp-toolcall-lab/pages-pixiv.js');
const route = require('./tools/mcp-toolcall-lab/pages-hash.js');
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
    subprocess.run(['node', '-e', js], cwd=ROOT, check=True)


def test_shared_presentation_keeps_original_report_identity():
    meta=json.loads((PUBLIC/'publication.json').read_text())
    assert meta['source_sha']=='6af885d90f7f0b04ab5a29759404130fece946e2'
    assert meta['source_sha256']['pages-wiki.js']=='9d179d5a8baf64096227db9694b2cf11a1c486d59cf5984444a29a563fd187f5'
    assert meta['source_sha256']['pages-pixiv.js']=='c19d6a41df02ed6e2ca33d0b9f0291e8db92cbbdc48c2208adcda9b4b3848ff1'
    assert meta['presentation']['owner']=='myon-bioinformatics/PySaiyanWeBoo'
    assert meta['source_sha256']['index.html']!=meta['published_sha256']['index.html']
    assert 'shared-navigation.mjs' not in meta['source_sha256']
    assert 'shared-navigation.mjs' in meta['published_sha256']
    page=(PUBLIC/'index.html').read_text()
    assert 'data-ui-theme="modern"' in page
    assert 'href="terminal.css' not in page
    assert 'src="pages-hash.js' not in page
    assert 'data-shared-ui="web-ui"' in page
    assert 'font-family: inherit;' in page


def test_reimport_reapplies_shared_runtime_and_records_both_hashes():
    with tempfile.TemporaryDirectory() as directory:
        source=Path(directory)/'source';source.mkdir()
        destination=Path(directory)/'publication'
        for name in module.FILES:
            content=(PUBLIC/name).read_bytes()
            if name=='index.html':
                content=b'<html><head><link rel="stylesheet" href="terminal.css?v=1"></head><body><header>Demo</header><main class="term-page"><pre>Original report</pre></main><script src="pages-hash.js"></script></body></html>'
            (source/name).write_bytes(content)
        manifest=module.import_export(source,destination)
        assert manifest['source_sha256']['index.html']==hashlib.sha256((source/'index.html').read_bytes()).hexdigest()
        assert 'data-ui-theme="modern"' in (destination/'index.html').read_text()
        assert '<pre class="ui-output">Original report</pre>' in (destination/'index.html').read_text()
        assert (destination/'shared-navigation.mjs').is_file()
        assert manifest['presentation']['owner']=='myon-bioinformatics/PySaiyanWeBoo'


def test_reimport_preserves_consumer_niconico_panel_and_routes():
    from lab_import import apply_shared_ui, NAVIGATION_BINDING
    source = '''<html><head></head><body><header>Lab</header>
    <a href="#pixiv" data-pages-nav="pixiv">Pixiv</a>
    <section data-pages-view="pixiv"></section></body></html>'''
    page = apply_shared_ui(source)
    assert 'data-pages-nav="niconico"' in page
    assert 'id="pages-niconico-results"' in page
    assert '../niconico/search.js' in page
    assert apply_shared_ui(page).count('data-pages-view="niconico"') == 1
    assert b"niconico:'niconico'" in NAVIGATION_BINDING


def test_reimport_preserves_consumer_pokemon_panel_and_routes():
    from lab_import import NAVIGATION_BINDING
    page = (PUBLIC / 'index.html').read_text()
    assert 'data-pages-nav="pokemon"' in page
    assert 'data-pages-view="pokemon"' in page
    assert 'data-source-fetch' in page
    assert 'data-source-extract' in page
    assert 'source.js' in page
    assert (PUBLIC / 'source.js').is_file()
    assert b"pokemon:'pokemon'" in NAVIGATION_BINDING


def test_example_defaults_are_blank_and_execution_is_linked():
    import subprocess
    from html.parser import HTMLParser

    class Inputs(HTMLParser):
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'input' and attrs.get('id') == 'pages-wiki-title':
                assert attrs.get('value') == ''

    Inputs().feed((PUBLIC / 'index.html').read_text())
    for path in (SITE / 'index.html', ROOT / 'README.md', PUBLIC / 'index.html'):
        assert module.EXECUTION_URL in path.read_text()
    services = json.loads((ROOT / 'services.json').read_text())
    assert services['services']['projects']['mcp-toolcall-lab']['execution']['url'] == module.EXECUTION_URL
    subprocess.run(['node', '-e', "require('node:assert/strict').equal(require('./tools/mcp-toolcall-lab/pages-wiki.js').DEFAULT_TITLE, '')"], cwd=ROOT, check=True)


def test_import_clears_only_example_controls_and_preserves_original_evidence():
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


def test_lab_branding_is_idempotent_and_uses_published_absolute_paths():
    from lab_import import apply_lab_branding, FAVICON, LOGO
    from urllib.parse import urljoin
    for name in ('index.html', 'repository-diagnostics.html'):
        page = (PUBLIC / name).read_text()
        assert apply_lab_branding(page) == page
        assert page.count('data-lab-brand="favicon"') == 1
        assert page.count('rel="apple-touch-icon"') == 1
        assert page.count('mcp-toolcall-lab-logo.png') == 1
        for asset in (FAVICON, LOGO):
            assert asset in page
            assert urljoin('https://myon-bioinformatics.github.io/tools/mcp-toolcall-lab/' + name, asset) == 'https://myon-bioinformatics.github.io' + asset
    upstream = '<html><head><link rel="icon" href="assets/old.png"></head><body><header><img src="assets/mcp-toolcall-lab-logo.png"></header></body></html>'
    branded = apply_lab_branding(upstream)
    assert apply_lab_branding(branded) == branded
    assert branded.count('rel="icon"') == 1
    assert 'assets/old.png' not in branded
    assert LOGO in branded


def test_reimport_applies_branding_without_changing_source_identity():
    from lab_import import FAVICON, LOGO
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / 'source'; source.mkdir()
        destination = Path(directory) / 'publication'
        for name in (*module.FILES, *module.OPTIONAL):
            (source / name).write_bytes((PUBLIC / name).read_bytes())
        before = {name: (source / name).read_bytes() for name in (*module.FILES, *module.OPTIONAL)}
        manifest = module.import_export(source, destination)
        for name in ('index.html', 'repository-diagnostics.html'):
            page = (destination / name).read_text()
            assert page.count(FAVICON) == 2 and page.count(LOGO) == 1
            assert manifest['source_sha256'][name] == hashlib.sha256(before[name]).hexdigest()
            assert manifest['published_sha256'][name] == hashlib.sha256((destination / name).read_bytes()).hexdigest()
        assert all((source / name).read_bytes() == content for name, content in before.items())
        assert manifest['source_sha'] == json.loads(before['build_meta.json'])['sha']


def test_prose_extract_adapter_preserves_whitespace_hooks_and_code_blocks():
    from lab_import import apply_prose_extracts, apply_shared_ui
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
    published = (PUBLIC / 'index.html').read_text()
    assert '<div data-testid="pages-pixiv-extract" hidden class="ui-output"></div>' in published
    assert '<div data-testid="pages-wiki-extract" hidden class="ui-output"></div>' in published
