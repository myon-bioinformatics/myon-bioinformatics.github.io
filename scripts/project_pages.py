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
``--record NAME=CHECKOUT`` reruns that command in a checkout of exactly that commit and stores the output. A showcase
with ``scripts`` also gets a 🧰 table of the scripts its globs match there: each one's own description (module docstring,
or the leading ``//`` comment of a JS module) and the usage line of its ``--help``, recorded by the same ``--record``
so the list follows the code instead of being written by hand.

``tools/html-import/index.html`` (the HTML import tool page) is built here too and hash-locked with the other pages.
Every generated or imported tool page gets the same way back and shortcut label: ``add_back_nav()`` and
``add_home_label()`` (scripts/lab_import.py calls them for the lab pages). ``load_module()`` loads a file of this
repository by path (a sibling script or a vendored module) without touching ``sys.path``.
"""
from __future__ import annotations

import argparse
import ast
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
HTML_IMPORT_MODULE = 'tools/html-import/extract.mjs'
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


def render_projects(ui, root: Path = ROOT) -> dict[str, bytes]:
    """A page per showcased project (icon, description, media, the recorded run, links) and their catalog, by published path."""
    result = {}
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
        blocks.append({'type': 'links', 'items': [{'label': '🐙 GitHub', 'href': project['url']},
                                                  {'label': '📄 README', 'href': project['url'] + '#readme'}]})
        if project.get('topics'):
            blocks.append({'type': 'badges', 'items': project['topics']})
        spec = {'schema': 'web-ui-page/1', 'title': project['name'], 'blocks': blocks} | ({'icon': raw(show['icon'])} if 'icon' in show else {})
        page = ui.page_document(spec).replace('</head>', '<style>.ui-title,.ui-kv dd,.ui-page h3{overflow-wrap:anywhere}</style></head>', 1)  # long names and commands
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


def script_summary(path: Path) -> str:
    """The first line a script says about itself: its module docstring (Python) or leading ``//`` / ``/*`` comment (JS), else ''."""
    text = path.read_text(encoding='utf-8')
    if path.suffix == '.py':
        return (ast.get_docstring(ast.parse(text)) or '').strip().split('\n', 1)[0]
    for line in text.splitlines():  # past a shebang and the imports, up to the first statement
        line = line.strip()
        if line.startswith(('//', '/*')):
            return line.lstrip('/*').removesuffix('*/').strip()
        if line and not line.startswith(('#!', 'import ', "'use strict'", '"use strict"')):
            return ''
    return ''


def _minimal_run(command: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as home:      # 🔒 PATH only: no names or values of this machine's other variables
        return subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                              env={'PATH': os.environ.get('PATH', ''), 'HOME': home, 'LANG': 'C.UTF-8'})


def script_catalog(base: Path, patterns: list[str]) -> list[dict]:
    """``{path, summary, usage}`` for every file the globs match under ``base``: usage is the first line of ``--help``
    (``python3 -S`` or ``node``) with its indented continuations, '' when the script has none or needs more than this;
    best effort, never raises."""
    items = []
    for path in sorted({p for pattern in patterns for p in base.glob(pattern) if p.is_file()}):
        relative = path.relative_to(base).as_posix()
        command = ['python3', '-S', relative, '--help'] if path.suffix == '.py' else ['node', relative, '--help']
        try:
            done = _minimal_run(command, base, 20)
            lines = (done.stdout or done.stderr).strip().splitlines() if done.returncode == 0 else []
        except (OSError, subprocess.TimeoutExpired):
            lines = []
        end = next((i for i, line in enumerate(lines[1:], 1) if not line[:1].isspace() or not line.strip()), len(lines))
        usage = ' '.join(' '.join(line.split()) for line in lines[:end])  # the first line and its indented continuations
        items.append({'path': relative, 'summary': script_summary(path), 'usage': usage[:300] + ('…' if len(usage) > 300 else '')})
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
                        help="rerun NAME's showcase command and catalog its scripts in CHECKOUT (at the showcase commit), stored in projects.json; repeatable")
    args = parser.parse_args(argv)
    for target in (args.output, args.stage):
        if target:
            validate_output(target)
    for name, checkout in args.record:
        show = record(name, checkout)
        if 'run' in show:
            print(f"▶ {name}: exit {show['run']['exit']}, {len(show['run']['output'].splitlines())} lines", file=sys.stderr)
        if 'scripts' in show:
            items = show['scripts']['items']
            print(f"🧰 {name}: {len(items)} scripts, ❔ {sum(not i['summary'] for i in items)} without a description", file=sys.stderr)
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
