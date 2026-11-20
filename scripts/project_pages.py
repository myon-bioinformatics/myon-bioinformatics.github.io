"""Generate the shared browser assets from the pinned PySaiyanWeBoo dependency.

The generator is the ``pysaiyanweboo`` module installed from ``requirements-pages.txt`` (a git
dependency pinned by commit). ``web-ui-assets.lock.json`` records that commit and the
SHA-256 of every output, so a build fails closed when the installed module is not the
pinned commit or when its output drifted from the lock. The generated files are not kept in git: ``--output DIR``
writes them (Pages overlays them on its build), ``--stage DIR`` writes the whole site for tests and local previews,
and ``--refresh-lock`` rewrites the lock after the pin moves.

The demos are PySaiyanWeBoo's stubs and mocks (MCP / API stubs, an in-page MCP server, a JUnit reader), published here
with the portfolio's way back, shortcut label and icons. ``tools/projects/`` gives every project in ``projects.json`` that
has a ``showcase`` a page of its own, Pages or not: its icon and media at a fixed commit, and one recorded run.
``--record NAME=CHECKOUT`` reruns that command in a checkout of exactly that commit and stores the output.

``tools/html-import/index.html`` (the HTML import tool page) is built here too and hash-locked with the other pages.
Every generated or imported tool page gets the same way back and shortcut label: ``add_back_nav()`` and
``add_home_label()`` (scripts/lab_import.py calls them for the lab pages). ``load_module()`` loads a file of this
repository by path (a sibling script or a vendored module) without touching ``sys.path``.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import importlib.util
import json
import os
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
MAP_PAGES = {'tools/maps/index.html', 'tools/maps/tokyo.html'}
BACK_NAV = ('<nav class="portfolio-back" aria-label="Portfolio">'
            '<a href="../../index.html#tools" data-testid="portfolio-back">← Tools &amp; Demos</a></nav>')

# 🧰 name -> (how pysaiyanweboo builds it, shortcut label, title, summary): the only list of demos.
DEMOS = {
    'mcp-stub': (lambda ui: ui.stub_document(ui.EXAMPLE_STUBS['mcp']), '🤖 MCP stub', 'MCP stub', '通信しない MCP のスタブ：ツール名を入れて結果と証跡を見る'),
    'api-stub': (lambda ui: ui.stub_document(ui.EXAMPLE_STUBS['api']), '🔁 API stub', 'API stub', '通信しない API のスタブ：パスを送って結果と証跡を見る'),
    'mcp-lab': (lambda ui: ui.mcp_document(), '🔌 MCP試験', 'MCP lab', 'ページ内で動く MCP サーバーのモック：新旧の protocol、PKCE、ヘッダー名、Bearer、OAuth メタデータ'),
    'test-report': (lambda ui: ui.report_document(), '🧾 JUnit', 'Test report', 'JUnit の結果を貼るか開いて読み、前回と比べて新規・再発・解消を分ける'),
}


def installed_commit(distribution: str = DISTRIBUTION) -> str:
    """The git commit the installed generator came from (pysaiyanweboo.installed_commit, i.e. pip's install record)."""
    if distribution != DISTRIBUTION:
        raise ValueError(f'{distribution} is not installed (pip install -r requirements-pages.txt)')
    try:
        import pysaiyanweboo
    except ImportError as exc:
        raise ValueError(f'{distribution} is not installed (pip install -r requirements-pages.txt)') from exc
    commit = pysaiyanweboo.installed_commit()
    if not commit:
        raise ValueError(f'{distribution} was not installed from its git source')
    return commit


def pinned_commit(root: Path = ROOT) -> str:
    """Read the immutable dependency pin; refresh must never adopt another install."""
    requirement = (root / 'requirements-pages.txt').read_text(encoding='utf-8')
    pins = re.findall(r'^pysaiyanweboo @ git\+https://github\.com/myon-bioinformatics/PySaiyanWeBoo@([0-9a-f]{40})$',
                      requirement, re.MULTILINE)
    if len(pins) != 1:
        raise ValueError('expected one full PySaiyanWeBoo commit pin')
    return pins[0]


def verify_pin(commit: str, root: Path = ROOT) -> None:
    if commit != pinned_commit(root):
        raise ValueError('installed generator differs from requirements-pages.txt pin')


def render(ui) -> dict[str, bytes]:
    """Every public asset rendered by the generator module, keyed by its published path."""
    result = {}
    for name in ASSETS:
        kind, filename = name.split('/', 1)
        source = ui.css_source(filename) if kind == 'css' else ui.js_source(filename)
        result[ASSET_BASE + name] = source.encode('utf-8')
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
    """Insert BACK_NAV right after the opening <main> tag, else <body> (idempotent)."""
    if 'data-testid="portfolio-back"' in page:
        return page
    for tag in ('<main', '<body'):
        start = page.find(tag)
        end = page.find('>', start)
        if start >= 0 and end >= 0:
            return page[:end + 1] + BACK_NAV + page[end + 1:]
    raise ValueError('tool page has no <main> or <body> element')


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


def render_front(root: Path = ROOT) -> dict[str, bytes]:
    """The portfolio's own front page (scripts/front_page.py), built from profile.json, api/repos.json and projects.json.

    It is not in the lock: api/repos.json is refreshed by a workflow, and the page must follow it without a lock refresh."""
    return {'index.html': load_module('front_page', 'scripts/front_page.py').document(root).encode('utf-8')}


def render_demos(ui) -> dict[str, bytes]:
    """Every demo page, plus their catalog as tools/demos/index.html, keyed by published path (two levels below the site root)."""
    result = {DEMO_BASE + 'index.html': add_home_label(add_back_nav(ui.catalog_document({
        'schema': 'web-ui-catalog/1', 'title': '🧰 Demos',
        'description': 'PySaiyanWeBoo が Python で生成したスタブとモック。どれも通信せず、このページの中で動きます。',
        'items': [{'id': name, 'title': title, 'summary': summary, 'links': [{'label': 'Open →', 'href': f'./{name}.html'}]}
                  for name, (_, _, title, summary) in DEMOS.items()]})), '🧰 Demos', icons_from='../../').encode('utf-8')}
    for name, (build, label, _, _) in DEMOS.items():
        result[DEMO_BASE + name + '.html'] = add_home_label(add_back_nav(build(ui)), label, icons_from='../../').encode('utf-8')
    return result


# The generated shared stylesheets, as tools/vendor/web-ui/ publishes them (web-ui-assets.lock.json).
SHARED_STYLESHEETS = tuple(f'../vendor/web-ui/css/{name}.css' for name in ('tokens', 'base', 'components', 'themes/modern'))

HTML_IMPORT_BODY = '''<main class="ui-page">
<h1>📄 HTML文書取込</h1>
<p>貼り付けたHTMLやローカルファイルから本文・見出し・リンクを取り出します。入力と結果はこのページのメモリ内で処理し、運営者へ自動送信・保存しません。HTML内のスクリプトや画像は実行・取得しません。</p>
<section class="ui-panel" aria-labelledby="input-title"><h2 id="input-title">1. 取り込む</h2>
<label for="source-url">取得元URL（絶対HTTP(S)、相対リンクの基準）</label>
<input class="ui-input" id="source-url" type="url" placeholder="https://example.org/page" autocomplete="off">
__SOURCE_LINK__
<p>上のリンクを選んだ時だけ指定サイトへアクセスします。開いたサイトでHTMLを保存するかソースをコピーし、このページへ取り込んでください。サイトの表示内容を自動取得する機能ではありません。</p>
<p>URLは出典の申告です。取込・抽出処理はアクセスしません。元URLが不明な場合は明示した仮のURLを使用してください。ダウンロード済みの証明にはなりません。</p>
<label for="html-input">HTMLを貼り付ける</label><textarea class="ui-input" id="html-input" rows="8" spellcheck="false" placeholder="&lt;article&gt;&lt;h1&gt;見出し&lt;/h1&gt;&lt;p&gt;本文&lt;/p&gt;&lt;/article&gt;"></textarea>
<button class="ui-button" id="paste-load" type="button">貼り付けを取り込む</button>
<label for="file-input">またはHTMLファイルを選択（UTF-8、2 MiBまで）</label>
<input class="ui-input" id="file-input" type="file" accept=".html,.htm,text/html">
</section>
<section class="ui-panel" aria-labelledby="options-title"><h2 id="options-title">2. 抽出条件</h2>
<label for="profile">抽出プロファイル</label><select class="ui-input" id="profile"><option value="generic">一般（article → main → 文書全体）</option><option value="github-readme">GitHub README（article.markdown-bodyが1件）</option></select>
<label for="selector">一般プロファイルのセレクター（任意）</label><input class="ui-input" id="selector" placeholder="main > article.note" autocomplete="off">
<p>対応：タグ、#id、.class、子孫、&gt;、:root。CSS・外部参照は読み込みません。条件変更は取込済みデータを使い、ファイルを再読込しません。</p>
<button class="ui-button" id="apply" type="button">条件を適用</button> <button class="ui-button" id="clear" type="button">入力と結果を消去</button>
</section>
<p id="status" role="status" aria-live="polite">まず取得元URLとHTMLを指定してください。</p>
<section class="ui-panel"><h2>3. 結果</h2><button class="ui-button" id="download" type="button" disabled>結果JSONをダウンロード</button>
<h3>取得元・取込方法</h3><pre class="ui-output" id="provenance"></pre>
<h3>本文</h3><pre class="ui-output" id="body-result"></pre>
<h3>見出し</h3><pre class="ui-output" id="headings-result"></pre>
<h3>リンク（表示のみ、追跡しません）</h3><pre class="ui-output" id="links-result"></pre></section>
<details class="ui-panel"><summary>対応範囲と制約</summary>
<p>通常のHTML文書・整形式のarticle/main、見出しh1〜h6、HTTP(S)リンクを対象にします。script/style/template/noscriptの内容は除外します。HTMLのbase要素は無視します。隠された文字もCSSで判定せず、空白は正規化します。</p>
<p>ブラウザはHTML5として木構造を補正します。省略・不正なタグ、tableの補正、重複属性、SVG/MathML、特殊な文字参照、URLの正規化ではPythonと差が出る場合があります。Python/JS一致は共有fixtureで確認した範囲です。完全なCSS、計算済みスタイル、PDF、JS生成ページ、外部ファイルの取得、文字コード自動判定は未対応です。</p>
<p>JSONはhtml-snapshot/1のメタデータと抽出結果を含み、元HTML本文は含みません。fetched_atとresponse_sha256はnullです。入力はページを離れると失われます。保存は利用者がダウンロードを選んだ場合のみです。<a href="../../docs/html-import.md">抽出契約と検証方法</a></p></details>
</main>'''
HTML_IMPORT_CSS = 'label{display:block;margin:1rem 0 .3rem}input,textarea,select{width:100%;max-width:100%}button{margin:.3rem 0;min-height:44px}pre{overflow-wrap:anywhere}h1{font-size:1.8rem}'


def render_html_import(ui) -> dict[str, bytes]:
    """The HTML import tool page (tools/html-import/), built with the pinned PySaiyanWeBoo wrapper. No visitor input."""
    document = ui.render_document(
        title='HTML文書取込',
        trusted_html=HTML_IMPORT_BODY.replace("__SOURCE_LINK__", ui.source_link("source-url")),
        css=HTML_IMPORT_CSS,
        stylesheets=SHARED_STYLESHEETS,
        scripts=('./app.mjs',),
    )
    csp = (
        "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self'; connect-src 'none'; frame-src 'none'; object-src 'none'; "
        "base-uri 'none'; form-action 'none'"
    )
    # The portfolio icons too, so a tab or a home-screen shortcut shows them (img-src 'self' below).
    document = add_home_label(add_back_nav(document), '📄 HTML取込', icons_from='../../')
    return {HTML_IMPORT_PAGE: document.replace('<head>', '<head><meta http-equiv="Content-Security-Policy" content="' + csp + '">', 1).replace('<html lang="en">', '<html lang="ja">').encode('utf-8')}


def showcases(root: Path = ROOT) -> list[dict]:
    """The projects.json entries that have a ``showcase``, in their order there (none without a projects.json)."""
    path = root / 'projects.json'
    return [p for p in json.loads(path.read_text(encoding='utf-8')) if 'showcase' in p] if path.is_file() else []


def _project_file(project: dict) -> str:
    return PROJECT_BASE + project['name'].lower() + '.html'


def render_projects(ui, root: Path = ROOT) -> dict[str, bytes]:
    """A page per showcased project (icon, description, media, the recorded run, links) and their catalog, by published path."""
    result = {}
    for project in showcases(root):
        show = project['showcase']
        raw = lambda path: f"https://raw.githubusercontent.com/{show['repository']}/{show['commit']}/{show.get('path', '')}{path}"
        blocks = [{'type': 'text', 'text': project['desc']}]
        if show.get('media'):
            blocks.append({'type': 'section', 'title': '🎞️', 'blocks': [
                {'type': 'image', 'src': raw(m['src']), 'alt': m['alt']} for m in show['media']]})
        if 'run' in show:
            run = show['run']
            output = json.dumps(json.loads(run['output']), indent=2, ensure_ascii=False) if run.get('pretty_json') else run['output']
            where = show['repository'] + ('/' + show['path'].rstrip('/') if show.get('path') else '')
            blocks.append({'type': 'section', 'title': '▶ 実行例', 'blocks': [
                {'type': 'kv', 'rows': [['📦', f"{where} @ {show['commit'][:7]}"], ['⌨️', shlex.join(run['command'])],
                                        ['↩️', f"exit {run['exit']}"]]},
                {'type': 'output', 'text': output}]})
        blocks.append({'type': 'links', 'items': [{'label': '🐙 GitHub', 'href': project['url']},
                                                  {'label': '📄 README', 'href': project['url'] + '#readme'}]})
        if project.get('topics'):
            blocks.append({'type': 'badges', 'items': project['topics']})
        spec = {'schema': 'web-ui-page/1', 'title': project['name'], 'blocks': blocks} | ({'icon': raw(show['icon'])} if 'icon' in show else {})
        page = ui.page_document(spec).replace('</head>', '<style>.ui-title,.ui-kv dd{overflow-wrap:anywhere}</style></head>', 1)  # long names and commands
        result[_project_file(project)] = add_home_label(add_back_nav(page), show['label'], icons_from='../../').encode('utf-8')
    catalog = ui.catalog_document({
        'schema': 'web-ui-catalog/1', 'title': '📚 Projects',
        'description': 'GitHub Pages を持たないプロジェクトにも、ここに1ページずつ：アイコン、図や GIF、記録した実行例。',
        'items': [{'id': p['name'].lower(), 'title': p['name'], 'summary': p['desc'],
                   'links': [{'label': 'Open →', 'href': './' + p['name'].lower() + '.html'}, {'label': 'GitHub', 'href': p['url']}]}
                  for p in showcases(root)]})
    result[PROJECT_BASE + 'index.html'] = add_home_label(add_back_nav(catalog), '📚 Projects', icons_from='../../').encode('utf-8')
    return result


def render_pages(ui, root: Path = ROOT) -> dict[str, bytes]:
    """Every hash-locked page: demos, projects, HTML import and map tools, keyed by published path."""
    maps = {path: add_home_label(add_back_nav(document), '地図・ピン', icons_from='../../').encode('utf-8')
            for path, document in load_module('map_tool', 'scripts/map_tool.py').render(ui).items()}
    pages = {**render_demos(ui), **render_projects(ui, root), **render_html_import(ui), **maps}
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


def record(name: str, checkout: Path, root: Path = ROOT) -> dict:
    """Rerun ``name``'s showcase command in ``checkout`` (which must be at its commit) with a minimal environment; store the output."""
    path = root / 'projects.json'
    projects = json.loads(path.read_text(encoding='utf-8'))
    project = next((p for p in projects if p['name'] == name and 'showcase' in p), None)
    if project is None:
        raise ValueError(f'no showcase for {name} in projects.json')
    show = project['showcase']
    head = subprocess.run(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    if head != show['commit']:
        raise ValueError(f'{checkout} is at {head[:7]}, the showcase records {show["commit"][:7]}')
    with tempfile.TemporaryDirectory() as home:      # 🔒 PATH only: no names or values of this machine's other variables
        done = subprocess.run(show['run']['command'], cwd=Path(checkout) / show.get('path', ''), capture_output=True, text=True,
                              timeout=120, env={'PATH': os.environ.get('PATH', ''), 'HOME': home, 'LANG': 'C.UTF-8'})
    show['run']['output'], show['run']['exit'] = (done.stdout + done.stderr).rstrip('\n'), done.returncode
    path.write_text(json.dumps(projects, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return show['run']


def generate(root: Path = ROOT, ui=None, commit: str | None = None) -> dict[str, bytes]:
    lock = json.loads((root / 'web-ui-assets.lock.json').read_text(encoding='utf-8'))
    if lock['schema'] != 'web-ui-generated/2':
        raise ValueError('unsupported generated asset lock')
    commit = commit or installed_commit()
    verify_pin(commit, root)
    if commit != lock['commit']:
        raise ValueError(f'generator provenance mismatch: installed {commit[:8]}, lock {lock["commit"][:8]}')
    if set(lock['outputs']) != {ASSET_BASE + name for name in (*ASSETS, *STYLESHEET_BUNDLES)}:
        raise ValueError('generated output paths differ from public URL contract')
    expected = ({DEMO_BASE + 'index.html', PROJECT_BASE + 'index.html', HTML_IMPORT_PAGE} | MAP_PAGES | {DEMO_BASE + name + '.html' for name in DEMOS}
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
    payload = {**generate(root), **render_front(root)}  # Fail closed before touching any output.
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
        'generator': 'pysaiyanweboo (requirements-pages.txt)',
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
                        help="rerun NAME's showcase command in CHECKOUT (at the showcase commit) and store its output in projects.json; repeatable")
    args = parser.parse_args(argv)
    for target in (args.output, args.stage):
        if target:
            validate_output(target)
    for name, checkout in args.record:
        run = record(name, checkout)
        print(f"▶ {name}: exit {run['exit']}, {len(run['output'].splitlines())} lines", file=sys.stderr)
    if args.refresh_lock:
        print(json.dumps(refresh_lock(), indent=2))
    if args.output:
        build(args.output)
    if args.stage:
        stage(args.stage)
    if not args.refresh_lock and not args.output and not args.stage and not args.record:
        parser.error('give --output DIR, --stage DIR, --refresh-lock and/or --record NAME=CHECKOUT')


if __name__ == '__main__':
    raise SystemExit(main())
