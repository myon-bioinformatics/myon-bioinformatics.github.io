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
                content = b'<html><body><header>Demo</header></body></html>'
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
