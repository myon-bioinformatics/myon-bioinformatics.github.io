"""Generate the shared browser assets from the pinned PySaiyanWeBoo dependency.

The generator is the ``pysaiyanweboo`` module from the ``pages`` dependency group (a git dependency
pinned by commit in ``pyproject.toml``; ``uv run --locked --only-group pages`` installs it). ``web-ui-assets.lock.json`` records that commit and the
SHA-256 of every output, so a build fails closed when the installed module is not the
pinned commit or when its output drifted from the lock. The generated files are not kept in git: ``--output DIR``
writes them (Pages overlays them on its build), ``--stage DIR`` writes the whole site for tests and local previews,
and ``--refresh-lock`` rewrites the lock after the pin moves.

The demos are the 🌍 world (scripts/world.py: the travel world, 🏫 the school, 🗼 the parallel cities, 🎬 the camera), the 🤖 MCP / 🔁 API
stubs (below; both moved here from PySaiyanWeBoo) and PySaiyanWeBoo's mocks (an in-page MCP server, a JUnit reader), published
with the portfolio's way back, shortcut label and icons. ``tools/projects/`` gives every project in ``projects.json`` that
has a ``showcase`` a page of its own, Pages or not: its icon and media at a fixed commit, and one recorded run.
``--record NAME=CHECKOUT`` reruns that command in a checkout of exactly that commit and stores the output. A showcase
with ``scripts`` also gets a 🧰 table of the scripts its globs match there: each one's own description (module docstring,
or the leading ``//`` comment of a JS module) and, for a script that declares argparse / cli_args, the usage line of
its ``--help``, recorded by the same ``--record``
so the list follows the code instead of being written by hand. ``--advance`` (run daily by repos-api.yml) moves every
showcase to the newest commit of its repository and records it there, keeping the old pin when that commit lacks the
icon or media, or when the run that used to succeed now fails.

``tools/html-import/index.html`` (the HTML import tool page) is built here too and hash-locked with the other pages.
Every generated or imported tool page gets the same way back and shortcut label: ``add_back_nav()`` and
``add_home_label()`` (scripts/lab_import.py calls them for the lab pages). ``load_module()`` loads a file of this
repository by path (a sibling script or a vendored module) without touching ``sys.path``.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import html
import importlib.util
import json
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
ASSET_BASE = 'tools/vendor/web-ui/'
ASSETS = ('css/base.css', 'css/components.css', 'css/themes/modern.css',
          'css/tokens.css', 'js/navigation.js', 'js/ui.js', 'js/controls.js',
          'js/coordinates.js')
STYLESHEET_BUNDLES = {'css/bundle.css': 'bundled_css', 'css/core.css': 'core_css'}
DISTRIBUTION = 'pysaiyanweboo'
DEMO_BASE = 'tools/demos/'
PROJECT_BASE = 'tools/projects/'
HTML_IMPORT_PAGE = 'tools/html-import/index.html'
HTML_IMPORT_MODULE = 'tools/html-import/extract.mjs'
MAP_PAGES = {'tools/maps/index.html', 'tools/maps/tokyo.html'}

# 🧰 name -> (how it is built from pysaiyanweboo, shortcut label, title, summary): the only list of demos.
DEMOS = {
    'world': (lambda ui: world_page('overworld'), '🌍 ワールド', 'World',
              '🚪 で土地をわたる旅のワールド：絵文字のキャラで歩き、時刻・お気に入り・地図・言語を切り替える'),
    'school': (lambda ui: world_page('school'), '🏫 スクール', 'School',
               '教室を歩く：絵文字を選び、タップ・矢印キー・パッドで机のあいだを移動（机・黒板・棚には入らない）'),
    'cities': (lambda ui: world_page('cities'), '🗼 パラレル', 'Parallel cities',
               'パラレル東京・リバースロンドン・フェイクパリ：緯度・経度から、駅から駅へ歩く'),
    'world-shots': (lambda ui: world_page('world'), '🎬 カメラ', 'World camera',
                    'ページ遷移なしの1ページ：スクロールで場面、ドラッグ・ホイール・ピンチで地図を動かしスポットを開く'),
    'mcp-stub': (lambda ui: stub_document(ui, EXAMPLE_STUBS['mcp']), '🤖 MCP stub', 'MCP stub', '通信しない MCP のスタブ：ツール名を入れて結果と証跡を見る'),
    'api-stub': (lambda ui: stub_document(ui, EXAMPLE_STUBS['api']), '🔁 API stub', 'API stub', '通信しない API のスタブ：パスを送って結果と証跡を見る'),
    'mcp-lab': (lambda ui: ui.mcp_document(), '🔌 MCP試験', 'MCP lab', 'ページ内で動く MCP サーバーのモック：新旧の protocol、PKCE、ヘッダー名、Bearer、OAuth メタデータ'),
    'test-report': (lambda ui: ui.report_document(), '🧾 JUnit', 'Test report', 'JUnit の結果を貼るか開いて読み、前回と比べて新規・再発・解消を分ける'),
}


@functools.lru_cache(maxsize=None)
def _world() -> ModuleType:
    """🌍 scripts/world.py (the world engine and its specs), loaded once."""
    return load_module('world', 'scripts/world.py')


def world_page(name: str) -> str:
    """🌍 A world spec of scripts/world.py as one page, its body in <main> so the way back has its place (as in Parallel Tokyo)."""
    page = _world().world_document(_world().example_data(name))
    body = '<body data-ui-theme="modern">'
    if page.count(body) != 1 or page.count('</body>') != 1:
        raise ValueError(f'world page {name} has no single body')
    return page.replace(body, body + '<main>', 1).replace('</body>', '</main></body>', 1)


# --- 🤖 MCP stub · 🔁 API stub (moved from PySaiyanWeBoo): a request bar, a result, evidence and history; nothing is sent -----
STUB_SCHEMA = 'web-ui-stub/1'
# bindStub: one text input to a handler (needs setText / prettyJson from PySaiyanWeBoo's ui.js), then the mock evaluator ($input -> the query).
STUB_JS = r"""export function bindStub({input="#query",run="#run",output="#output",form="#stub-form",handler}){const q=document.querySelector(input),b=document.querySelector(run),f=document.querySelector(form);if(!q||!b)return;const execute=async event=>{event?.preventDefault();b.disabled=true;try{const result=await handler(q.value);setText(output,typeof result==="string"?result:prettyJson(result))}catch(error){setText(output,`Error: ${error?.message??error}`)}finally{b.disabled=false}};(f??b).addEventListener(f?"submit":"click",execute)}
const fill=(t,q)=>typeof t==="string"?t.replaceAll("$input",()=>q):Array.isArray(t)?t.map(x=>fill(x,q)):t&&typeof t==="object"?Object.fromEntries(Object.entries(t).map(([k,v])=>[k,fill(v,q)])):t;
"""


def stub_response(template, query: str):
    """What the mock answers for ``query``: ``template`` with every "$input" replaced by the query (same rule as the page)."""
    if isinstance(template, str):
        return template.replace('$input', query)
    if isinstance(template, list):
        return [stub_response(item, query) for item in template]
    if isinstance(template, dict):
        return {key: stub_response(value, query) for key, value in template.items()}
    return template


def stub_validate(spec) -> dict:
    """Checked ``web-ui-stub/1`` spec: id, title, heading, lead, tags, field, run, evidence, history and the mock template."""
    text, token = _world()._world_text, _world()._WORLD_ID
    keys = {'schema', 'id', 'title', 'heading', 'lead', 'tags', 'field', 'run', 'evidence', 'history', 'mock'}
    if not isinstance(spec, dict) or spec.get('schema') != STUB_SCHEMA or set(spec) - keys:
        raise ValueError(f'expected schema {STUB_SCHEMA} with keys {sorted(keys)}')
    stub_id = spec.get('id', 'stub')
    if not isinstance(stub_id, str) or not token.fullmatch(stub_id):
        raise ValueError('id must be a lowercase token that starts with a letter')
    tags = spec.get('tags', [])
    if not isinstance(tags, list) or len(tags) > 6:
        raise ValueError('tags must list at most 6 entries')
    field = spec.get('field')
    if not isinstance(field, dict) or set(field) - {'label', 'placeholder', 'value'} or 'label' not in field:
        raise ValueError('field has a label and optionally a placeholder or a value')
    mock = spec.get('mock', {'status': 'stub', 'query': '$input'})
    try:
        encoded_mock = json.dumps(mock, allow_nan=False)
        mock = json.loads(encoded_mock)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError('mock must be finite JSON data') from exc
    if len(encoded_mock) > 4000:
        raise ValueError('mock must be at most 4000 characters of JSON')
    return {'schema': STUB_SCHEMA, 'id': stub_id, 'title': text(spec.get('title', 'Stub'), 'title', 80),
            'heading': text(spec.get('heading', 'Stub Explorer'), 'heading', 80),
            'lead': text(spec.get('lead', ''), 'lead', 200, required=False),
            'tags': [text(tag, 'tag', 24) for tag in tags],
            'field': {'label': text(field['label'], 'field label', 40),
                      'placeholder': text(field.get('placeholder', ''), 'placeholder', 120, required=False),
                      'value': text(field.get('value', ''), 'value', 120, required=False)},
            'run': text(spec.get('run', 'Run'), 'run', 24),
            'evidence': text(spec.get('evidence', ''), 'evidence', 200, required=False),
            'history': text(spec.get('history', ''), 'history', 200, required=False), 'mock': mock}


def stub_html(spec, *, heading_level: int = 1) -> str:
    """The stub workspace (request bar, result, evidence, history) with ids prefixed by the spec's id; text is escaped."""
    s = stub_validate(spec)
    esc = html.escape
    level = heading_level if type(heading_level) is int and 1 <= heading_level <= 6 else 1
    sid, field = s['id'], s['field']
    attrs = (f' placeholder="{esc(field["placeholder"], quote=True)}"' if field['placeholder'] else '') + \
            (f' value="{esc(field["value"], quote=True)}"' if field['value'] else '')
    tags = ''.join(f'<span class="ui-tag">{esc(tag)}</span>' for tag in s['tags'])
    mock = json.dumps(s['mock'], ensure_ascii=False).replace('</', '<\\/')
    return (f'<div class="stub-shell" id="{sid}"><header class="stub-header"><div><h{level} class="ui-title">{esc(s["heading"])}</h{level}>'
            f'<p class="ui-muted">{esc(s["lead"])}</p></div><div class="stub-meta">{tags}</div></header>'
            f'<section class="ui-panel"><form class="stub-toolbar" id="{sid}-form"><fieldset><legend>Stub request</legend>'
            f'<label for="{sid}-query">{esc(field["label"])}</label><input class="ui-input" id="{sid}-query"{attrs}>'
            f'<button class="ui-button" id="{sid}-run" type="submit">{esc(s["run"])}</button></fieldset></form>'
            '<p class="stub-status ui-muted">Endpoint: <span class="stub-endpoint">consumer-owned</span></p></section>'
            f'<div class="stub-workspace"><section class="ui-panel stub-result"><h2>Result</h2>'
            f'<pre class="ui-output" id="{sid}-output" aria-live="polite">Ready.</pre></section>'
            '<aside aria-label="Supporting information"><section class="ui-card stub-evidence"><h2>Evidence</h2>'
            f'<p class="ui-muted">{esc(s["evidence"])}</p></section><section class="ui-card stub-history"><h2>History</h2>'
            f'<p class="ui-muted">{esc(s["history"])}</p><div class="stub-actions"><button class="ui-button" type="button">Export</button>'
            f'<button class="ui-button" type="button">Clear</button></div></section></aside></div>'
            f'<script type="application/json" id="{sid}-mock">{mock}</script></div>')


def stub_script(ui, *specs) -> str:
    """One inline module for any number of stubs on a page: PySaiyanWeBoo's ui.js, STUB_JS and one bind per stub."""
    binds = ''.join(
        f'bindStub({{input:"#{s["id"]}-query",run:"#{s["id"]}-run",output:"#{s["id"]}-output",form:"#{s["id"]}-form",'
        f'handler:q=>fill(JSON.parse(document.getElementById("{s["id"]}-mock").textContent),q)}});\n'
        for s in (stub_validate(spec) for spec in specs))
    return ui.EMBEDDED_UI_JS + STUB_JS + binds


def stub_document(ui, spec, *, theme: str = 'modern') -> str:
    """A single-file page for one stub."""
    s = stub_validate(spec)
    return ui.render_document(trusted_html='<main class="ui-page">' + stub_html(s) + '</main>'
                              + ui.module_script(stub_script(ui, s)), title=s['title'], theme=theme, css=ui.bundled_css())


EXAMPLE_STUBS = {
    'mcp': {'schema': STUB_SCHEMA, 'id': 'mcp', 'title': 'MCP Stub', 'heading': 'MCP Stub Explorer',
            'lead': 'Protocol behavior stays with the consumer; web-ui supplies presentation and generic interaction.',
            'tags': ['mcp', 'ready'], 'field': {'label': 'Tool or filter', 'placeholder': 'tools/list'}, 'run': 'Run',
            'evidence': 'Trace, source, SHA, or request metadata can be rendered here by the consumer.',
            'history': 'Consumer-owned history/export controls.',
            'mock': {'kind': 'mcp', 'query': '$input', 'status': 'stub'}},
    'api': {'schema': STUB_SCHEMA, 'id': 'api', 'title': 'API Stub', 'heading': 'API Stub Explorer',
            'lead': 'A generic request/result surface without API-specific logic in web-ui.',
            'tags': ['api', 'ready'], 'field': {'label': 'Path', 'value': '/api/example'}, 'run': 'Send',
            'evidence': 'Status, headers, provenance, or timing metadata belongs here.',
            'history': 'Consumer-owned request history and export actions.',
            'mock': {'method': 'GET', 'path': '$input', 'status': 200, 'body': {'stub': True}}},
}


def installed_commit(distribution: str = DISTRIBUTION) -> str:
    """The git commit the installed generator came from (pysaiyanweboo.installed_commit, i.e. pip's install record)."""
    if distribution != DISTRIBUTION:
        raise ValueError(f'{distribution} is not installed (uv run --locked --only-group pages)')
    try:
        import pysaiyanweboo
    except ImportError as exc:
        raise ValueError(f'{distribution} is not installed (uv run --locked --only-group pages)') from exc
    commit = pysaiyanweboo.installed_commit()
    if not commit:
        raise ValueError(f'{distribution} was not installed from its git source')
    return commit


def pinned_commit(root: Path = ROOT) -> str:
    """Read the immutable dependency pin ([tool.uv.sources] in pyproject.toml); refresh must never adopt another install."""
    import tomllib
    sources = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8')).get('tool', {}).get('uv', {}).get('sources', {})
    source, rev = sources.get(DISTRIBUTION, {}), sources.get(DISTRIBUTION, {}).get('rev', '')
    if source.get('git') != 'https://github.com/myon-bioinformatics/PySaiyanWeBoo' or not re.fullmatch(r'[0-9a-f]{40}', rev):
        raise ValueError('expected one full PySaiyanWeBoo commit pin')
    return rev


def verify_pin(commit: str, root: Path = ROOT) -> None:
    if commit != pinned_commit(root):
        raise ValueError('installed generator differs from the pyproject.toml pin')


def render(ui) -> dict[str, bytes]:
    """Every public asset rendered by the generator module, keyed by its published path."""
    result = {}
    for name in ASSETS:
        kind, filename = name.split('/', 1)
        source = ui.css_source(filename) if kind == 'css' else ui.js_source(filename)
        result[ASSET_BASE + name] = source.encode('utf-8')
    result[HTML_IMPORT_MODULE] = html_import_files(ui)["extract.mjs"]
    for name, builder in STYLESHEET_BUNDLES.items():
        result[ASSET_BASE + name] = getattr(ui, builder)().encode()
    return result


def load_module(name: str, relative_path: str | Path) -> ModuleType:
    """Load a Python module from an absolute path or a path relative to the repository root."""
    path = Path(relative_path)
    if not path.is_absolute():
        path = ROOT / path

    if not path.is_file():
        raise FileNotFoundError(f"Vendor module file not found: {path}")

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not create module spec for {name} from {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def add_back_nav(page: str) -> str:
    """🏠 PySaiyanWeBoo's way back (``back_nav_html``) to the 🧭 Tools & Demos cards, right after <main> (else <body>);
    a page that already has one keeps it."""
    import pysaiyanweboo as ui
    return ui.add_back_nav(page, [{'label': '← 🧭 Tools & Demos', 'href': '../../index.html#tools'}], test_id='portfolio-back')


def add_home_label(page: str, label: str, *, icons_from: str | None = None) -> str:
    """Name a home-screen shortcut of the page ``label`` (iOS reads apple-mobile-web-app-title, Chrome application-name).

    A long <title> is cut off under the icon; replaces any earlier label, so it is idempotent. ``icons_from`` is the way
    back to the site root (``'../../'``): it also links the portfolio's tab icon and home-screen icon, replacing any others.
    """
    page = re.sub(r'<meta\b[^>]*\bname=["\'](?:apple-mobile-web-app-title|application-name)["\'][^>]*>', '', page, flags=re.I)
    value = html.escape(label, quote=True)
    tags = f'<meta name="apple-mobile-web-app-title" content="{value}"><meta name="application-name" content="{value}">'
    if icons_from is not None:
        page = re.sub(r'<link\b[^>]*\brel=["\'](?:icon|apple-touch-icon)["\'][^>]*>', '', page, flags=re.I)
        tags += (f'<link rel="icon" type="image/png" sizes="32x32" href="{icons_from}assets/brand/favicon-32x32.png">'
                 f'<link rel="apple-touch-icon" sizes="170x170" href="{icons_from}assets/brand/myon-profile-icon.png">')
    # Right after <title>, the name it shortens, so steps that append to </head> (lab branding) keep their place.
    for anchor in ('</title>', '</head>'):
        if anchor in page:
            return page.replace(anchor, anchor + tags if anchor == '</title>' else tags + anchor, 1)
    raise ValueError('page has no </title> or </head>')


def render_front(root: Path = ROOT, samples=frozenset()) -> dict[str, bytes]:
    """The portfolio's own front page (scripts/front_page.py), built from profile.json, api/repos.json and projects.json.

    It is not in the lock: api/repos.json is refreshed by a workflow, and the page must follow it without a lock refresh."""
    return {'index.html': load_module('front_page', 'scripts/front_page.py').document(root, samples=samples).encode('utf-8')}


def render_demos(ui) -> dict[str, bytes]:
    """Every demo page, plus their catalog as tools/demos/index.html, keyed by published path (two levels below the site root)."""
    result = {DEMO_BASE + 'index.html': add_home_label(add_back_nav(ui.catalog_document({
        'schema': 'web-ui-catalog/1', 'title': '🧰 Demos',
        'description': '🌍 ワールドと 🤖🔁 スタブ、PySaiyanWeBoo のモック。どれも Python で生成し、通信せずこのページの中で動きます。',
        'items': [{'id': name, 'title': title, 'summary': summary, 'links': [{'label': 'Open →', 'href': f'./{name}.html'}]}
                  for name, (_, _, title, summary) in DEMOS.items()]})), '🧰 Demos', icons_from='../../').encode('utf-8')}
    for name, (build, label, _, _) in DEMOS.items():
        result[DEMO_BASE + name + '.html'] = add_home_label(add_back_nav(build(ui)), label, icons_from='../../').encode('utf-8')
    return result


def html_import_files(ui):
    return ui.html_import_files(shared_base="../vendor/web-ui", docs_href="../../docs/html-import.md")


def render_html_import(ui) -> dict[str, bytes]:
    document = html_import_files(ui)["index.html"].decode()
    document = add_home_label(add_back_nav(document), '📄 HTML取込', icons_from='../../')
    return {HTML_IMPORT_PAGE: document.encode()}


def showcases(root: Path = ROOT) -> list[dict]:
    """The projects.json entries that have a ``showcase``, in their order there (none without a projects.json)."""
    path = root / 'projects.json'
    return [p for p in json.loads(path.read_text(encoding='utf-8')) if 'showcase' in p] if path.is_file() else []


def _project_file(project: dict) -> str:
    return PROJECT_BASE + project['name'].lower() + '.html'


def pages_urls(root: Path = ROOT) -> dict[str, str]:
    """Repository name → its GitHub Pages root, from api/repos.json (generated from GitHub's ``has_pages``)."""
    path = root / 'api/repos.json'
    repos = json.loads(path.read_text(encoding='utf-8'))['repos'] if path.is_file() else []
    return {repo['name']: repo['pages'] for repo in repos if repo.get('pages') and not repo.get('archived')}


def render_projects(ui, root: Path = ROOT) -> dict[str, bytes]:
    """A page per showcased project (icon, description, media, the recorded run, links) and their catalog, by published path."""
    result = {}
    pages = pages_urls(root)
    for project in showcases(root):
        show = project['showcase']
        raw = lambda path: f"https://raw.githubusercontent.com/{show['repository']}/{show['commit']}/{show.get('path', '')}{path}"
        blocks = [{'type': 'text', 'text': project['desc']}]
        where = show['repository'] + ('/' + show['path'].rstrip('/') if show.get('path') else '')
        if show.get('media'):
            blocks.append({'type': 'section', 'title': '🎞️', 'blocks': [
                {'type': 'image', 'src': raw(m['src']), 'alt': m['alt']} for m in show['media']]})
        if 'run' in show:
            run = show['run']
            output = json.dumps(json.loads(run['output']), indent=2, ensure_ascii=False) if run.get('pretty_json') else run['output']
            blocks.append({'type': 'section', 'title': '▶ 実行例', 'blocks': [
                {'type': 'kv', 'rows': [['📦', f"{where} @ {show['commit'][:7]}"], ['⌨️', shlex.join(run['command'])],
                                        ['↩️', f"exit {run['exit']}"]]},
                {'type': 'output', 'text': output}]})
        if show.get('scripts', {}).get('items'):
            items = show['scripts']['items']
            unknown = sum(not item['summary'] for item in items)
            blocks.append({'type': 'section', 'title': '🧰 スクリプト', 'blocks': [
                {'type': 'kv', 'rows': [['📦', f"{where} @ {show['commit'][:7]}"],
                                        ['🔢', f"{len(items)}" + (f" · ❔ {unknown}" if unknown else '')],
                                        ['🛠️', 'docstring · --help → 自動生成']]},
                *[block for item in items for block in (     # 📱 stacked, not a table: paths stay whole on a phone
                    {'type': 'heading', 'level': 3, 'text': '📄 ' + item['path']},
                    {'type': 'kv', 'rows': [['📝', item['summary'] or '❔'], ['⌨️', item['usage'] or '—']]})]]})
        blocks.append({'type': 'links', 'items': [*([{'label': '🌐 Pages', 'href': pages[project['name']]}] if project['name'] in pages else []),
                                                  {'label': '🐙 GitHub', 'href': project['url']},
                                                  {'label': '📄 README', 'href': project['url'] + '#readme'}]})
        if project.get('topics'):
            blocks.append({'type': 'badges', 'items': project['topics']})
        spec = {'schema': 'web-ui-page/1', 'title': project['name'], 'blocks': blocks} | ({'icon': raw(show['icon'])} if 'icon' in show else {})
        page = ui.page_document(spec).replace('</head>', '<style>.ui-title,.ui-kv dd,.ui-page h3{overflow-wrap:anywhere}</style></head>', 1)  # long names and commands
        result[_project_file(project)] = add_home_label(add_back_nav(page), show['label'], icons_from='../../').encode('utf-8')
    catalog = ui.catalog_document({
        'schema': 'web-ui-catalog/1', 'title': '📚 Projects',
        'description': '固定したコミットで記録した実行例・図や GIF・スクリプト一覧を1ページずつ。🌐 はそのリポジトリの Pages。',
        'items': [{'id': p['name'].lower(), 'title': p['name'], 'summary': p['desc'],
                   'links': [{'label': 'Open →', 'href': './' + p['name'].lower() + '.html'},
                             *([{'label': '🌐 Pages', 'href': pages[p['name']]}] if p['name'] in pages else []),
                             {'label': 'GitHub', 'href': p['url']}]}
                  for p in showcases(root)]})
    result[PROJECT_BASE + 'index.html'] = add_home_label(add_back_nav(catalog), '📚 Projects', icons_from='../../').encode('utf-8')
    return result


# ── 🎞 GIF工房 and 🎥 the moving samples: both draw with PySaiyanWeBoo's gif.js (window.UiGif) ──────────────────────────
GIF_PAGE = 'tools/gif/index.html'
SAMPLES = 'media/pages/'          # 🎥 one moving sample per repository's Pages, recorded at deploy time (not kept in git)
GIF_SIZES = ('240x432', '320x240', '480x360', '640x480', '392x704')   # canvas below the caption, multiples of 8
GIF_SCRIPT = r"""(() => {
  const $ = id => document.getElementById(id);
  let url = null;
  // 🖼 any image the browser can open → PNG, so the encoder sees one format (nothing leaves the page)
  const png = async file => {
    const bitmap = await createImageBitmap(file), canvas = document.createElement("canvas");
    canvas.width = bitmap.width; canvas.height = bitmap.height;
    canvas.getContext("2d").drawImage(bitmap, 0, 0);
    return canvas.toDataURL("image/png").split(",")[1];
  };
  $("gif-files").addEventListener("change", () => {
    $("gif-status").textContent = `🖼 ${$("gif-files").files.length}枚`;
  });
  $("gif-make").addEventListener("click", async () => {
    const files = [...$("gif-files").files];
    if (!files.length) { $("gif-status").textContent = "📂 画像を選んでください"; return; }
    const [width, height] = $("gif-size").value.split("x").map(Number);
    const delay = Number($("gif-delay").value), named = $("gif-names").checked;
    $("gif-status").textContent = `⏳ ${files.length}枚…`;
    try {
      const recorder = new UiGif.Recorder({width, height, caption: named ? 32 : 0});
      const frames = [];
      for (const file of files) frames.push({png: await png(file), caption: named ? file.name : "", ok: true, delay});
      await recorder.add(frames);
      const bytes = Uint8Array.from(atob(recorder.encodeBase64({}).gif), c => c.charCodeAt(0));
      if (url) URL.revokeObjectURL(url);
      url = URL.createObjectURL(new Blob([bytes], {type: "image/gif"}));
      $("gif-preview").src = url; $("gif-preview").hidden = false;
      $("gif-save").href = url; $("gif-save").hidden = false;
      $("gif-status").textContent = `✅ ${files.length}枚 · ${Math.max(1, Math.round(bytes.length / 1024))} KiB`;
    } catch (error) {
      $("gif-status").textContent = "⛔ " + error.message;
    }
  });
})();"""


def render_gif_tool(ui) -> dict[str, bytes]:
    """🎞 GIF工房: images the visitor picks become one looping GIF in the page (gif.js); nothing is sent or stored."""
    option = lambda value, label, chosen=False: f'<option value="{value}"{" selected" if chosen else ""}>{label}</option>'
    body = ('<main class="ui-page"><h1 class="ui-title">🎞 GIF工房</h1>'
            '<p class="ui-muted">🖼 画像を選ぶ → ▶ つくる → ⬇ 保存。端末の中だけで作り、画像はどこにも送らず、残しもしない。</p>'
            '<p><label>📂 <input id="gif-files" type="file" accept="image/*" multiple></label></p>'
            '<p><label>📐 <select id="gif-size">' + ''.join(option(s, s.replace('x', '×'), s == '480x360') for s in GIF_SIZES) + '</select></label> '
            '<label>⏱ <select id="gif-delay">' + ''.join(option(ms, f'{ms} ms', ms == 600) for ms in (200, 400, 600, 1000, 1500)) + '</select></label> '
            '<label>🏷 <input id="gif-names" type="checkbox"> ファイル名</label></p>'
            '<p><button id="gif-make" type="button" class="ui-button">▶ つくる</button> '
            '<a id="gif-save" class="ui-button" download="gif-kobo.gif" hidden>⬇ 保存</a> <span id="gif-status" role="status"></span></p>'
            '<p><img id="gif-preview" alt="🎞 できた GIF" hidden style="max-width:100%;height:auto"></p></main>')
    page = ui.render_document(trusted_html=body + ui.classic_script(ui.js_source('gif.js')) + ui.classic_script(GIF_SCRIPT),
                              title='🎞 GIF工房', css=ui.bundled_css())       # the shared sheet (render_pages links it as css/bundle.css)
    return {GIF_PAGE: add_home_label(add_back_nav(page), '🎞 GIF工房', icons_from='../../').encode('utf-8')}


def recorded_samples(output: Path) -> frozenset[str]:
    """The lower-case names whose 🎥 sample is under ``output`` (the front page shows only those)."""
    return frozenset(path.stem for path in (Path(output) / SAMPLES).glob('*.gif'))


def record_samples(output: Path, pages: dict[str, str], *, viewport=(392, 704), size=(240, 432), max_bytes=300_000,
                   browser=None) -> list[str]:
    """🎥 Open each Pages in Chromium at phone size, keep the top and one screen further down, and write a two-frame GIF
    per repository as ``output/media/pages/<name>.gif`` with gif.js. Best effort: one line per repository (🎥 / ⏸).
    ``browser``: a launched Playwright browser to use (a caller already inside Playwright); otherwise Chromium is started."""
    if browser is None:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            chromium = playwright.chromium.launch()
            try:
                return record_samples(output, pages, viewport=viewport, size=size, max_bytes=max_bytes, browser=chromium)
            finally:
                chromium.close()
    import base64
    import pysaiyanweboo as ui
    folder = Path(output) / SAMPLES
    folder.mkdir(parents=True, exist_ok=True)
    lines = []
    site_context, encoder_context = browser.new_context(viewport={'width': viewport[0], 'height': viewport[1]}, is_mobile=True,
                                                        has_touch=True), browser.new_context()
    try:
        site, encoder = site_context.new_page(), encoder_context.new_page()
        encoder.set_content(ui.gif_recorder_document())
        for name, url in pages.items():
            try:
                response = site.goto(url, wait_until='load', timeout=30_000)
                if response is None or response.status >= 400:
                    raise RuntimeError(f'HTTP {response.status if response else "no response"}')
                site.wait_for_timeout(800)
                frames = [site.screenshot()]
                site.evaluate('h => window.scrollBy(0, h)', viewport[1])
                site.wait_for_timeout(500)
                if (lower := site.screenshot()) != frames[0]:
                    frames.append(lower)
                encoder.evaluate('o => { window.rec = new UiGif.Recorder(o); }', {'width': size[0], 'height': size[1], 'caption': 24})
                encoder.evaluate('items => rec.add(items)', [{'png': base64.b64encode(png).decode('ascii'), 'caption': f'🌐 {name}',
                                                             'ok': True, 'delay': 1500} for png in frames])
                gif = base64.b64decode(encoder.evaluate('o => rec.encodeBase64(o)', {'maxBytes': max_bytes})['gif'])
                (folder / f'{name.lower()}.gif').write_bytes(gif)
                lines.append(f'🎥 {name}: {len(frames)} frames · {len(gif) // 1024} KiB')
            except Exception as exc:                       # one Pages failing keeps the rest (and the deploy) going
                lines.append(f'⏸ {name}: {type(exc).__name__}: {str(exc).splitlines()[0][:120] if str(exc) else ""}')
    finally:
        site_context.close()
        encoder_context.close()
    return lines


# ── 🌊 流れの実験室: one FFSS run, seen twice — 🌊 how it moves (FFSS's demo GIF) and 📊 where it ends up (DRAgoWing) ──
FLOW_PAGE = 'tools/flow/index.html'
FLOW = 'media/flow/'                     # recorded at deploy time (pages.yml), with receipt.json; not kept in git
FLOW_REPOSITORIES = {'ffss': 'myon-bioinformatics/FluidFullSpeedSimulation', 'dragowing': 'myon-bioinformatics/DRAgoWing'}
FLOW_EXPERIMENTS = ('E30', 'E31', 'E32')
# (icon, title, FFSS demo, DRAgoWing figure, the FFSS record behind both)
FLOW_PAIRS = (('🫀', '血液の循環', 'D24', 'F09_blood-flow', 'E30 · blood'),
              ('🪨', '石炭火力', 'D25', 'F01_energy-coal', 'E31 · energy:coal'),
              ('🌀', 'LNG 複合（GTCC）', 'D26', 'F02_energy-gtcc', 'E31 · energy:lng'),
              ('❄️', 'ヒートポンプ', 'D27', 'F05_balance-point', 'E32 · balance'),
              ('🌅', '起動', 'D32', 'F06_startup', 'E31 · startup'))


def collect_flow(output: Path, ffss: Path, dragowing: Path, commits: dict[str, str]) -> dict:
    """Run FFSS's experiments and demos in ``ffss`` and DRAgoWing's figures from those same records in ``dragowing``
    (both ``python -S``, standard library only), copy each pair's GIF and SVG to ``output/media/flow/`` and write the
    receipt (commits and the pairs made) there; returns the receipt."""
    folder = Path(output) / FLOW
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        run = lambda cwd, *args: subprocess.run([sys.executable, '-S', *args], cwd=cwd, check=True, capture_output=True, timeout=900)
        for experiment in FLOW_EXPERIMENTS:
            run(ffss, 'fluidfullspeedsimulation.py', 'run', experiment, '--jsonl', str(tmp / f'{experiment}.jsonl'))
        (tmp / 'records.jsonl').write_bytes(b''.join((tmp / f'{e}.jsonl').read_bytes() for e in FLOW_EXPERIMENTS))
        run(ffss, 'fluidfullspeedsimulation.py', 'demos', '--out-dir', str(tmp / 'demos'), '--only', *(p[2] for p in FLOW_PAIRS))
        run(dragowing, 'dragowing.py', '--ffss', str(tmp / 'records.jsonl'), '--out', str(tmp / 'figures'))
        made = []
        for icon, title, demo, figure, record in FLOW_PAIRS:
            gif, svg = next(iter((tmp / 'demos').glob(f'{demo}_*.gif')), None), tmp / 'figures' / 'svg' / f'{figure}.svg'
            if gif and svg.is_file():
                shutil.copyfile(gif, folder / f'{demo}.gif')
                shutil.copyfile(svg, folder / f'{figure}.svg')
                made.append(demo)
    receipt = {'schema': 'flow-lab/1', 'commits': commits, 'made': made}
    (folder / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return receipt


def record_flow(output: Path, remote: str = 'https://github.com/') -> list[str]:
    """🌊 Clone FFSS and DRAgoWing at their default branches and ``collect_flow``; one log line each (best effort)."""
    with tempfile.TemporaryDirectory() as tmp:
        dirs, commits = {}, {}
        for key, repository in FLOW_REPOSITORIES.items():
            dirs[key] = Path(tmp) / key
            subprocess.run(['git', 'clone', '--quiet', '--depth', '1', remote + repository, str(dirs[key])], check=True, timeout=300)
            commits[key] = subprocess.run(['git', '-C', str(dirs[key]), 'rev-parse', 'HEAD'], check=True, capture_output=True,
                                          text=True).stdout.strip()
        receipt = collect_flow(output, dirs['ffss'], dirs['dragowing'], commits)
    return [f"🌊 FFSS @ {commits['ffss'][:7]} · 📊 DRAgoWing @ {commits['dragowing'][:7]}",
            *(f"{'✅' if p[2] in receipt['made'] else '⏸'} {p[0]} {p[1]}: {p[2]} × {p[3]}" for p in FLOW_PAIRS)]


def render_flow(ui, output: Path | None = None) -> dict[str, bytes]:
    """The 🌊 lab page from what this build recorded under ``output/media/flow/`` (not in the lock, like the front page:
    the media change with the two repositories); a pair that was not recorded says ⏸."""
    path = Path(output) / FLOW / 'receipt.json' if output else None
    receipt = json.loads(path.read_text(encoding='utf-8')) if path and path.is_file() else {'commits': {}, 'made': []}
    link = lambda key: (f"https://github.com/{FLOW_REPOSITORIES[key]}/tree/{receipt['commits'][key]}"
                        if key in receipt['commits'] else f"https://github.com/{FLOW_REPOSITORIES[key]}")
    blocks = [{'type': 'text', 'text': '同じ FFSS の実験記録を2回見る：🌊 流れと遅れの時間変化（FFSS の動く像）と、'
                                       '📊 流れた先の内訳（DRAgoWing の静止図）。どちらも公開のたびに、そのとき最新のコミットで作り直す。'},
              {'type': 'kv', 'rows': [['🌊', 'FFSS ' + receipt['commits'].get('ffss', '—')[:7]],
                                      ['📊', 'DRAgoWing ' + receipt['commits'].get('dragowing', '—')[:7]]]}]
    for icon, title, demo, figure, record in FLOW_PAIRS:
        inner = [{'type': 'kv', 'rows': [['🔢', record], ['🌊', f'FFSS {demo}'], ['📊', f'DRAgoWing {figure}']]}]
        if demo in receipt['made']:
            inner += [{'type': 'image', 'src': f'../../{FLOW}{demo}.gif', 'alt': f'🌊 FFSS {demo}: {title}'},
                      {'type': 'image', 'src': f'../../{FLOW}{figure}.svg', 'alt': f'📊 DRAgoWing {figure}: {title}'}]
        else:
            inner.append({'type': 'text', 'text': '⏸ このビルドでは記録していない'})
        blocks.append({'type': 'section', 'title': f'{icon} {title}', 'blocks': inner})
    blocks.append({'type': 'links', 'items': [{'label': '🌊 FFSS', 'href': link('ffss')}, {'label': '📊 DRAgoWing', 'href': link('dragowing')}]})
    page = ui.page_document({'schema': 'web-ui-page/1', 'title': '🌊 流れの実験室', 'blocks': blocks}).replace(
        '</head>', '<style>.ui-page img{max-width:100%;height:auto}</style></head>', 1)       # 📱 the GIF and SVG fit a phone
    return {FLOW_PAGE: add_home_label(add_back_nav(page), '🌊 流れ実験', icons_from='../../').encode('utf-8')}   # fits an 80 px tile


# ── 🧠 リポジトリ地図: who copies what from whom, read from each repository's own vendor.lock.json (and Aoi's subtrees) ──
MAP_PAGE = 'tools/repo-map/index.html'
MAP = 'media/map/'                       # graph.json and map.svg, recorded at deploy time (pages.yml); not kept in git
OWNER = 'myon-bioinformatics'


def _ls_remote(repository: str) -> str:
    out = subprocess.run(['git', 'ls-remote', f'https://github.com/{repository}', 'HEAD'], check=True, capture_output=True,
                         text=True, timeout=60).stdout.split()
    return out[0]


def _raw(repository: str, commit: str, path: str) -> bytes | None:
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(f'https://raw.githubusercontent.com/{repository}/{commit}/{path}', timeout=30) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def map_edges(locks: dict[str, dict | None], subtrees: dict | None) -> list[dict]:
    """📤 → 📥 edges: one per (source repository, consumer) from the locks' rows, and Aoi → each subtree child."""
    edges = {}
    for consumer, lock in locks.items():
        for row in (lock or {}).get('files', []):
            source = row['repository'].split('/')[-1]
            if source != consumer:
                edges.setdefault((source, consumer, 'vendor'), []).append(row['destination'])
    for child, head in ((subtrees or {}).get('heads') or {}).items():
        edges[('Aoi', child.split('/')[-1], 'subtree')] = [head.get('optional', {}).get('subtree_prefix', '') + '/']
    return [{'from': a, 'to': b, 'kind': kind, 'files': sorted(files)} for (a, b, kind), files in sorted(edges.items())]


def map_svg(edges: list[dict], archived=frozenset()) -> str:
    """The edges as one SVG: suppliers on the left, users on the right (most connected first), Meiryo, sizes in 8s;
    an ``archived`` repository is marked 🗄."""
    out_deg, in_deg = {}, {}
    for e in edges:
        out_deg[e['from']] = out_deg.get(e['from'], 0) + 1
        in_deg[e['to']] = in_deg.get(e['to'], 0) + 1
    left = sorted(out_deg, key=lambda n: (-out_deg[n], n.lower()))
    right = sorted(in_deg, key=lambda n: (-in_deg[n], n.lower()))
    row, top, width = 24, 48, 720
    height = top + row * max(len(left), len(right), 1) + 16
    y = lambda side, name: top + row * side.index(name) + row // 2
    esc = lambda text: html.escape(text, quote=True)
    mark = lambda name: ('🗄 ' if name in archived else '') + name
    color = {'vendor': '#19d3f3', 'subtree': '#00cc96'}
    paths = ''.join(f'<path d="M232 {y(left, e["from"])} C360 {y(left, e["from"])} 360 {y(right, e["to"])} 488 {y(right, e["to"])}" '
                    f'stroke="{color[e["kind"]]}" stroke-width="{1 + min(4, len(e["files"]))}" fill="none" opacity=".55">'
                    f'<title>{esc(e["from"])} → {esc(e["to"])}: {esc(", ".join(e["files"]))}</title></path>' for e in edges)
    labels = (''.join(f'<text x="224" y="{y(left, n) + 4}" text-anchor="end">{esc(mark(n))} ({out_deg[n]})</text>' for n in left)
              + ''.join(f'<text x="496" y="{y(right, n) + 4}">{esc(mark(n))} ({in_deg[n]})</text>' for n in right))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
            'font-family="Meiryo, \'メイリオ\', sans-serif" font-size="13" fill="#e6edf3">'
            f'<rect width="{width}" height="{height}" fill="#0d1117"/>'
            '<text x="224" y="24" text-anchor="end" font-size="15">📤 写す元</text><text x="496" y="24" font-size="15">📥 写す先</text>'
            f'{paths}{labels}</svg>')


def record_map(output: Path, root: Path = ROOT, *, head=_ls_remote, raw=_raw) -> list[str]:
    """🧠 Read every active repository's vendor.lock.json (and Aoi's child-heads.json) at its current commit and write
    ``output/media/map/graph.json`` and ``map.svg``. Best effort: a repository that cannot be read is listed and skipped."""
    catalog = json.loads((root / 'api/repos.json').read_text(encoding='utf-8'))
    names = [repo['name'] for repo in catalog['repos'] if not repo.get('archived')]
    commits, locks, missed, subtrees = {}, {}, [], None
    for name in names:
        try:
            commits[name] = head(f'{OWNER}/{name}')
            data = raw(f'{OWNER}/{name}', commits[name], 'vendor.lock.json')
            locks[name] = json.loads(data) if data else None
            if name == 'Aoi' and (heads := raw(f'{OWNER}/Aoi', commits[name], 'child-heads.json')):
                subtrees = json.loads(heads)
        except Exception as exc:
            missed.append(f'⏸ {name}: {type(exc).__name__}')
    edges = map_edges(locks, subtrees)
    folder = Path(output) / MAP
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'graph.json').write_text(json.dumps({'schema': 'repo-map/1', 'commits': commits, 'edges': edges},
                                                  indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    archived = frozenset(repo['name'] for repo in catalog['repos'] if repo.get('archived'))
    (folder / 'map.svg').write_text(map_svg(edges, archived), encoding='utf-8')
    return [f'🧠 {len(commits)} repositories · {len(edges)} edges · {sum(len(e["files"]) for e in edges)} files', *missed]


def render_map(ui, output: Path | None = None) -> dict[str, bytes]:
    """The 🧠 map page from this build's graph.json (not in the lock, like the front page); ⏸ when nothing was read."""
    path = Path(output) / MAP / 'graph.json' if output else None
    graph = json.loads(path.read_text(encoding='utf-8')) if path and path.is_file() else None
    blocks = [{'type': 'text', 'text': 'どのリポジトリが、どのリポジトリのファイルを写して使っているか。各リポジトリの vendor.lock.json と、'
                                       'Aoi の subtree（child-heads.json）を、公開のたびにそのときのコミットで読む。線の太さはファイルの数。'}]
    if graph:
        users, uses = {}, {}
        for e in graph['edges']:
            users.setdefault(e['from'], []).append(e['to'])
            uses.setdefault(e['to'], []).append(e['from'])
        blocks += [{'type': 'kv', 'rows': [['🔗', f"{len(graph['edges'])} 本"], ['📦', f"{len(graph['commits'])} リポジトリ"],
                                           ['🟦', 'vendor（ファイルを写す）'], ['🟩', 'subtree（Aoi の子）']]},
                   {'type': 'image', 'src': f'../../{MAP}map.svg', 'alt': '🧠 写す元 → 写す先の地図'},
                   {'type': 'section', 'title': '📋 リポジトリごと', 'blocks': [{'type': 'kv', 'rows': [
                       [name, ' · '.join(part for part in (('📥 ' + ', '.join(sorted(uses[name]))) if name in uses else '',
                                                          ('📤 ' + ', '.join(sorted(users[name]))) if name in users else '') if part)]
                       for name in sorted(set(users) | set(uses), key=str.lower)]}]}]
    else:
        blocks.append({'type': 'text', 'text': '⏸ このビルドでは記録していない'})
    page = ui.page_document({'schema': 'web-ui-page/1', 'title': '🧠 リポジトリ地図', 'blocks': blocks}).replace(
        '</head>', '<style>.ui-page img{max-width:100%;height:auto}.ui-kv dd{overflow-wrap:anywhere}</style></head>', 1)
    return {MAP_PAGE: add_home_label(add_back_nav(page), '🧠 地図', icons_from='../../').encode('utf-8')}


# ── 🧰 道具: Ironmate's studios and mcp-toolcall-lab's execution lab, built from their default branches at deploy time ──
TOOLS = 'media/tools/receipt.json'       # what this build recorded; the pages live under their folders (not kept in git)
# key: (repository, folder under the site, entry pages inside it)
TOOL_SOURCES = {'ironmate': ('myon-bioinformatics/Ironmate', 'tools', ('image-studio/', 'browser-tools/', 'slide-studio/', 'slide-studio/phone/')),
                'mcp-toolcall-lab': ('myon-bioinformatics/mcp-toolcall-lab', 'tools/mcp-toolcall-lab/execution', ('',)),
                'dragowing': ('myon-bioinformatics/DRAgoWing', 'tools/heatmap', ('',))}


def _back_to_tools(page: str, path: str) -> str:
    """The way back to 🧭 Tools & Demos from ``path`` (any depth), right after <main> (else <body>)."""
    import pysaiyanweboo as ui
    return ui.add_back_nav(page, [{'label': '← 🧭 Tools & Demos', 'href': '../' * path.count('/') + 'index.html#tools'}],
                           test_id='portfolio-back')


_IRONMATE_ROUTES = {'tools/': 'browser-tools/', 'slides/': 'slide-studio/'}


def _studio_path(path: str) -> str:
    for source, target in _IRONMATE_ROUTES.items():
        if path.startswith(source):
            return target + path[len(source):]
    return 'image-studio/' + path


_STUDIO_LINK = re.compile(r'(?P<attr>\b(?:href|src)=)(?P<quote>["\'])(?P<url>[^"\']+)(?P=quote)')


def _studio_href(source: str, url: str) -> str:
    from urllib.parse import urlsplit, urlunsplit
    parts = urlsplit(url)
    if not parts.path or parts.scheme or parts.netloc or parts.path.startswith('/'):
        return url
    directory = posixpath.dirname(source)
    old_target = posixpath.normpath(posixpath.join(directory, parts.path))
    if parts.path.endswith('/'):
        old_target = '' if old_target == '.' else old_target + '/'
    if old_target.startswith('../') or old_target == '..':
        return url
    target = _studio_path(old_target)
    new_path = posixpath.relpath(target, posixpath.dirname(_studio_path(source)))
    if parts.path.endswith('/'):
        new_path += '/'
    return urlunsplit(('', '', new_path, parts.query, parts.fragment))


def _stage_studios(built: Path, mapped: Path) -> None:
    """Relocate Ironmate's generated pages and keep their shared assets and cross-links working."""
    for page in ('index.html', 'tools/index.html', 'slides/index.html', 'slides/phone/index.html'):
        if not (built / page).is_file():
            raise FileNotFoundError(page)
    for path in built.rglob('*'):
        if not path.is_file() or path.name == '.nojekyll':
            continue
        source = path.relative_to(built).as_posix()
        target = mapped / _studio_path(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == '.html':
            page = _STUDIO_LINK.sub(lambda m: m['attr'] + m['quote'] + _studio_href(source, m['url']) + m['quote'],
                                    path.read_text(encoding='utf-8'))
            if source != 'brand/index.html':
                page = _back_to_tools(page, 'tools/' + _studio_path(source))
            target.write_text(page, encoding='utf-8')
        elif source == 'brand/manifest.webmanifest':
            manifest = json.loads(path.read_text(encoding='utf-8'))
            # One shared app can open its two sibling tools under /tools/.
            manifest['scope'] = '../../'
            for shortcut in manifest.get('shortcuts', []):
                shortcut['url'] = _studio_href(source, shortcut['url'])
            target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        else:
            shutil.copyfile(path, target)

def collect_tools(output: Path, checkouts: dict[str, Path], commits: dict[str, str]) -> dict:
    """Build each tool from its checkout with ``python -S`` (the lab's build also runs Node) into ``output/<folder>/``,
    give each entry page the way back, and write the receipt; a tool that fails is left out. Returns the receipt."""
    made, failed = [], {}
    for key, (repository, folder, entries) in TOOL_SOURCES.items():
        if key not in checkouts:
            continue
        dest = Path(output) / folder
        try:
            with tempfile.TemporaryDirectory() as tmp:       # build aside; the ⏸ page stays unless the whole tool built
                built = Path(tmp) / 'site'
                run = lambda *args, env=None: subprocess.run([sys.executable, '-S', *args], cwd=checkouts[key], check=True,
                                                             capture_output=True, timeout=900, env=env)
                if key == 'ironmate':
                    run('image_studio.py', '--build-site', str(built))
                elif key == 'dragowing':                          # 🌡️ one page on stdout; its scenes open in Image Studio
                    built.mkdir()
                    (built / 'index.html').write_bytes(run('scripts/build_heatmap_page.py').stdout)
                else:
                    run('scripts/build_portable_pages.py', '--source-sha', commits[key], '--out', str(Path(tmp) / 'lab'),
                        env={**os.environ, 'PYTHONPATH': 'src'})
                    shutil.move(str(Path(tmp) / 'lab' / 'execution'), str(built))
                if key == 'ironmate':
                    mapped = Path(tmp) / 'mapped'
                    _stage_studios(built, mapped)
                    for entry in sorted(child.name for child in mapped.iterdir()):
                        target = dest / entry
                        if target.exists():
                            shutil.rmtree(target)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(mapped / entry), str(target))
                    made.append(key)
                    continue
                for entry in entries:
                    page = built / entry / 'index.html'
                    page.write_text(_back_to_tools(page.read_text(encoding='utf-8'), f'{folder}/{entry}index.html'), encoding='utf-8')
                if dest.exists():
                    shutil.rmtree(dest)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(built), str(dest))
            made.append(key)
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            failed[key] = type(exc).__name__
    receipt = {'schema': 'portfolio-tools/1', 'commits': commits, 'made': made, 'failed': failed}
    path = Path(output) / TOOLS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return receipt


def record_tools(output: Path, remote: str = 'https://github.com/') -> list[str]:
    """🧰 Clone each TOOL_SOURCES repository at its default branch and ``collect_tools``; one log line each (best effort)."""
    checkouts, commits, lines = {}, {}, []
    with tempfile.TemporaryDirectory() as tmp:
        for key, (repository, _, _) in TOOL_SOURCES.items():
            try:
                checkout = Path(tmp) / key
                subprocess.run(['git', 'clone', '--quiet', '--depth', '1', remote + repository, str(checkout)], check=True, timeout=300)
                commits[key] = subprocess.run(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], check=True, capture_output=True,
                                              text=True).stdout.strip()
                checkouts[key] = checkout
            except (OSError, subprocess.SubprocessError) as exc:
                lines.append(f'⏸ {key}: clone failed ({type(exc).__name__})')
        receipt = collect_tools(output, checkouts, commits)
    return lines + [f"✅ {key} @ {commits[key][:7]} → {TOOL_SOURCES[key][1]}/" if key in receipt['made'] else
                    f"⏸ {key}: {receipt['failed'][key]}" for key in checkouts]


def render_tools(ui, output: Path | None = None) -> dict[str, bytes]:
    """⏸ A short page at every entry of a tool this build did not record (tests, a failed clone), so a 🧭 link never 404s;
    a recorded tool is left as built."""
    path = Path(output) / TOOLS if output else None
    made = json.loads(path.read_text(encoding='utf-8'))['made'] if path and path.is_file() else []
    pages = {}
    for key, (repository, folder, entries) in TOOL_SOURCES.items():
        if key in made:
            continue
        for entry in entries:
            name = f'{folder}/{entry}index.html'
            page = ui.page_document({'schema': 'web-ui-page/1', 'title': f'🧰 {repository.split("/")[1]}', 'blocks': [
                {'type': 'text', 'text': f'⏸ この道具は、公開のたびに {repository} の最新のコミットから作り直す。このビルドでは作っていない。'},
                {'type': 'links', 'items': [{'label': '🐙 GitHub リポジトリ', 'href': f'https://github.com/{repository}'}]}]})
            pages[name] = _back_to_tools(page, name).encode('utf-8')
    return pages


def render_pages(ui, root: Path = ROOT) -> dict[str, bytes]:
    """Every hash-locked page: demos, projects, HTML import, map tools and the GIF workshop, keyed by published path."""
    maps = {path: add_home_label(add_back_nav(document), '地図・ピン', icons_from='../../').encode('utf-8')
            for path, document in load_module('map_tool', 'scripts/map_tool.py').render(ui, _world()).items()}
    pages = {**render_demos(ui), **render_projects(ui, root), **render_html_import(ui), **maps, **render_gif_tool(ui)}
    for sheet, builder in STYLESHEET_BUNDLES.items():
        prefix = b'<style>' + getattr(ui, builder)().encode()
        for path, page in pages.items():
            head, end, body = page.partition(b'</head>')
            if prefix in head:
                href = os.path.relpath(ASSET_BASE + sheet, os.path.dirname(path)).replace(os.sep, '/')
                link = f'<link rel="stylesheet" href="{href}">'.encode()
                head = head.replace(prefix, link + b'<style>', 1).replace(link + b'<style></style>', link, 1)
                pages[path] = head + end + body
    return pages


def _minimal_run(command: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as home:      # 🔒 PATH only: no names or values of this machine's other variables
        return subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                              env={'PATH': os.environ.get('PATH', ''), 'HOME': home, 'LANG': 'C.UTF-8'})


def script_catalog(base: Path, patterns: list[str]) -> list[dict]:
    """``{path, summary, usage}`` for every file the globs match under ``base``, from what each one declares.

    The summary and whether it declares its arguments come from the parent's ``fleet_check.script_facts`` (read with
    ``ast``, never run). Only a script that imports argparse or cli_args is asked for ``--help`` (``python3 -S``, minimal
    environment); usage is the first line of that and its indented continuations. Nothing else is executed, so a
    script that would just run cannot answer for itself. Best effort, never raises."""
    facts_of = load_module('portfolio_fleet_check', 'vendor/fleet_check.py').script_facts
    items = []
    for path in sorted({p for pattern in patterns for p in base.glob(pattern) if p.is_file()}):
        relative, facts, lines = path.relative_to(base).as_posix(), facts_of(path), []
        if facts['argparse']:
            try:
                done = _minimal_run(['python3', '-S', relative, '--help'], base, 20)
                lines = done.stdout.strip().splitlines() if done.returncode == 0 else []
            except (OSError, subprocess.TimeoutExpired):
                pass
        lines = lines if lines and lines[0].lower().startswith('usage') else []
        end = next((i for i, line in enumerate(lines[1:], 1) if not line[:1].isspace() or not line.strip()), len(lines))
        usage = ' '.join(' '.join(line.split()) for line in lines[:end])  # the first line and its indented continuations
        items.append({'path': relative, 'summary': facts['summary'], 'usage': usage[:300] + ('…' if len(usage) > 300 else '')})
    return items


def record(name: str, checkout: Path, root: Path = ROOT) -> dict:
    """Rerun ``name``'s showcase command and catalog its ``scripts`` in ``checkout`` (which must be at its commit) with a
    minimal environment; store both in projects.json and return the showcase."""
    path = root / 'projects.json'
    projects = json.loads(path.read_text(encoding='utf-8'))
    project = next((p for p in projects if p['name'] == name and 'showcase' in p), None)
    if project is None:
        raise ValueError(f'no showcase for {name} in projects.json')
    show = project['showcase']
    head = subprocess.run(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    if head != show['commit']:
        raise ValueError(f'{checkout} is at {head[:7]}, the showcase records {show["commit"][:7]}')
    base = Path(checkout) / show.get('path', '')
    if 'run' in show:
        done = _minimal_run(show['run']['command'], base, 120)
        show['run']['output'], show['run']['exit'] = (done.stdout + done.stderr).rstrip('\n'), done.returncode
    if 'scripts' in show:
        show['scripts']['items'] = script_catalog(base, show['scripts']['match'])
    path.write_text(json.dumps(projects, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return show


def advance(root: Path = ROOT, remote: str = 'https://github.com/') -> list[str]:
    """Move each showcase to the tip of its repository's default branch and ``record`` it there; one log line each.

    ⏩ moved · = already there · ⏸ kept at its pin because the new commit lacks the icon or media the page shows, or
    because its run now fails where it used to succeed (the page keeps a working example; the line says why)."""
    path, log = root / 'projects.json', []
    with tempfile.TemporaryDirectory() as tmp:
        checkouts = {}
        for project in showcases(root):
            name, show = project['name'], project['showcase']
            repository = show['repository']
            if repository not in checkouts:                    # one shallow fetch per repository (Aoi hosts several)
                checkout = Path(tmp) / str(len(checkouts))
                git = ['git', '-C', str(checkout)]
                checkout.mkdir()
                try:
                    for step in (['init', '-q'], ['fetch', '-q', '--depth', '1', remote + repository, 'HEAD'],
                                 ['-c', 'advice.detachedHead=false', 'checkout', '-q', 'FETCH_HEAD']):
                        subprocess.run(git + step, check=True, capture_output=True, timeout=300)
                    checkouts[repository] = checkout
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                    checkouts[repository] = None
            checkout = checkouts[repository]
            if checkout is None:
                log.append(f"⏸ {name} {show['commit'][:7]} (✗ fetch {repository})")
                continue
            head = subprocess.run(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                                  check=True).stdout.strip()
            old = show['commit']
            if head == old:
                log.append(f'= {name} {old[:7]}')
                continue
            base = checkout / show.get('path', '')
            missing = [f for f in [show.get('icon'), *(m['src'] for m in show.get('media', []))] if f and not (base / f).is_file()]
            if missing:
                log.append(f"⏸ {name} {old[:7]} (✗ {head[:7]}: {', '.join(missing)} missing)")
                continue
            before = path.read_text(encoding='utf-8')
            projects = json.loads(before)
            next(p for p in projects if p['name'] == name)['showcase']['commit'] = head
            path.write_text(json.dumps(projects, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
            new = record(name, checkout, root)
            if 'run' in show and show['run'].get('exit') == 0 and new['run']['exit'] != 0:
                path.write_text(before, encoding='utf-8')
                log.append(f"⏸ {name} {old[:7]} (✗ {head[:7]}: run exit {new['run']['exit']})")
                continue
            log.append(f'⏩ {name} {old[:7]} → {head[:7]}')
    return log


def generate(root: Path = ROOT, ui=None, commit: str | None = None) -> dict[str, bytes]:
    lock = json.loads((root / 'web-ui-assets.lock.json').read_text(encoding='utf-8'))
    if lock['schema'] != 'web-ui-generated/2':
        raise ValueError('unsupported generated asset lock')
    commit = commit or installed_commit()
    verify_pin(commit, root)
    if commit != lock['commit']:
        raise ValueError(f'generator provenance mismatch: installed {commit[:8]}, lock {lock["commit"][:8]}')
    if set(lock['outputs']) != {HTML_IMPORT_MODULE, *(ASSET_BASE + name for name in (*ASSETS, *STYLESHEET_BUNDLES))}:
        raise ValueError('generated output paths differ from public URL contract')
    expected = ({DEMO_BASE + 'index.html', PROJECT_BASE + 'index.html', HTML_IMPORT_PAGE, GIF_PAGE} | MAP_PAGES | {DEMO_BASE + name + '.html' for name in DEMOS}
                | {_project_file(p) for p in showcases(root)})
    if set(lock.get('pages', {})) != expected:
        raise ValueError('generated page paths differ from the demo list, projects.json showcases and the HTML import page')
    if ui is None:
        import pysaiyanweboo as ui
    result = render(ui)
    for target, data in result.items():
        if hashlib.sha256(data).hexdigest() != lock['outputs'][target]:
            raise ValueError(f'generated asset hash mismatch: {target}')
    pages = render_pages(ui, root)
    for target, data in pages.items():
        if hashlib.sha256(data).hexdigest() != lock['pages'][target]:
            raise ValueError(f'generated page hash mismatch: {target}')
    return {**result, **pages}


def validate_output(output: Path, root: Path = ROOT) -> None:
    output = output.resolve()
    if output == root.resolve() or root.resolve().is_relative_to(output):
        raise ValueError('output must not overwrite the source snapshot')


def build(output: Path, root: Path = ROOT) -> None:
    validate_output(output, root)
    import pysaiyanweboo as ui
    payload = {**generate(root), **render_front(root, recorded_samples(output)), **render_flow(ui, output), **render_map(ui, output),
               **render_tools(ui, output)}  # Fail closed first.
    for name, data in payload.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    # Publish the active asset provenance beside the generated files.
    (output / ASSET_BASE / 'generated.lock.json').write_bytes(
        (root / 'web-ui-assets.lock.json').read_bytes())


def stage(output: Path, root: Path = ROOT) -> None:
    """The site as Pages serves it: the source tree plus the generated files. Tests and local previews serve this."""
    validate_output(output, root)
    generate(root)  # Fail closed before copying anything.
    skip = ['.git', 'node_modules', '.venv', 'test-results', 'reports', '__pycache__', '.pytest_cache']
    if output.resolve().is_relative_to(root.resolve()):
        skip.append(output.resolve().relative_to(root.resolve()).parts[0])
    shutil.copytree(root, output, ignore=shutil.ignore_patterns(*skip), dirs_exist_ok=True)
    build(output, root)


def refresh_lock(root: Path = ROOT) -> dict:
    """After moving the pin: rewrite the lock from the installed generator (the generated files are not kept in git)."""
    import pysaiyanweboo as ui
    commit = installed_commit()
    verify_pin(commit, root)
    payload, pages = render(ui), render_pages(ui, root)
    lock = {
        'schema': 'web-ui-generated/2',
        'generator': 'pysaiyanweboo (pyproject.toml pages group)',
        'commit': commit,
        'outputs': {target: hashlib.sha256(data).hexdigest() for target, data in payload.items()},
        'pages': {target: hashlib.sha256(data).hexdigest() for target, data in pages.items()},
    }
    (root / 'web-ui-assets.lock.json').write_text(json.dumps(lock, indent=2) + '\n', encoding='utf-8')
    return lock


def _name_checkout(value: str) -> tuple[str, Path]:
    name, sep, checkout = value.partition('=')
    if not sep or not name or not checkout:
        raise argparse.ArgumentTypeError('NAME=CHECKOUT, e.g. Err-o-RoadRunner=../err-o-roadrunner')
    return name, Path(checkout)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='write the generated assets under this directory')
    parser.add_argument('--stage', type=Path, help='write the whole site (source tree plus generated assets) under this directory')
    parser.add_argument('--refresh-lock', action='store_true',
                        help='rewrite web-ui-assets.lock.json from the installed generator')
    parser.add_argument('--record', action='append', default=[], metavar='NAME=CHECKOUT', type=_name_checkout,
                        help="rerun NAME's showcase command and catalog its scripts in CHECKOUT (at the showcase commit), stored in projects.json; repeatable")
    parser.add_argument('--record-samples', type=Path, metavar='DIR',
                        help="🎥 record a moving sample of every repository's Pages under DIR/media/pages/ (Chromium; best effort)")
    parser.add_argument('--record-flow', type=Path, metavar='DIR',
                        help='🌊 run FFSS and DRAgoWing (their default branches) and put the flow lab media under DIR/media/flow/')
    parser.add_argument('--record-tools', type=Path, metavar='DIR',
                        help='🧰 build Ironmate\'s studios and mcp-toolcall-lab\'s execution lab (their default branches) under DIR/tools/')
    parser.add_argument('--record-map', type=Path, metavar='DIR',
                        help="🧠 read every repository's vendor.lock.json (and Aoi's subtrees) and draw the map under DIR/media/map/")
    parser.add_argument('--advance', action='store_true',
                        help="move every showcase to its repository's newest commit and record it there (keeps the pin when that would break the page)")
    args = parser.parse_args(argv)
    for target in (args.output, args.stage):
        if target:
            validate_output(target)
    if args.advance:
        print('\n'.join(advance()), file=sys.stderr)
    for name, checkout in args.record:
        show = record(name, checkout)
        if 'run' in show:
            print(f"▶ {name}: exit {show['run']['exit']}, {len(show['run']['output'].splitlines())} lines", file=sys.stderr)
        if 'scripts' in show:
            items = show['scripts']['items']
            print(f"🧰 {name}: {len(items)} scripts, ❔ {sum(not i['summary'] for i in items)} without a description", file=sys.stderr)
    if args.record_samples:
        pages = {name: url for name, url in pages_urls().items() if url != 'https://myon-bioinformatics.github.io/'}
        print('\n'.join(record_samples(args.record_samples, pages)))
    if args.record_map:
        print('\n'.join(record_map(args.record_map)))
    if args.record_flow:
        print('\n'.join(record_flow(args.record_flow)))
    if args.record_tools:
        print('\n'.join(record_tools(args.record_tools)))
    if args.refresh_lock:
        print(json.dumps(refresh_lock(), indent=2))
    if args.output:
        build(args.output)
    if args.stage:
        stage(args.stage)
    if not (args.refresh_lock or args.output or args.stage or args.record or args.advance or args.record_samples or args.record_flow or args.record_map
            or args.record_tools):
        parser.error('give --output DIR, --stage DIR, --refresh-lock, --advance, --record-samples DIR and/or --record NAME=CHECKOUT')


if __name__ == '__main__':
    raise SystemExit(main())
