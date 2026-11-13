"""🌐 The published site: portal links, HTML import and the lab publication (the set Dockerfile.html-import runs)."""

import hashlib
import importlib.util
import json
import socket
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]


# ═══ 🔗 portal links ══════════════════════════════════════════════════════════════════════════════════════

EXPECTED_PAGES = {
    "https://myon-bioinformatics.github.io/flutter_navigation_basic/",
    "https://myon-bioinformatics.github.io/PySaiyanWeBoo/",
    "https://myon-bioinformatics.github.io/Ironmate/",
    "https://myon-bioinformatics.github.io/Ironmate/tools/",
    "https://myon-bioinformatics.github.io/Ironmate/slides/",
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
    parser.feed((ROOT / "index.html").read_text(encoding="utf-8"))
    assert "tools" in parser.ids
    assert EXPECTED_PAGES <= set(parser.links)

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
    parser.feed((ROOT / "index.html").read_text())
    assert metadata["repository"] not in parser.links
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

    html = (ROOT / "index.html").read_text(encoding="utf-8")
    card_start = html.index('<h3 id="ironmate">Ironmate</h3>')
    card = html[card_start:html.index("</article>", card_start)]
    assert "PPTX対応は計画段階" not in card
    assert "Markdown→PPTX" in card
    assert "試作実装" in card
    assert "ブラウザでスライドを作成" in card
    assert "Open Repository" not in card
    assert "Ironmate/slides/" in card


def test_lab_pages_are_hosted_by_portfolio():
    parser = LinkParser()
    parser.feed((ROOT / "index.html").read_text())
    assert "mcp-toolcall-lab" in parser.ids
    assert "./tools/mcp-toolcall-lab/" in parser.links
    assert (ROOT / "tools/mcp-toolcall-lab/index.html").is_file()


def test_every_tool_page_has_the_same_back_link_first_in_main():
    import re
    pages = [ROOT / "tools/html-import/index.html", ROOT / "tools/mcp-toolcall-lab/index.html",
             ROOT / "tools/mcp-toolcall-lab/repository-diagnostics.html"]
    for page in pages:
        html = page.read_text(encoding="utf-8")
        main = re.search(r"<main[^>]*>", html)
        assert main, page
        after = html[main.end():]
        assert after.startswith('<nav class="portfolio-back" aria-label="Portfolio">'
                                '<a href="../../index.html#tools" data-testid="portfolio-back">'), page
        assert html.count('data-testid="portfolio-back"') == 1, page
        assert "Back to portfolio" not in html, page


# ═══ 📥 HTML import ═══════════════════════════════════════════════════════════════════════════════════════

_scripts = str(ROOT / 'scripts')
sys.path.insert(0, _scripts)
try:
    from vendor_loader import load_module
finally:
    if sys.path and sys.path[0] == _scripts:
        sys.path.pop(0)

extractor = load_module('html_snapshot', 'tools/vendor/lab/html_snapshot.py')
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


def test_exact_vendor_bytes():
    lock = json.loads((ROOT / 'tools/html-import/vendor.lock.json').read_text(encoding='utf-8'))
    for item in lock['sources']:
        assert len(item['commit']) == 40
        assert hashlib.sha256((ROOT / item['path']).read_bytes()).hexdigest() == item['sha256']


def test_generated_page_is_current():
    builder = load_module('build_html_import', 'tools/build_html_import.py')
    assert (ROOT / 'tools/html-import/index.html').read_text(encoding='utf-8') == builder.generate()


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

spec = importlib.util.spec_from_file_location('import_lab_pages', ROOT / 'scripts/import_lab_pages.py')
module = importlib.util.module_from_spec(spec)
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
assert.equal(route.viewFromLocation('',''),'home');
'''
    subprocess.run(['node', '-e', js], cwd=ROOT, check=True)


def test_shared_presentation_keeps_original_report_identity():
    meta=json.loads((PUBLIC/'publication.json').read_text())
    assert meta['source_sha']=='2e581d2cc9683a94568d881a59f0a8e2d87475bb'
    assert meta['source_sha256']['pages-wiki.js']=='9d179d5a8baf64096227db9694b2cf11a1c486d59cf5984444a29a563fd187f5'
    assert meta['source_sha256']['pages-pixiv.js']=='b44157ffc92d6bdcee5d9a10e575ae0fc6f21f91bbbe28776bcbeda48956a8cb'
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
    from lab_shared_ui import apply_shared_ui, NAVIGATION_BINDING
    source = '''<html><head></head><body><header>Lab</header>
    <a href="#pixiv" data-pages-nav="pixiv">Pixiv</a>
    <section data-pages-view="pixiv"></section></body></html>'''
    page = apply_shared_ui(source)
    assert 'data-pages-nav="niconico"' in page
    assert 'id="pages-niconico-results"' in page
    assert '../niconico/search.js' in page
    assert apply_shared_ui(page).count('data-pages-view="niconico"') == 1
    assert b"niconico:'niconico'" in NAVIGATION_BINDING


def test_example_defaults_are_blank_and_execution_is_linked():
    import subprocess
    from html.parser import HTMLParser

    class Inputs(HTMLParser):
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'input' and attrs.get('id') == 'pages-wiki-title':
                assert attrs.get('value') == ''

    Inputs().feed((PUBLIC / 'index.html').read_text())
    for path in (ROOT / 'index.html', ROOT / 'README.md', PUBLIC / 'index.html'):
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
    from lab_branding import apply_lab_branding, FAVICON, LOGO
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
    from lab_branding import FAVICON, LOGO
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
    from lab_shared_ui import apply_prose_extracts, apply_shared_ui
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
