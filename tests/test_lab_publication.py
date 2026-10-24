import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
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
    assert meta['source_sha']=='e51e059accd1a78fb704162b3d11ccb701a34ec7'
    assert meta['source_sha256']['pages-wiki.js']=='9d179d5a8baf64096227db9694b2cf11a1c486d59cf5984444a29a563fd187f5'
    assert meta['source_sha256']['pages-pixiv.js']=='b44157ffc92d6bdcee5d9a10e575ae0fc6f21f91bbbe28776bcbeda48956a8cb'
    assert meta['presentation']['owner']=='myon-bioinformatics/web-ui'
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
        assert manifest['presentation']['owner']=='myon-bioinformatics/web-ui'


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
            assert page.count(FAVICON) == 1 and page.count(LOGO) == 1
            assert manifest['source_sha256'][name] == hashlib.sha256(before[name]).hexdigest()
            assert manifest['published_sha256'][name] == hashlib.sha256((destination / name).read_bytes()).hexdigest()
        assert all((source / name).read_bytes() == content for name, content in before.items())
        assert manifest['source_sha'] == json.loads(before['build_meta.json'])['sha']
