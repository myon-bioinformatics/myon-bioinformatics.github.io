import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pixiv_markup', ROOT / 'scripts/pixiv_markup.py')
markup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(markup)
FIXTURES = json.loads((ROOT / 'tests/fixtures/pixiv-markup.json').read_text())


def test_python_and_browser_share_one_narrow_contract():
    js = "const m=require('./tools/pixiv/markup.js');const fs=require('fs');console.log(JSON.stringify(JSON.parse(fs.readFileSync(0,'utf8')).map(x=>m.extractSource(x.source,x.title||''))))"
    run = subprocess.run(['node', '-e', js], input=json.dumps(FIXTURES), text=True, capture_output=True, cwd=ROOT, check=True)
    assert json.loads(run.stdout) == [markup.extract_source(item['source'], item.get('title', '')) for item in FIXTURES]


def test_plain_star_headings_parent_scope_tables_and_media():
    result = markup.extract_source(FIXTURES[0]['source'])
    assert result['title'] == '試験記事'
    assert [h['heading'] for h in result['headings']] == ['概要', '世界観', '文明描写', '社会構成', '関連イラスト', '関連動画']
    world = result['sections'][1]['body']
    assert '## 文明描写' in world and '## 社会構成' in world
    assert '関連イラスト' not in world
    assert '| **火の国** | [里](里) |' in world
    assert '| **水の国** | 別の里 |' in world
    assert '- **用語**\n  - [下位](用語%28詳細%29)' in world
    assert 'https://www.pixiv.net/artworks/123' in result['body']
    assert 'https://www.youtube.com/watch?v=nlRxufviKuc' in result['body']


def test_fenced_code_emphasis_and_duplicate_sections():
    result = markup.extract_source(FIXTURES[2]['source'])
    assert [h['heading'] for h in result['headings']] == ['本物', '次']
    assert '**太字だけ**' in result['body']
    assert '`[[literal]]`' in result['body']
    assert '*not heading\n# not heading' in result['body']
    duplicate = markup.extract_source('*同名\nfirst\n*同名\nsecond')['sections']
    assert [item['value'] for item in duplicate] == ['0', '1']
    assert [item['body'] for item in duplicate] == ['first', 'second']


def test_normalization_is_idempotent_and_rejects_oversize_input():
    for fixture in FIXTURES:
        normalized = markup.pixiv_to_markdown(fixture['source'])
        assert markup.pixiv_to_markdown(normalized) == normalized
    with pytest.raises(ValueError):
        markup.extract_source('x' * 200001)
    # Many sibling headings must not require quadratic lookahead.
    result = markup.extract_source('*x\ny\n' * 15000)
    assert len(result['sections']) == 15000
    assert result['sections'][-1]['body'] == 'y'


def test_import_reapplies_wrapper_and_generated_select():
    sys.path.insert(0, str(ROOT / 'scripts'))
    from lab_shared_ui import apply_shared_navigation
    source = '<html><head></head><body><div data-testid="pages-pixiv-app"><p data-testid="pages-pixiv-status"></p></div><script src="pages-pixiv.js?v=old"></script></body></html>'
    payload = {'index.html': source.encode(), 'pages-pixiv.js': b'api.autoMount(root);'}
    apply_shared_navigation(payload)
    apply_shared_navigation(payload)
    html = payload['index.html'].decode()
    assert html.count('id="pages-pixiv-heading"') == 1
    assert html.count('src="pixiv-panel.js"') == 1
    assert b'api.autoMount(root);' not in payload['pages-pixiv.js']
    assert payload['pixiv-markup.js'] == (ROOT / 'tools/pixiv/markup.js').read_bytes()
    assert payload['pixiv-panel.js'] == (ROOT / 'tools/pixiv/panel.js').read_bytes()
