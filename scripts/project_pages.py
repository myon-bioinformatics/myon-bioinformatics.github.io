"""Generate the shared browser assets from the pinned PySaiyanWeBoo dependency.

The generator is the ``pysaiyanweboo`` module from the ``pages`` dependency group (a git dependency
pinned by commit in ``pyproject.toml``; ``uv run --locked --only-group pages`` installs it). ``web-ui-assets.lock.json`` records that commit and the
SHA-256 of every output, so a build fails closed when the installed module is not the
pinned commit or when its output drifted from the lock. The generated files are not kept in git: ``--output DIR``
writes them (Pages overlays them on its build), ``--stage DIR`` writes the whole site for tests and local previews,
and ``--refresh-lock`` rewrites the lock after the pin moves.

The 🧰 Tools cards (scripts/front_page.py ``PORTAL``) list the practical pages, each one working on what the visitor brings:
the 💬 cross-repo chat (scripts/chat.py, run by Pyodide in the page; ``--record-chat`` indexes the other repositories at deploy
time) and PySaiyanWeBoo's own tool documents (``PSWB_TOOLS``: 🧾 the JUnit reader; 🤝 its MCP connection test is the lab's #protocol panel), published with
the portfolio's way back, shortcut label and icons. The 🌍 world pages (scripts/world.py: the travel world, 🏫 the school,
🗼 the parallel cities, 🎬 the camera; tools/demos/) are built the same way for PySaiyanWeBoo's 🎞 GIF demo and are not among
the cards. Each repository's own Pages carry its 🧩 機能一覧 / 🔬 検証ガイド / 🎞 GIF デモ; nothing here copies them.

``tools/html-import/index.html`` (the HTML import tool page) is built here too and hash-locked with the other pages.
Every generated or imported tool page gets the same way back, chrome and shortcut label: ``add_back_nav()`` (the way back and
🧰 PySaiyanWeBoo's chrome: the board with the clock, 🏠 ⭐ ⚙️ and each page's own ☰ ⋯, from the spec ``tools_chrome()`` makes, and
🚪 PySaiyanWeBoo's Door-to-Door, every 🧰 Tools link as a footer pull-down: ``tools_door()``) and
``add_home_label()`` (_src/tools/mcp_lab.py gets them for the lab pages). ``load_module()`` loads a file of this
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
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
import posixpath
from urllib.parse import urljoin, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
ASSET_BASE = 'tools/vendor/web-ui/'
ASSETS = ('css/base.css', 'css/components.css', 'css/themes/modern.css',
          'css/tokens.css', 'js/navigation.js', 'js/ui.js', 'js/records.js', 'js/controls.js',
          'js/coordinates.js')
STYLESHEET_BUNDLES = {'css/bundle.css': 'bundled_css', 'css/core.css': 'core_css'}
DISTRIBUTION = 'pysaiyanweboo'
WORLD_PAGE = 'tools/demos/world.html'
# 🌍 One document: the school, the cities and the camera are its #school, #tokyo and #camera (no forwarding pages).
HTML_IMPORT_PAGE = 'tools/html-import/index.html'
HTML_IMPORT_MODULE = 'tools/html-import/extract.mjs'
WORLD_CSS_ASSET = 'tools/world-assets/world.css'
WORLD_JS_ASSET = 'tools/world-assets/world.js'
WORLD_ASSETS = (WORLD_CSS_ASSET, WORLD_JS_ASSET)
DRAGON_PNG_ASSET = 'tools/world-assets/london-dragon.png'
DRAGON_GRID_ASSET = 'tools/world-assets/london-dragon.json'
DRAGON_ASSETS = (DRAGON_PNG_ASSET, DRAGON_GRID_ASSET)
MAP_PINS_PAGE = 'tools/maps/index.html'

# Files served verbatim. The generators write every other public file to the output tree.
PUBLIC_SOURCE_FILES = (
    '.nojekyll',
    'api/repos.json',
    'assets/brand/favicon-16x16.png',
    'assets/brand/favicon-32x32.png',
    'assets/brand/favicon-48x48.png',
    'assets/brand/myon-profile-icon.png',
    'docs/evidence/browser.gif',
    'docs/evidence/browser.json',
    'docs/evidence/chat.gif',
    'docs/evidence/home-screen.gif',
    'docs/html-import.md',
    'favicon.ico',
    'license',
    'manifest.webmanifest',
    'profile.json',
    'projects.json',
    'site.config.json',
    'tools/niconico/search.js',
    'tools/vendor/web-ui/LICENSE',
)

# 🧰 PySaiyanWeBoo's documents that work on what the visitor brings, each a 🧰 Tools link (front_page.py PORTAL):
# published path -> (how it is built from pysaiyanweboo, the home-screen name)
PSWB_TOOLS = {
    'tools/test-report/index.html': (lambda ui: ui.report_document(), '🧾 テスト結果'),
}
@functools.lru_cache(maxsize=None)
def _world() -> ModuleType:
    """🌍 scripts/world.py (the world engine and its specs), loaded once."""
    return load_module('world', 'scripts/world.py')


def world_page(ui) -> str:
    shell = load_module('world_shell', 'scripts/world_shell.py')
    maps = load_module('map_tool', 'scripts/map_tool.py')
    css, js = (os.path.relpath(path, os.path.dirname(WORLD_PAGE)).replace(os.sep, '/') for path in WORLD_ASSETS)
    places = [p for p in tools_places('../../') if p['href'].split('#', 1)[0] != '../../' + WORLD_PAGE]
    runtime = {key: _chat().RUNTIME[key] for key in ('wllama', 'model')}
    dialogue = WLLAMA_JS + f'\nconst worldAnswer = localModel({json.dumps(runtime)});\n'
    dragon_png, dragon_grid = (os.path.relpath(path, os.path.dirname(WORLD_PAGE)).replace(os.sep, '/')
                               for path in DRAGON_ASSETS)
    return shell.document(ui, _world(), maps, places, css, js, dialogue,
                          dragon_png=dragon_png, dragon_grid=dragon_grid)


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
    result[WORLD_CSS_ASSET] = ('@layer components{' + _world().world_base_css() + '}').encode('utf-8')
    result[WORLD_JS_ASSET] = _world().WORLD_JS.encode('utf-8')
    grid = (ROOT / 'scripts/london-dragon.json').read_bytes()
    result[DRAGON_GRID_ASSET] = grid
    result[DRAGON_PNG_ASSET] = ui.pixel_grid_png(json.loads(grid))
    result[HTML_IMPORT_MODULE] = html_import_files(ui)["extract.mjs"]
    result[CHAT_SOURCES] = json.dumps(chat_sources(), ensure_ascii=False).encode('utf-8')
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


@functools.cache
def _front_module():
    return load_module('front_page', 'scripts/front_page.py')


def tools_places(prefix: str = '../../') -> list[dict]:
    """🧰 Every link of the 🧰 Tools cards (front_page.py ``PORTAL``, so a new card is a new row) as ``{'id', 'label', 'href'}``, for
    a page ``prefix`` below the site root: the doors of 🚪 Door-to-Door. ``text`` is the card's own description (the board shows it).

    Every label is ``emoji words``, one emoji per page (the door knows a page by its emoji): the card's own, or the one named here
    for a link that has none or shares its card's."""
    site, places = 'https://myon-bioinformatics.github.io/tools/', {}
    marks = {'html-import': '📄', 'maps': '🗺️', 'demos-world-html-tokyo': '🗼', 'browser-tools': '🎨', 'slide-studio': '📽️', 'mcp-execution': '🧪', 'mcp-protocol': '🤝'}
    for card in _front_module().PORTAL:
        mark, _, title = card['title'].partition(' ')
        if not title or any(c.isalnum() for c in mark):                  # a title without an emoji: all of it is words
            mark, title = '🚪', card['title']
        for label, href in card['links']:
            href = prefix + href[2:] if href.startswith('./') else prefix + 'tools/' + href[len(site):] if href.startswith(site) else href
            name = re.sub(r'[^a-z0-9]+', '-', href.partition('tools/')[2].removesuffix('.html').lower()).strip('-') or card['id']
            words = title if len(card['links']) == 1 else label.removesuffix(' →').removeprefix('Open ')   # several links: each link's own words
            places.setdefault(href, {'id': name, 'href': href, 'label': f'{marks.get(name, mark)} {words}', 'text': card['text']})
    return list(places.values())


def host_rows(page: str) -> dict:
    """🧰 The rows a page asks the site's header to show for it: ``<script type="application/json" id="ui-chrome-rows">`` in the page,
    ``{"tools": {emoji: …}, "settings": rows, "screen": rows, "replaces": "#id,#id"}`` in PySaiyanWeBoo's chrome terms (Ironmate's
    studios: one 💾 listing every format, one 📂, 📱 under ⚙️, the shelf under ⋯). Every row is an action (``{label, key}``): the page
    answers ``ui-chrome-action`` itself, so the site routes nothing. ``replaces`` names the page's own menus the rows stand in for;
    ``add_site_chrome`` hides them, so there is one way to save, in the one header. A page without the block asks for nothing."""
    block = re.search(r'<script type="application/json" id="ui-chrome-rows">(.*?)</script>', page, re.S)
    if not block:
        return {}
    rows = json.loads(block[1])
    listed = [row for tool in rows.get('tools', {}).values() for row in tool.get('links', [])] + rows.get('settings', []) + rows.get('screen', [])
    if set(rows) - {'tools', 'settings', 'screen', 'replaces'} or any(set(row) != {'label', 'key'} for row in listed):
        raise ValueError('a page\'s header rows are tools, settings and screen of {label, key}, and replaces')
    if not re.fullmatch(r'(#[a-z][a-z0-9-]*(,#[a-z][a-z0-9-]*)*)?', rows.get('replaces', '')):
        raise ValueError('replaces lists ids: #a,#b')
    return rows


def tools_chrome(prefix: str = '../../', tools: dict | None = None, description: str = '', *, title: str = 'TOOLS', home: bool = True,
                 rows: dict | None = None) -> dict:
    """🧰 The chrome every page of the site carries (PySaiyanWeBoo's ``chrome_validate``), for a page ``prefix`` below the site root:
    the board (``title``, the clock, then ``description`` — what this page is, a sentence per item — and the cards' titles), 🏠 back
    to the cards (``home=False``: the front page itself) and ``tools``, the emoji this page adds (``{'🗼': {'label': …, 'href': …}}``).
    ☰ is each page's own (itself and its sections, listed in the page); the tools themselves are 🚪 Door-to-Door's rows (``tools_places``)."""
    cards = _front_module().PORTAL
    about = [{'text': part if len(part) <= 120 else part[:119] + '…'}
             for part in (p.strip() for p in re.split(r'(?<=[。！？])|(?<=[.!?])\s+', html.unescape(description))) if part][:3]
    rows = rows or {}                       # 🧰 what the page itself asks the header to show (host_rows): its 💾 📂, its ⚙️ and ⋯ rows
    return {'id': 'tools', **({'home': prefix + 'index.html#tools'} if home else {}), 'tools': {**(tools or {}), **rows.get('tools', {})},
            'settings': rows.get('settings', []), 'screen': rows.get('screen', []),
            'board': {'title': title, 'items': (about + [{'text': card['title']} for card in cards])[:12]}}


def tools_door(ui, prefix: str = '../../', here: str | None = None, title: str = '') -> dict[str, str]:
    """🚪 PySaiyanWeBoo's Door-to-Door as the page's foot (``door_html(foot=True)``), as component parts: 🏠 the cards, then every
    tool (``tools_places``); ``here`` (this page's href) is the door you came in by, and a page that is no tool is added as 📌 ``title``.
    After the pull-down: 🐦 the X account and 📦 this page's size (``pysaiyanweboo.stamp_page_size`` writes it once the page is whole)."""
    pages = [{'emoji': '🏠', 'label': 'Tools', 'href': prefix + 'index.html#tools'},
             *({'emoji': mark, 'label': words, 'href': place['href']} for place in tools_places(prefix) for mark, _, words in [place['label'].partition(' ')])]
    if here and not any(page['href'] in (here, here + '#' + page['href'].partition('#')[2]) for page in pages):   # 🧰 the screen's #panels are here
        pages.append({'emoji': '📌', 'label': title[:40] or here, 'href': here})
    door = {'schema': ui.DOOR_SCHEMA, 'k': 0, 'pages': pages, **({'current': here} if here in {page['href'] for page in pages} else {})}
    x = [{'emoji': '🐦', 'label': f'X (Twitter) @{X_URL.rpartition("/")[2]}', 'href': X_URL}]
    return ui.component_parts('door', door, foot=True, links=x, size=True)


X_URL = 'https://twitter.com/myonitbusiness'


def add_site_chrome(page: str, path: str | None = None, tools: dict | None = None, description: str | None = None, *,
                    title: str = 'TOOLS', home: bool = True) -> str:
    """🧰 The parts every page of the site shares, for the page published at ``path`` (``tools/gif/index.html``; left out: two folders
    below the root, and no door marked as this page): the header (``tools_chrome``: the board with ``description``, 🫧 the round face
    that follows the pointer, 🏠 ⭐ ⚙️), the side
    (☰ ⋯) and the foot (``tools_door``: 🚪 every tool as a pull-down, 🐦 X, 📦 the page's size). ``description`` left out is the text
    of the 🧰 Tools card that leads here, else the page's own ``<meta name="description">``, else a line any page can carry (its
    title and where 🚪 🏠 lead; a placeholder until the page says what it is).

    🌍 A world page already has the header and the side (``<header class="ui-world-head">``: its own board and menus, the same
    parts), so it gets what it lacks: 🫧 in that header (in each scene's, when one page holds several: the school and the cities
    have it like the village) and the foot.

    🎨 Every page is published in one look: the shared sheet's ``modern`` theme, the front page's default. A page built with
    another palette on its ``<body>`` (Ironmate's studios: green; the MCP lab: terminal or github-like) is switched to it, and the
    chrome then takes the page's own colours; a page with no ``data-ui-theme`` keeps it and gets the chrome's colours with the chrome.
    The way back spans a grid ``<main>``'s whole first row, so it never takes the place of a column (Ironmate's three-column studio).
    🧰 A page may ask the header to show rows of its own (``host_rows``: Ironmate's studios, one 💾 with every format); the page's
    own menus those rows replace are hidden, so the header is the one place.
    The parts are PySaiyanWeBoo's (``component_parts("chrome" | "door" | "gaze-avatar")``, put on the page by ``add_part``): a page
    whose CSP lists its scripts or styles without ``'unsafe-inline'`` (HTML import, Ironmate's studios) gets their hashes listed,
    nothing wider."""
    import pysaiyanweboo as ui
    prefix = ('../' * path.count('/') or './') if path else '../../'
    here = prefix + re.sub(r'index\.html$', '', path) if path else None
    if description is None:
        meta = re.search(r'<meta name="description" content="([^"]*)"', page)
        description = next((place['text'] for place in tools_places(prefix) if place['href'] == here), meta[1] if meta else '')
    heading = re.search(r'<title>(.*?)</title>', page, re.S)
    name = html.unescape(heading[1]).strip() if heading else ''
    description = description or f'{name or "myon-bioinformatics"}：myon-bioinformatics の道具のページ。🚪 でほかの道具へ、🏠 で一覧へ。'
    body = re.search(r'<body\b[^>]*>', page)
    if body and 'data-ui-theme="' in body[0]:
        page = page[:body.start()] + re.sub(r'data-ui-theme="[^"]*"', 'data-ui-theme="modern"', body[0], count=1) + page[body.end():]
    own = 'data-ui-theme="modern"' in page        # 🎨 modern: the parts take the page's colours; else they bring theirs (add_part's scope)
    rows = host_rows(page)                   # 🧰 the page's own 💾 📂 ⚙️ ⋯ rows go into the one header; the menus they replace are hidden
    face, head = ui.component_parts('gaze-avatar'), ui.component_parts('chrome', tools_chrome(prefix, tools, description, title=title, home=home, rows=rows))
    tools_nav, world = '<nav class="ui-world-tools">', '<header class="ui-world-head">' in page
    hide = rows['replaces'] + '{display:none}' if rows.get('replaces') else ''
    page = ui.add_part(page, {'css': face['css'] + '.ui-world-head .ui-gaze{flex:none;margin:0 4px}main>nav.ui-back{grid-column:1/-1}' + hide, 'js': face['js']})
    if world:
        page = page.replace(tools_nav, face['html'] + tools_nav)                                   # 🫧 after each scene's own board (one shows at a time)
    else:
        head['html'] = head['html'].replace(tools_nav, face['html'] + tools_nav, 1)               # 🫧 after the board
        page = ui.add_part(page, head, at='top', scope=None if own else '.ui-chrome')
    door = tools_door(ui, prefix, here if path and '/' in path else None, name)
    return ui.stamp_page_size(ui.add_part(page, door, scope=None if own else '.ui-door-foot'))


def add_back_nav(page: str, path: str | None = None, tools: dict | None = None) -> str:
    """🏠 PySaiyanWeBoo's way back (``back_nav_html``) to the 🧰 Tools cards, right after <main> (else <body>), then the site's
    shared header, side and foot (``add_site_chrome``; a 🌍 world page keeps its own header and side and gets 🫧 and the foot). A
    page that already has them keeps them, and a fragment without <head> and <body> gets the way back only."""
    import pysaiyanweboo as ui
    prefix = '../' * path.count('/') if path else '../../'
    # Studio pages already have the same destination in the site's header.
    # Keep the standalone back link for fragments and other page contracts.
    studio = path in {f'tools/{entry}index.html' for entry in _STUDIO_ROUTES.PUBLIC_STUDIO_ENTRIES}
    full_page = '</head>' in page and '<body' in page
    if not (studio and full_page):
        page = ui.add_back_nav(page, [{'label': '← 🧰 Tools', 'href': prefix + 'index.html#tools'}], test_id='portfolio-back')
    if '<div class="ui-door-foot">' in page or not full_page:
        return page                               # a page that has it, or a fragment with no <head> and <body> to carry it
    return add_site_chrome(page, path, tools)


def add_home_label(page: str, label: str, *, icons_from: str | None = None) -> str:
    """📱 PySaiyanWeBoo's ``home_label``: the home-screen shortcut is named ``label``; ``icons_from`` (the way back to the site
    root, ``'../../'``) also gives the page the portfolio's tab icon and home-screen icon. Idempotent; 📦 the foot's size follows."""
    import pysaiyanweboo as ui
    icons = {} if icons_from is None else {'icon': f'{icons_from}assets/brand/favicon-32x32.png',
                                           'touch_icon': f'{icons_from}assets/brand/myon-profile-icon.png'}
    return ui.stamp_page_size(ui.home_label(page, label, **icons))


def render_front(root: Path = ROOT, samples=frozenset()) -> dict[str, bytes]:
    """The portfolio's own front page (scripts/front_page.py), built from profile.json, api/repos.json and projects.json, with the
    site's shared header, side and foot (``add_site_chrome``: the board reads the page's description, ☰ lists its sections).

    It is not in the lock: api/repos.json is refreshed by a workflow, and the page must follow it without a lock refresh."""
    front = _front_module()
    return {'index.html': add_site_chrome(front.document(root, samples=samples), 'index.html', front.LINKS, title='MYON', home=False).encode('utf-8')}


def render_world(ui) -> dict[str, bytes]:
    page = add_back_nav(world_page(ui), WORLD_PAGE)
    return {WORLD_PAGE: add_home_label(page, '🌍 ワールド', icons_from='../../').encode('utf-8')}


def render_pswb_tools(ui) -> dict[str, bytes]:
    """🧾 PySaiyanWeBoo's own tool documents (``PSWB_TOOLS``), each a #panel of the one 🧰 screen (``render_shell``)."""
    return {path: build(ui).encode('utf-8') for path, (build, _) in PSWB_TOOLS.items()}


def html_import_files(ui):
    return ui.html_import_files(shared_base="../vendor/web-ui", docs_href="../../docs/html-import.md")


def render_html_import(ui) -> dict[str, bytes]:
    document = html_import_files(ui)["index.html"].decode()
    document = add_home_label(add_back_nav(document, HTML_IMPORT_PAGE), '📄 HTML取込', icons_from='../../')
    return {HTML_IMPORT_PAGE: document.encode()}


def pages_urls(root: Path = ROOT) -> dict[str, str]:
    """Repository name → its GitHub Pages root, from api/repos.json (generated from GitHub's ``has_pages``)."""
    path = root / 'api/repos.json'
    repos = json.loads(path.read_text(encoding='utf-8'))['repos'] if path.is_file() else []
    return {repo['name']: repo['pages'] for repo in repos if repo.get('pages') and not repo.get('archived')}


# ── 🎞 GIF工房 and 🎥 the moving samples: both draw with PySaiyanWeBoo's gif.js (window.UiGif) ──────────────────────────
GIF_PAGE = 'tools/gif/index.html'
SAMPLES = 'media/pages/'          # 🎥 one moving sample per repository's Pages, recorded at deploy time (not kept in git)
def render_gif_tool(ui) -> dict[str, bytes]:
    """🎞 GIF工房: PySaiyanWeBoo's ``gif_maker_document`` — images the visitor picks become one looping GIF in the page."""
    page = ui.gif_maker_document(filename='gif-kobo.gif', css=ui.bundled_css())   # the shared sheet is the 🧰 screen's (render_shell)
    return {GIF_PAGE: page.encode('utf-8')}


def recorded_samples(output: Path) -> frozenset[str]:
    """The lower-case names whose 🎥 sample is under ``output`` (the front page shows only those): a repository's name, or
    ``tools/<id>`` for a 🧰 Tools card."""
    folder = Path(output) / SAMPLES
    return frozenset(path.relative_to(folder).as_posix().removesuffix('.gif') for path in folder.rglob('*.gif'))


def tools_samples() -> dict[str, tuple[str, str]]:
    """🧰 ``tools/<id>`` → (the page the card opens first, the card's title): what ``--record-samples`` records for the 🧰 Tools cards."""
    front = _front_module()
    return {f'tools/{card["id"]}': (urljoin(front._site_url, card['links'][0][1]), card['title']) for card in front.PORTAL}


def sample_stand_in(title: str) -> str:
    """🖼 What a 🧰 Tools card's picture shows when its page could not be recorded: the page's name and ⏳, in the site's look,
    so the cards stay alike (``record_samples(stand_ins=…)``)."""
    import pysaiyanweboo as ui
    return ui.page_document({'schema': 'web-ui-page/1', 'title': title, 'theme': 'modern', 'blocks': [
        {'type': 'heading', 'text': '🎥 ⏳', 'level': 2}, {'type': 'text', 'text': 'このページはまだ撮れていません。次の公開で撮り直します。', 'muted': True}]})


def record_samples(output: Path, pages: dict[str, str], *, viewport=(392, 704), size=(240, 432), max_bytes=300_000,
                   browser=None, captions: dict[str, str] | None = None, stand_ins: dict[str, str] | None = None) -> list[str]:
    """🎥 Open each page in Chromium at phone size, keep the top and one screen further down, and write a two-frame GIF
    per name as ``output/media/pages/<name>.gif`` with gif.js (a name may hold a folder: ``tools/gif``). The caption is
    ``captions[name]``, else ``🌐 name``. Best effort: one line per name (🎥 / ⏸). A name in ``stand_ins`` (name → HTML) whose
    page cannot be opened gets that HTML as its picture instead (⏸ … 🖼), so it is never left without one.
    ``browser``: a launched Playwright browser to use (a caller already inside Playwright); otherwise Chromium is started."""
    if browser is None:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            chromium = playwright.chromium.launch()
            try:
                return record_samples(output, pages, viewport=viewport, size=size, max_bytes=max_bytes, browser=chromium, captions=captions,
                                      stand_ins=stand_ins)
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
        def save(name: str, frames: list[bytes]) -> int:
            encoder.evaluate('o => { window.rec = new UiGif.Recorder(o); }', {'width': size[0], 'height': size[1], 'caption': 24})
            encoder.evaluate('items => rec.add(items)', [{'png': base64.b64encode(png).decode('ascii'), 'caption': (captions or {}).get(name, f'🌐 {name}'),
                                                         'ok': True, 'delay': 1500} for png in frames])
            gif = base64.b64decode(encoder.evaluate('o => rec.encodeBase64(o)', {'maxBytes': max_bytes})['gif'])
            (folder / f'{name.lower()}.gif').parent.mkdir(parents=True, exist_ok=True)
            (folder / f'{name.lower()}.gif').write_bytes(gif)
            return len(gif) // 1024

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
                lines.append(f'🎥 {name}: {len(frames)} frames · {save(name, frames)} KiB')
            except Exception as exc:                       # one Pages failing keeps the rest (and the deploy) going
                lines.append(f'⏸ {name}: {type(exc).__name__}: {str(exc).splitlines()[0][:120] if str(exc) else ""}')
                if name in (stand_ins or {}):
                    try:
                        site.set_content(stand_ins[name])
                        lines[-1] += f' · 🖼 {save(name, [site.screenshot()])} KiB'
                    except Exception:                      # no picture then: the card keeps its links in words
                        pass
    finally:
        site_context.close()
        encoder_context.close()
    return lines


# ── 🌊 流れの実験室: every FFSS scene as it moves (FFSS's demo GIFs) and every DRAgoWing figure from the same records ──
FLOW_PAGE = 'tools/flow/index.html'
FLOW = 'media/flow/'                     # recorded at deploy time (pages.yml), with receipt.json; not kept in git
FLOW_REPOSITORIES = {'ffss': 'myon-bioinformatics/FluidFullSpeedSimulation', 'dragowing': 'myon-bioinformatics/DRAgoWing'}
FLOW_EXPERIMENTS = ('E30', 'E31', 'E32')
# 📊 which DRAgoWing figure sits with which FFSS scene; a figure not named here still shows, after the scenes
FLOW_FIGURES = {'circulation': ('blood-flow',), 'coal-power': ('energy-coal',), 'combined-cycle': ('energy-gtcc',),
                'heat-pump': ('balance-point',), 'hrsg-loop': ('pinch-tq',), 'startup': ('startup',), 'metal': ('rate-window',)}


def collect_flow(output: Path, ffss: Path, dragowing: Path, commits: dict[str, str]) -> dict:
    """Run FFSS's experiments and every demo in ``ffss`` and DRAgoWing's figures from those same records in ``dragowing``
    (both ``python -S``, standard library only), copy each GIF and SVG to ``output/media/flow/`` and write the receipt
    (commits, the demos as FFSS lists them in demos.json, and the figures made) there; returns the receipt."""
    folder = Path(output) / FLOW
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        run = lambda cwd, *args: subprocess.run([sys.executable, '-S', *args], cwd=cwd, check=True, capture_output=True, timeout=900)
        for experiment in FLOW_EXPERIMENTS:
            run(ffss, 'fluidfullspeedsimulation.py', 'run', experiment, '--jsonl', str(tmp / f'{experiment}.jsonl'))
        (tmp / 'records.jsonl').write_bytes(b''.join((tmp / f'{e}.jsonl').read_bytes() for e in FLOW_EXPERIMENTS))
        run(ffss, 'fluidfullspeedsimulation.py', 'demos', '--out-dir', str(tmp / 'demos'))      # 🎞 all of them, none picked
        run(dragowing, 'dragowing.py', '--ffss', str(tmp / 'records.jsonl'), '--out', str(tmp / 'figures'))
        listed = json.loads((tmp / 'demos' / 'demos.json').read_text(encoding='utf-8'))['demos']
        demos = []
        for demo in listed:
            gif = tmp / 'demos' / demo['file']
            if gif.is_file():
                shutil.copyfile(gif, folder / f"{demo['id']}.gif")
                demos.append({key: demo[key] for key in ('id', 'icon', 'scene', 'fluid')})
        figures = []
        for svg in sorted((tmp / 'figures' / 'svg').glob('F*_*.svg')):
            shutil.copyfile(svg, folder / svg.name)
            figures.append(svg.stem)
    receipt = {'schema': 'flow-lab/2', 'commits': commits, 'demos': demos, 'figures': figures}
    (folder / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
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
            f"🎞 {len(receipt['demos'])} 場面: " + ' '.join(f"{d['icon']}{d['id']}" for d in receipt['demos']),
            f"📊 {len(receipt['figures'])} 図: " + ' '.join(receipt['figures'])]


FLOW_MARKDOWN = 'tools/flow/records.md'
FLOW_RIG_JS = 'tools/flow/rig.mjs'
FLOW_RIG = """
<section id="workbench" aria-labelledby="flow-heading">
<h2 id="flow-heading">モニアック式の実験台</h2>
<p>入口と出口の弁を動かし、観察槽の残量を比べます。4素材は同じ収支モデルの例で、物性の再現ではありません。</p>
<div class="flow-fields">
<label>素材 <select id="flow-medium"><option value="water">水</option><option value="gold">金</option>
<option value="currency">通貨</option><option value="noodles">そうめん</option></select></label>
<label>入口 / 秒 <input id="flow-in" type="number" min="0" max="100" step="1" value="5" required></label>
<label>出口 / 秒 <input id="flow-out" type="number" min="0" max="100" step="1" value="2" required></label>
</div>
<div class="flow-controls">
<button id="flow-run" type="button" disabled>開始</button>
<button id="flow-step" type="button" disabled>1秒進める</button>
<button id="flow-reset" type="button" disabled>初期化</button>
</div>
<noscript><p>操作するにはJavaScriptを有効にしてください。</p></noscript>
<div class="flow-fields">
<label>供給槽 <meter id="flow-source" min="0" max="100" value="100"></meter></label>
<label>観察槽 <meter id="flow-middle" min="0" max="100" value="0"></meter></label>
<label>回収槽 <meter id="flow-sink" min="0" max="100" value="0"></meter></label>
</div>
<p id="flow-status">0秒 · 供給 100 L · 観察 0 L · 回収 0 L</p>
<figure><figcaption>観察槽の残量（直近60秒・縦軸0〜100）</figcaption>
<svg id="flow-chart" viewBox="0 0 240 104" role="img" aria-label="観察槽の残量グラフ">
<path d="M2 2v100h236" fill="none" stroke="currentColor" opacity=".45"/>
<polyline id="flow-line" points="2,102" fill="none" stroke="currentColor" stroke-width="2"/>
</svg></figure>
</section>
"""
FLOW_RIG_CSS = """<style>
.flow-fields,.flow-controls{display:flex;gap:.75rem;flex-wrap:wrap;margin-block:1rem}
.flow-fields label{display:grid;gap:.25rem}
.flow-fields input{width:5em}
#workbench :is(input, select, button){font:inherit}
#flow-chart{width:min(100%,420px);display:block}
</style>"""
FLOW_RIG_SOURCE = r"""
const total = 100;
const limit = n => Number.isFinite(n) ? Math.min(total, Math.max(0, n)) : 0;
export function flowStep({source, middle, sink}, inlet, outlet) {
  const incoming = Math.min(source, limit(inlet));
  const outgoing = Math.min(middle + incoming, limit(outlet));
  return {source: source - incoming, middle: middle + incoming - outgoing, sink: sink + outgoing};
}
if (typeof document !== "undefined") {
  const get = id => document.getElementById("flow-" + id);
  const units = {water: "L", gold: "g", currency: "円", noodles: "束"};
  let tanks, elapsed, history, timer = null;
  function render() {
    const unit = units[get("medium").value];
    for (const [name, n] of Object.entries(tanks)) get(name).value = n;
    get("status").textContent =
      `${elapsed}秒 · 供給 ${tanks.source} ${unit} · 観察 ${tanks.middle} ${unit} · 回収 ${tanks.sink} ${unit}`;
    get("line").setAttribute("points", history.map((n, i) => `${2 + (236 * i / 60)},${102 - n}`).join(" "));
  }
  function stop() {
    if (timer !== null) clearInterval(timer);
    timer = null;
    get("run").textContent = "開始";
    get("step").disabled = false;
  }
  function tick() {
    if (!get("in").reportValidity() || !get("out").reportValidity()) { stop(); return; }
    tanks = flowStep(tanks, get("in").valueAsNumber, get("out").valueAsNumber);
    elapsed++;
    history.push(tanks.middle);
    if (history.length > 61) history.shift();
    render();
  }
  function reset() {
    stop();
    tanks = {source: total, middle: 0, sink: 0};
    elapsed = 0;
    history = [0];
    render();
  }
  get("run").onclick = () => {
    if (timer !== null) { stop(); return; }
    if (!get("in").reportValidity() || !get("out").reportValidity()) return;
    timer = setInterval(tick, 1000);
    get("run").textContent = "一時停止";
    get("step").disabled = true;
  };
  get("step").onclick = tick;
  get("reset").onclick = reset;
  get("medium").onchange = reset;
  for (const name of ["run", "reset"]) get(name).disabled = false;
  reset();
}
"""


def flow_markdown(demos: list[dict], figures: list[str]) -> str:
    """One record of all displayed media, in FFSS order, with unmatched figures last."""
    def label(value: str) -> str:
        return str(value).replace('\n', ' ').replace('[', '（').replace(']', '）').replace('<', '＜').replace('>', '＞')

    named = {name.split('_', 1)[-1]: name for name in figures}
    lines = ['# 流れの実験記録']
    used = set()

    def figure(name):
        return f'![📊 DRAgoWing {label(name)}](../../{FLOW}{name}.svg)'

    for demo in demos:
        name, scene = demo['id'], demo['scene']
        fluid = '' if demo['fluid'] == 'water' else f" · {demo['fluid']}"
        title = label(f"{demo['icon']} {name} {scene}{fluid}")
        lines += [f'## {title}', f'![🌊 FFSS {label(name)}: {label(scene)}](../../{FLOW}{name}.gif)']
        for key in FLOW_FIGURES.get(scene, ()):
            if key in named:
                used.add(named[key])
                lines.append(figure(named[key]))
    remaining = [name for name in figures if name not in used]
    if remaining:
        lines += ['## 📊 ほかの図', *map(figure, remaining)]
    if not demos and not figures:
        lines.append('⏸ このビルドでは記録していない')
    return '\n\n'.join(lines) + '\n'


def render_flow(ui, output: Path | None = None) -> dict[str, bytes]:
    """Render the lab and a Markdown-derived archive from the same published flow receipt."""
    import markdown as md_market

    path = Path(output) / FLOW / 'receipt.json' if output else None
    receipt = json.loads(path.read_text(encoding='utf-8')) if path and path.is_file() else {}
    commits, demos, figures = receipt.get('commits', {}), receipt.get('demos', []), receipt.get('figures', [])
    link = lambda key: (f"https://github.com/{FLOW_REPOSITORIES[key]}/tree/{commits[key]}"
                        if key in commits else f"https://github.com/{FLOW_REPOSITORIES[key]}")
    blocks = [{'type': 'text', 'text': '水・金・通貨・そうめんを選んで、入口と出口の流量を比べます。'},
              {'type': 'text', 'text': 'FLOW_RIG_SLOT'},
              {'type': 'kv', 'rows': [['🌊', f"FFSS {commits.get('ffss', '—')[:7]} · 🎞 {len(demos)} 場面"],
                                      ['📊', f"DRAgoWing {commits.get('dragowing', '—')[:7]} · {len(figures)} 図"]]},
              {'type': 'links', 'items': [{'label': '📜 実験記録を見る', 'href': '#records'},
                                          {'label': 'Markdown原本', 'href': './records.md'},
                                          {'label': '🌊 FFSS', 'href': link('ffss')},
                                          {'label': '📊 DRAgoWing', 'href': link('dragowing')}]}]
    if not demos and not figures:
        blocks.append({'type': 'text', 'text': '⏸ このビルドでは記録していない'})
    blocks.append({'type': 'section', 'title': '📜 実験記録', 'blocks': [{'type': 'text', 'text': 'FLOW_RECORDS_SLOT'}]})   # #records, one page
    page = ui.page_document({'schema': 'web-ui-page/1', 'title': '🌊 流れの実験室', 'blocks': blocks})
    slot = '<p>FLOW_RIG_SLOT</p>'
    if page.count(slot) != 1:
        raise ValueError('flow workbench placeholder missing')
    page = page.replace(slot, FLOW_RIG, 1).replace('</head>', FLOW_RIG_CSS + '</head>', 1)
    page = page.replace('</body>', '<script type="module" src="./rig.mjs"></script></body>', 1)

    records = flow_markdown(demos, figures)   # 📜 the same page, below the rig: its pictures load only when scrolled to
    slot = '<p>FLOW_RECORDS_SLOT</p>'
    if page.count(slot) != 1:
        raise ValueError('flow records placeholder missing')
    archive = md_market.markdown_to_html(records).replace('<img src="../../media/flow/', '<img loading="lazy" src="../../media/flow/')
    page = page.replace(slot, f'<div id="records">{archive}</div>', 1)
    page = page.replace('</head>', '<style>#records img{max-width:100%;height:auto}</style></head>', 1)
    return {FLOW_PAGE: page.encode('utf-8'),   # 🧰 a #panel of the one screen (render_shell)
            FLOW_MARKDOWN: records.encode('utf-8'), FLOW_RIG_JS: FLOW_RIG_SOURCE.encode('utf-8')}


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
    return {MAP_PAGE: page.encode('utf-8')}   # 🧰 a #panel of the one screen (render_shell)


# ── 💬 横断チャット: scripts/chat.py in Pyodide with the pinned markdown.py · ascii_artist.py · cli_args.py (pages group);
# what it knows of the other repositories is recorded at deploy time (media/chat/, not kept in git) ──
CHAT = 'media/chat/'
_CHAT_SLOT = '💬chat-slot'
CHAT_CSS = '.ui-step [data-chat-say]{margin-top:8px}'    # 📇 the index's "💬 送る"; the chat itself is PySaiyanWeBoo's (chat.css)
# 💬 the page's part of the chat: the bubbles, Enter, chips and 😀 reactions are PySaiyanWeBoo's chat component (chat.js, webUiChat);
# here are only the bot (chat.py in Pyodide), 🤖 /ask (wllama) and the index's buttons
WLLAMA_JS = r"""
function localModel(runtime){
 let llm=null,busy=false;
 return async(messages,show,limit=256)=>{
  if(busy)throw new Error("生成中です");
  busy=true;
  try{
   if(!llm){
    show("⏳ 🤖 llama.cpp…");
    const {Wllama}=await import(runtime.wllama+"index.js");
    const engine=new Wllama({default:runtime.wllama+"wasm/wllama.wasm"});
    try{
     await engine.loadModelFromUrl(runtime.model,{n_ctx:2048,progressCallback:({loaded,total})=>
      show(`⏳ 🤖 ${total?Math.round(100*loaded/total):0}% · ${Math.round(loaded/2**20)} / ${Math.round(total/2**20)} MB`)});
    }catch(error){await engine.exit?.();throw error}
    llm=engine;
   }
   let output="",tokens=0;
   const start=performance.now();
   await llm.createChatCompletion({messages,max_tokens:limit,temperature:0.3,stream:true,
    chat_template_kwargs:{enable_thinking:false},onData:chunk=>{
     output+=chunk.choices?.[0]?.delta?.content??"";tokens++;show(output);
    }});
   return {output,tokens,seconds:(performance.now()-start)/1000,llm};
  }finally{busy=false}
 };
}
"""

CHAT_JS = WLLAMA_JS + r"""const $ = (s) => document.querySelector(s);
const cfg = JSON.parse($("#chat-config").textContent);
const [chat] = webUiChat.bindChat(document);
let bot = null;
const generateAnswer=localModel(cfg.runtime);
async function ask(text,reply){
 const {output,tokens,seconds,llm}=await generateAnswer(JSON.parse(bot.ask_messages(text)),s=>reply.text(s));
 return bot.ask_html.callKwargs(output,tokens,seconds,
     {threads:llm.isMultithread()?navigator.hardwareConcurrency:1,webgpu:llm.isSupportWebGPU()});
}
chat.respond = (text, reply) => /^\/ask(\s|$)/i.test(text.trim()) ? ask(text, reply) : bot.reply_html(text);
document.addEventListener("click", (event) => {         // 📇 a step of the index (beside the chat) sends its command there
  const chip = event.target.closest(".ui-step [data-chat-say]");
  if (!chip) return;
  const tab = $("#ui-tabs-chat-0");
  if (tab) tab.checked = true;
  chat.say(chip.dataset.chatSay);
});
for (const step of document.querySelectorAll(".ui-step")) {            // 📇 each step of the index can be sent as it is
  const command = step.querySelector("pre")?.textContent ?? "";
  const button = Object.assign(document.createElement("button"), {type: "button", className: "ui-button", textContent: "💬 送る"});
  button.dataset.chatSay = command;
  step.querySelector(".ui-code")?.after(button);
}
async function boot() {
  const {loadPyodide} = await import(cfg.runtime.pyodide + "pyodide.mjs");
  const py = await loadPyodide({indexURL: cfg.runtime.pyodide});
  py.FS.mkdirTree("/chat");
  const sources = await (await fetch(cfg.sources)).json();                       // 🐍 the Python, fetched when the chat opens
  for (const [name, text] of Object.entries(sources)) py.FS.writeFile("/chat/" + name, text);
  let index = null;
  try { const response = await fetch(cfg.index); if (response.ok) index = await response.text(); } catch {}
  py.runPython("import sys; sys.path.insert(0, '/chat')");
  bot = py.pyimport("chat");
  bot.configure(index, new URL(cfg.base, location.href).href);
  const files = index ? JSON.parse(index).files?.length : undefined;
  chat.status(`✅ 🐍 ${py.runPython("import sys; sys.version.split()[0]")} · ` + (files === undefined ? "⏸ 索引なし" : `🔎 ${files} files`));
  chat.ready();
  document.documentElement.dataset.chatReady = "true";
}
boot().catch((error) => { chat.status("⚠️ Python を読み込めない: " + (error?.message ?? error)); });
"""


@functools.lru_cache(maxsize=None)
def _chat() -> ModuleType:
    """💬 scripts/chat.py, loaded once (it imports the pinned markdown, ascii_artist and cli_args)."""
    return load_module('chat', 'scripts/chat.py')


def chat_sources() -> dict[str, str]:
    """The Python the page writes into Pyodide: chat.py and the pinned modules it imports, by file name."""
    chat = _chat()
    sources = {'chat.py': (ROOT / 'scripts/chat.py').read_text(encoding='utf-8')}
    for name in chat.MODULES:
        sources[f'{name}.py'] = Path(importlib.util.find_spec(name).origin).read_text(encoding='utf-8')
    return sources


def chat_books() -> list[dict]:
    """📇 The index as a runbook (records, search and state filter, as in olnm's guide): one book per kind of tool, one
    step per example; the expected reply is the bot's own where it needs nothing recorded at deploy time."""
    chat = _chat()
    groups = [('📝 Markdown', ('md', 'table', 'help')), ('🎨 ASCII art', ('ascii', 'box', 'flow')), ('🗂 圧縮 · 🔌 MCP', ('compress', 'mcp')),
              ('🔎 JSON / JSONL', ('find', 'show')), ('🧬 オントロジー', ('onto', 'guess')), ('🧷 OLNM', ('olnm',)),
              ('🤖 LLM', ('ask',)), ('⌨️ もしかして', ())]           # (a runbook holds 1..8 books)
    recorded = {'compress': '🗂 TalkCompress の短い文と 📏 文字数（TalkCompress は公開時に記録）',
                'mcp': '🔌 mcp-toolcall-lab が広告する道具で判定（✅ 送ってよい／❌ 断る。道具は公開時に記録）',
                'find': '🔎 公開時に取得できた JSON / JSONL の索引から検索', 'show': '👀 そのコミットの raw を読んで表に',
                'onto': '🧬 OnTautoLogy の概念の台帳（concepts-*.json、索引のコミットの raw）から、属（似たものと共通）と種差（決め手）',
                'guess': '🎯 台帳の概念を 1 つ思い浮かべて y / n / ? で回答。最後に候補名を確認する',
                # argparse's error text varies by Python release; the live chat still shows its suggestions.
                'typo': '⌨️ もしかして: 入力ミスに近いコマンドや引数を提案する',
                'ask': '🤖 初回だけ約 560 MB のモデルを読み、端末の中で答える（⚡ WebGPU があれば GPU、なければ 🧮 CPU 1 スレッド）'}
    books = []
    for label, names in groups:
        examples = [(name, example) for name in names for example in chat.COMMANDS[name][3]] or [('typo', t) for t in chat.TYPOS]
        steps = []
        for i, (name, example) in enumerate(examples):
            expect = recorded.get(name) or chat.respond(example, index={})
            steps.append({'id': f'{name}-{i}', 'title': f'{chat.COMMANDS.get(name, ("⌨️",))[0]} {example.splitlines()[0][:60]}',
                          'command': example, 'expect': expect if len(expect) <= 1000 else expect[:999] + '…'})
        books.append({'label': label, 'runbook': {'key': f'portfolio/chat/{names[0] if names else "typo"}', 'steps': steps}})
    return books


def chat_document(ui) -> str:
    """💬 The chat page: 💬 the conversation (Pyodide runs chat.py in the page) and 📇 the index of what it answers."""
    chat = _chat()
    page = ui.page_document({'schema': 'web-ui-page/1', 'title': '💬 横断チャット', 'description':
                             'markdown.py・ascii_artist・cli_args・TalkCompress・mcp-toolcall-lab・OnTautoLogy・OLNM をページの中の Python で。'
                             '公開リポジトリの JSON / JSONL を索引から検索できる。🤖 /ask は llama.cpp が端末の中で答える。'
                             '送った文はどこにも送らない（/show は GitHub の raw を、/ask はモデルを読むだけ）。',
                             'blocks': [{'type': 'tabs', 'id': 'chat', 'tabs': [
                                 {'label': '💬 チャット', 'blocks': [{'type': 'text', 'text': _CHAT_SLOT}]},
                                 {'label': '📇 索引', 'blocks': [{'type': 'runbook', 'id': 'chat-index', 'choice': '📇 道具',
                                                                  'books': chat_books()}]}]}]})
    parts = ui.component_parts('chat', chat_id='chat-box', placeholder='/help · /flow a > b · onto', ready=False,     # 💬 PySaiyanWeBoo's chat
                               chips=[(f'{icon} /{name}', example) for name, (icon, _, _, (example, *_)) in chat.COMMANDS.items()],
                               status='⏳ 🐍 Python（Pyodide）を読み込み中…')
    body = (parts['html'] + '<noscript><p>⏸ このチャットは JavaScript と Pyodide で動く。📇 索引のコマンドは scripts/chat.py でも試せる。</p></noscript>')
    data = lambda value: json.dumps(value, ensure_ascii=False).replace('<', '\\u003c')
    config = {'runtime': chat.RUNTIME, 'index': f'../{CHAT}index.json', 'base': f'../{CHAT}', 'sources': CHAT_SOURCES.removeprefix('tools/')}   # 🧰 from tools/
    body += (f'<script type="application/json" id="chat-config">{data(config)}</script>'
             + ui.module_script(parts['js']) + ui.module_script(CHAT_JS))
    slot = f'<p>{_CHAT_SLOT}</p>'
    if page.count(slot) != 1:
        raise ValueError('chat page has no single slot')
    return page.replace(slot, body, 1).replace('</head>', f'<style>{parts["css"]}{CHAT_CSS}</style></head>', 1)


CHAT_PAGE = 'tools/chat/index.html'   # 💬 a #panel of the 🧰 screen (render_shell), not one of the 🤖 stubs
CHAT_SOURCES = 'tools/chat/sources.json'   # 🐍 chat_sources(), beside it: the page fetches them when the chat opens
def render_chat_tool(ui) -> dict[str, bytes]:
    """💬 横断チャット: ``chat_document``, a #panel of the 🧰 screen."""
    return {CHAT_PAGE: chat_document(ui).encode('utf-8')}


def _tree(repository: str, commit: str) -> tuple[list[tuple[str, int]], bool]:
    """Return the API's blob paths and sizes at ``commit``, plus its truncation flag."""
    github = load_module('repos_catalog', 'scripts/repos_catalog.py')
    data = github._get_json(f'{github.API_ROOT}/repos/{repository}/git/trees/{commit}?recursive=1')
    if not isinstance(data, dict) or not isinstance(data.get('tree'), list) or type(data.get('truncated')) is not bool:
        raise ValueError('invalid tree response')
    blobs = [(item['path'], item.get('size', 0)) for item in data['tree'] if item.get('type') == 'blob']
    return blobs, data['truncated']


def record_chat(output: Path, root: Path = ROOT, *, head=_ls_remote, raw=_raw, tree=_tree) -> list[str]:
    """💬 What the chat knows of the other repositories, at their current commits, under ``output/media/chat/``: index.json
    (observed JSON / JSONL paths and sizes, repository scan errors, the tools advertised by mcp-toolcall-lab,
    and README summaries from api/repos.json) and TalkCompress's shorthand compressor (talkcompress/).
    Repositories in commits without a scan error were fully listed."""
    catalog = json.loads((root / 'api/repos.json').read_text(encoding='utf-8'))
    folder = Path(output) / CHAT
    commits, files, tools, scan_errors, missed, compressor = {}, [], {}, {}, [], '⏸'
    for name in [repo['name'] for repo in catalog['repos'] if not repo.get('archived')]:
        try:
            commit = head(f'{OWNER}/{name}')
            blobs, truncated = tree(f'{OWNER}/{name}', commit)
        except Exception as exc:
            scan_errors[name] = 'unavailable'
            missed.append(f'⏸ {name}: {type(exc).__name__}')
            continue
        if truncated:
            scan_errors[name] = 'truncated_tree'
            missed.append(f'⚠️ {name}: truncated_tree')
        commits[name] = commit
        files += [[name, path, size] for path, size in blobs if path.lower().endswith(('.json', '.jsonl', '.ndjson'))]
        try:
            if name == 'mcp-toolcall-lab':
                for path, _ in blobs:
                    if path.startswith('fixtures/prompt_experiments/') and path.endswith('.json'):
                        fixture = json.loads(raw(f'{OWNER}/{name}', commit, path) or b'{}')
                        for tool in fixture.get('openai', {}).get('request', {}).get('tools', []):
                            tools.setdefault(tool['function']['name'], tool['function'])
            if name == 'TalkCompress':
                for path in _chat().TALKCOMPRESS:
                    data = raw(f'{OWNER}/{name}', commit, path)
                    if data is None:
                        raise FileNotFoundError(path)
                    (folder / 'talkcompress' / path).parent.mkdir(parents=True, exist_ok=True)
                    (folder / 'talkcompress' / path).write_bytes(data)
                compressor = f'✅ {commit[:7]}'
        except Exception as exc:
            missed.append(f'⏸ {name}: {type(exc).__name__}')
    folder.mkdir(parents=True, exist_ok=True)
    summaries = {}                                          # 🤖 what /ask tells the model of each one: its README summary
    for repo in catalog['repos']:
        text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', repo.get('description') or repo.get('readmeSummary') or '')
        text = ' '.join(text.split())
        if text and not repo.get('archived'):
            summaries[repo['name']] = text if len(text) <= 160 else text[:159] + '…'
    index = {'schema': 'chat-index/1', 'owner': OWNER, 'commits': commits, 'files': files, 'tools': list(tools.values()),
             'repos': summaries, 'scan_errors': scan_errors}
    (folder / 'index.json').write_text(json.dumps(index, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    return [f'💬 {len(commits)} repositories · {len(files)} JSON/JSONL · 🔌 {len(tools)} tools · 🗂 TalkCompress {compressor}', *missed]


# ── 🧰 道具: Ironmate's studios, mcp-toolcall-lab's tools and execution lab (🔌 MCP 実験室) and DRAgoWing's heatmap, built
# from their default branches at deploy time; each lives at its feature route, not at the repository's name ──
TOOLS = 'media/tools/receipt.json'       # what this build recorded; the pages live under their folders (not kept in git)
# key: (repository, folder under the site, entry pages inside it). The lab's tools come before its execution lab, which
# lives inside them (a tool replaces its whole folder).
_STUDIO_ROUTES = load_module('studio_routes', '_src/tools/studio_routes.py')
TOOL_SOURCES = {'ironmate': ('myon-bioinformatics/Ironmate', 'tools', _STUDIO_ROUTES.PUBLIC_STUDIO_ENTRIES),
                'mcp-toolcall-lab': ('myon-bioinformatics/mcp-toolcall-lab', 'tools/mcp', ('',)),
                'mcp-toolcall-lab-execution': ('myon-bioinformatics/mcp-toolcall-lab', 'tools/mcp/execution', ('',)),
                'format-lab': ('myon-bioinformatics/myon-bioinformatics', 'tools/format-lab', ()),   # () : a #panel of the 🧰 screen
                'dragowing': ('myon-bioinformatics/DRAgoWing', 'tools/heatmap', ())}
CHECKOUTS = '.test-deps'   # 🧪 local checkouts (CI pins them) that --stage builds the tools from, one folder per repository


def _back_to_tools(page: str, path: str) -> str:
    """The way back to 🧰 Tools and the chrome (``add_back_nav``) from ``path`` (any depth)."""
    return add_back_nav(page, path)


def collect_tools(output: Path, checkouts: dict[str, Path], commits: dict[str, str]) -> dict:
    """Build each tool from its checkout with this ``python`` (📦 its pages group carries the pinned PySaiyanWeBoo the tools
    render through; the lab's build also runs Node) into ``output/<folder>/``,
    give each entry page the way back, and write the receipt; a tool that fails is left out. Returns the receipt."""
    made, failed = [], {}
    for key, (repository, folder, entries) in TOOL_SOURCES.items():
        if key not in checkouts:
            continue
        dest = Path(output) / folder
        try:
            with tempfile.TemporaryDirectory() as tmp:       # build aside; the ⏸ page stays unless the whole tool built
                built = Path(tmp) / 'site'
                run = lambda *args, env=None: subprocess.run([sys.executable, *args], cwd=checkouts[key], check=True,
                                                             capture_output=True, timeout=900, env=env)
                if key == 'ironmate':
                    run('image_studio.py', '--build-site', str(built))
                elif key == 'format-lab':
                    run('tools/format-lab/build.py', str(built))
                elif key == 'dragowing':                          # 🌡️ one page on stdout; its scenes open in Image Studio
                    built.mkdir()
                    (built / 'index.html').write_bytes(run('scripts/build_heatmap_page.py').stdout)
                elif key == 'mcp-toolcall-lab':                   # 🔌 Wiki · Pixiv · Pokémon and the diagnostics (Python only)
                    env = {**os.environ, 'PYTHONPATH': os.pathsep.join(('src', 'vendor'))}
                    run('-m', 'mcp_toolcall_lab.stub_front', 'pages', '--out', str(built), env=env)
                    run('-m', 'mcp_toolcall_lab.mcp_toolcall_lab_repository_diagnostics', str(built), env=env)
                    load_module('mcp_lab', '_src/tools/mcp_lab.py').stage_lab_tools(
                        built, commits[key], checkouts[key], _back_to_tools, add_home_label, folder)
                else:
                    run('scripts/build_portable_pages.py', '--source-sha', commits[key], '--out', str(Path(tmp) / 'lab'),
                        env={**os.environ, 'PYTHONPATH': 'src'})
                    shutil.move(str(Path(tmp) / 'lab' / 'execution'), str(built))
                    for copy in built.glob('runtime/**/*.html'):   # 🚫 a source copy of the page (it is index.html); runtime.zip keeps it
                        copy.unlink()
                if key == 'ironmate':
                    mapped = Path(tmp) / 'mapped'
                    _STUDIO_ROUTES.stage_ironmate_studios(built, mapped, _back_to_tools)
                    for entry in sorted(child.name for child in mapped.iterdir()):
                        target = dest / entry
                        if target.exists():
                            shutil.rmtree(target)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(mapped / entry), str(target))
                    made.append(key)
                    continue
                for entry in entries:                             # the way back (a page that has one keeps it)
                    page = built / entry / 'index.html'
                    document = _back_to_tools(page.read_text(encoding='utf-8'), f'{folder}/{entry}index.html')
                    if key == 'format-lab':
                        document = add_home_label(document, '🗃️ 形式検証', icons_from='../../')
                    page.write_text(document, encoding='utf-8')
                for _, inner, _ in TOOL_SOURCES.values():      # a tool inside this one (the execution lab) stays as it was
                    nested = inner[len(folder) + 1:] if inner.startswith(folder + '/') else ''
                    if nested and (dest / nested).exists() and not (built / nested).exists():
                        (built / nested).parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(dest / nested), str(built / nested))
                if dest.exists():
                    shutil.rmtree(dest)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(built), str(dest))
            made.append(key)
        except (OSError, subprocess.SubprocessError, ValueError, ImportError) as exc:
            failed[key] = type(exc).__name__
    receipt = {'schema': 'portfolio-tools/1', 'commits': commits, 'made': made, 'failed': failed}
    path = Path(output) / TOOLS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return receipt


def record_tools(output: Path, remote: str = 'https://github.com/') -> list[str]:
    """🧰 Clone each TOOL_SOURCES repository at its default branch and ``collect_tools``; one log line each (best effort)."""
    checkouts, commits, lines, cloned = {}, {}, [], {}
    with tempfile.TemporaryDirectory() as tmp:
        for key, (repository, _, _) in TOOL_SOURCES.items():
            try:
                if repository not in cloned:                      # one clone per repository (the lab has two tools)
                    checkout = Path(tmp) / repository.split('/')[1]
                    subprocess.run(['git', 'clone', '--quiet', '--depth', '1', remote + repository, str(checkout)], check=True,
                                   timeout=300)
                    cloned[repository] = checkout, _checkout_commit(checkout)
                checkouts[key], commits[key] = cloned[repository]
            except (OSError, subprocess.SubprocessError) as exc:
                lines.append(f'⏸ {key}: clone failed ({type(exc).__name__})')
        receipt = collect_tools(output, checkouts, commits)
    return lines + [f"✅ {key} @ {commits[key][:7]} → {TOOL_SOURCES[key][1]}/" if key in receipt['made'] else
                    f"⏸ {key}: {receipt['failed'][key]}" for key in checkouts]


def _checkout_commit(checkout: Path) -> str:
    return subprocess.run(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()


def stage_tools(output: Path, root: Path = ROOT) -> dict | None:
    """🧪 Build the tools whose repository is checked out under ``root/.test-deps/<name>`` (CI pins the commit) into the
    staged ``output``, so tests and previews see them as Pages does; None when there is none."""
    found = {key: root / CHECKOUTS / repository.split('/')[1] for key, (repository, _, _) in TOOL_SOURCES.items()}
    checkouts = {key: path for key, path in found.items() if (path / '.git').exists()}
    if not checkouts:
        return None
    return collect_tools(output, checkouts, {key: _checkout_commit(path) for key, path in checkouts.items()})


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
            pages[name] = _back_to_tools(_paused(ui, repository), name).encode('utf-8')
    return pages


def _paused(ui, repository: str, why: str = 'このビルドでは作っていない。') -> str:
    """⏸ What stands in for a tool this build did not make."""
    return ui.page_document({'schema': 'web-ui-page/1', 'title': f'🧰 {repository.split("/")[1]}', 'blocks': [
        {'type': 'text', 'text': f'⏸ この道具は、公開のたびに {repository} の最新のコミットから作り直す。{why}'},
        {'type': 'links', 'items': [{'label': '🐙 GitHub リポジトリ', 'href': f'https://github.com/{repository}'}]}]})


def tool_panels(ui, output: Path | None = None) -> dict[str, tuple[bytes, str]]:
    """🧰 The TOOL_SOURCES tools that are #panels of the screen (no page of their own): the document ``--record-tools`` built,
    taken out of the tree, else ⏸; ``{source: (document, repository)}`` for ``render_shell``."""
    path = Path(output) / TOOLS if output else None
    made = json.loads(path.read_text(encoding='utf-8'))['made'] if path and path.is_file() else []
    panels = {}
    for key, (repository, folder, entries) in TOOL_SOURCES.items():
        built = Path(output) / folder / 'index.html' if output else None
        if entries:
            continue
        if key in made and built.is_file():
            panels[f'{folder}/index.html'] = built.read_bytes(), repository
            built.unlink()
            if not any(built.parent.iterdir()):        # 🌡️ a one-page tool leaves no folder behind
                built.parent.rmdir()
        else:
            panels[f'{folder}/index.html'] = _paused(ui, repository).encode('utf-8'), repository
    return panels


def render_pages(ui, root: Path = ROOT) -> dict[str, bytes]:
    """Every hash-locked page: the demos and world pages, HTML import, map tools and the GIF workshop, keyed by published path."""
    map_tool = load_module('map_tool', 'scripts/map_tool.py')
    maps = {MAP_PINS_PAGE: map_tool.map_document(ui, map_tool.tokyo_points(_world().example_data('cities'))).encode()}
    pages = {**render_world(ui), **render_html_import(ui)}
    pages = {path: link_shared_sheets(ui, path, page) for path, page in pages.items()}
    return {**pages, **render_pswb_tools(ui), **maps, **render_gif_tool(ui), **render_chat_tool(ui)}   # 🧰 the rest are #panels (render_shell)


def link_shared_sheets(ui, path: str, page: bytes) -> bytes:
    """The shared sheet a page inlines (``STYLESHEET_BUNDLES``) as a link to its published copy, so every page reads one file."""
    for sheet, builder in STYLESHEET_BUNDLES.items():
        prefix = b'<style>' + getattr(ui, builder)().encode()
        head, end, body = page.partition(b'</head>')
        if prefix in head:
            href = os.path.relpath(ASSET_BASE + sheet, os.path.dirname(path)).replace(os.sep, '/')
            link = f'<link rel="stylesheet" href="{href}">'.encode()
            head = head.replace(prefix, link + b'<style>', 1).replace(link + b'<style></style>', link, 1)
            page = ui.stamp_page_size((head + end + body).decode('utf-8')).encode('utf-8')   # 📦 the page is smaller now
    return page


# ── 🧰 One screen: every tool the portfolio builds is a #panel of tools/index.html, under one header, one foot and one ⚙️ ──
SHELL_PAGE = 'tools/index.html'
PANEL_PAGES = (GIF_PAGE, MAP_PINS_PAGE, *PSWB_TOOLS, FLOW_PAGE, MAP_PAGE, CHAT_PAGE)   # where each panel's document is built from; never published
_LINK = re.compile(r'(?P<attr>\b(?:href|src)=)(?P<quote>["\'])(?P<url>[^"\']*)(?P=quote)')
_SHELL_JS = """(()=>{const panels=[...document.querySelectorAll('[data-tools-panel]')],names=panels.map(p=>p.id);let current='';
const mark=()=>{const door=document.querySelector('[data-door-select]'),mine=door&&[...door.options].find(o=>o.value.endsWith('#'+current));if(mine)door.value=mine.value};   // 🚪 shows where you are
const show=(panel,target)=>{const inert=panel.querySelector(':scope>template');if(inert)panel.replaceChildren(document.importNode(inert.content,true));  // 💤 a panel loads when first opened
 for(const p of panels)p.hidden=p!==panel;document.title=panel.dataset.title;
 if(target)(document.getElementById(target)||panel).scrollIntoView();else if(current&&current!==panel.id)scrollTo(0,0);current=panel.id;mark()};
const route=()=>{const name=decodeURIComponent(location.hash.slice(1)).split('?')[0];
 if(names.includes(name))return show(document.getElementById(name));
 const owner=name&&panels.find(p=>p.querySelector(':scope>template')?.content.getElementById(name)||p.contains(document.getElementById(name)));   // #records: a section of a panel
 if(owner)return show(owner,name);if(!current)show(document.getElementById('home'))};
addEventListener('hashchange',route);addEventListener('pageshow',()=>setTimeout(mark));
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',route);else route()})();"""


def _rebase_links(markup: str, source: str, name: str) -> str:
    """Every relative ``href`` / ``src`` of ``markup`` (written for ``source``) as seen from SHELL_PAGE; a link to the page
    itself becomes ``#name``. Script bodies are left as they are (only a ``<script src>`` moves)."""
    def move(match):
        parts = urlsplit(match['url'])
        if not parts.path or parts.scheme or parts.netloc or parts.path.startswith('/'):
            return match[0]
        at = posixpath.normpath(posixpath.join(posixpath.dirname(source), parts.path))
        if at in (posixpath.dirname(source), source):
            url = '#' + (parts.fragment or name)
        else:
            url = urlunsplit(('', '', './' + posixpath.relpath(at, posixpath.dirname(SHELL_PAGE)) + ('/' if parts.path.endswith('/') else ''),
                              parts.query, parts.fragment))
        return match['attr'] + match['quote'] + url + match['quote']
    pieces = re.split(r'(<script\b[^>]*>.*?</script>)', markup, flags=re.S)
    return ''.join(_LINK.sub(move, piece) if i % 2 == 0 else re.sub(r'<script\b[^>]*>', lambda tag: _LINK.sub(move, tag[0]), piece, count=1)
                   for i, piece in enumerate(pieces))


def _panel(ui, source: str, page: str) -> tuple[str, str]:
    """(title, markup) of a tool's document as a #panel: its <head>'s own styles and scripts (the shared sheet, the name, the icons
    and the viewport are the screen's), then its <body>, links rebased (``_rebase_links``)."""
    page = re.sub(r'^\s*<!doctype html>\s*|<html\b[^>]*>|</html>\s*$', '', page, flags=re.I)   # a page may leave <head> / <body> implied
    head = re.search(r'<head>(.*?)</head>', page, re.S)
    body = re.search(r'<body\b([^>]*)>(.*)</body>', page, re.S)
    title = re.search(r'<title>(.*?)</title>', page, re.S)
    title = html.unescape(title[1]).strip() if title else source.split('/')[1]
    classes = re.search(r'\bclass="([^"]*)"', body[1]) if body else None
    head, body = (head[1] if head else ''), (body[2] if body else page[head.end():] if head else page)
    head, body = (re.sub(r'<meta\b[^>]*>|<title>.*?</title>|<link rel="(?:icon|apple-touch-icon|manifest)"[^>]*>', '', part, flags=re.S)
                  for part in (head, body))
    for builder in STYLESHEET_BUNDLES.values():
        head = head.replace('<style>' + getattr(ui, builder)(), '<style>')
    return title, _rebase_links(head.replace('<style></style>', '') + body, source, source.split('/')[1]), classes[1] if classes else ''


def render_shell(ui, docs: dict[str, bytes], tools: dict[str, tuple[bytes, str]] | None = None) -> bytes:
    """🧰 tools/index.html: the screen every tool of PANEL_PAGES is a panel of (``#gif``, ``#maps``, …; 🏠 ``#home`` lists them).
    The header, the side and the foot are the site's (``add_site_chrome``) once; a panel stays an inert ``<template>`` until it is
    first opened (its styles and scripts load then), and ``#section`` opens the panel that holds it."""
    places = {place['href']: place['label'] for place in tools_places('../')}
    names = [source.split('/')[1] for source in (*docs, *(tools or {}))]
    index, panels, owners = [], [], {name: name for name in ('home', *names, 'door', 'door-select', 'tools-chrome')}   # 🆔 one owner per id
    for source, data in (*docs.items(), *((source, (data, repository)) for source, (data, repository) in (tools or {}).items())):
        name = source.split('/')[1]
        title, markup, classes = _panel(ui, source, (data[0] if isinstance(data, tuple) else data).decode('utf-8'))
        ids = set(re.findall(r'\bid="([^"]+)"', re.sub(r'<script\b[^>]*>.*?</script>', '', markup, flags=re.S)))
        clash = sorted(i for i in ids if owners.get(i, name) != name)
        if clash and not isinstance(data, tuple):
            raise ValueError(f'🆔 the {name} panel shares ids with another part of the screen: {clash}')
        if clash:                                                          # 🧰 a tool of another repository: ⏸ rather than a broken screen
            title, markup, classes = _panel(ui, source, _paused(ui, data[1], f'id がほかの道具とぶつかる（{", ".join(clash)}）。'))
            ids = set()
        owners.update(dict.fromkeys(ids, name))
        index.append(f'<li><a href="#{name}">{html.escape(places.get(f"../tools/#{name}", title), quote=False)}</a></li>')
        css = f' class="{html.escape(classes)}"' if classes else ''      # the page's <body> class (ui-elements) holds for its panel
        panels.append(f'<section id="{name}"{css} data-tools-panel data-title="{html.escape(title)}" hidden><template>{markup}</template></section>')
    home = (f'<section id="home" data-tools-panel data-title="🧰 Tools"><main class="ui-page"><h1>🧰 Tools</h1>'
            f'<ul class="ui-tools-index">{"".join(index)}</ul></main></section>')
    page = ui.render_document(title='🧰 Tools', theme='modern', css=ui.bundled_css() + '.ui-tools-index{display:grid;gap:8px;padding:0;list-style:none}',
                              trusted_html=home + ''.join(panels) + f'<script>{_SHELL_JS}</script>')
    page = page.replace('<html lang="en">', '<html lang="ja">', 1).replace(
        '<head>', '<head><meta name="description" content="myon-bioinformatics の道具を 1 つの画面で。🚪 で道具を選び、🏠 で一覧へ。">', 1)   # 📟 the board reads it
    cities = {'🗼': {'label': 'パラレル都市', 'label_en': 'Parallel cities', 'href': './demos/world.html#tokyo'}}   # 🗺️ the map's neighbour
    page = ui.add_back_nav(page, [{'label': '← 🧰 Tools', 'href': '../index.html#tools'}], test_id='portfolio-back')   # 🏠 the home panel's first line
    page = add_site_chrome(page, SHELL_PAGE, cities)
    return link_shared_sheets(ui, SHELL_PAGE, add_home_label(page, '🧰 道具', icons_from='../').encode('utf-8'))


def generate(root: Path = ROOT, ui=None, commit: str | None = None) -> dict[str, bytes]:
    lock = json.loads((root / 'web-ui-assets.lock.json').read_text(encoding='utf-8'))
    if lock['schema'] != 'web-ui-generated/2':
        raise ValueError('unsupported generated asset lock')
    commit = commit or installed_commit()
    verify_pin(commit, root)
    if commit != lock['commit']:
        raise ValueError(f'generator provenance mismatch: installed {commit[:8]}, lock {lock["commit"][:8]}')
    if set(lock['outputs']) != {HTML_IMPORT_MODULE, CHAT_SOURCES, *WORLD_ASSETS, *DRAGON_ASSETS, *(ASSET_BASE + name for name in (*ASSETS, *STYLESHEET_BUNDLES))}:
        raise ValueError('generated output paths differ from public URL contract')
    expected = {HTML_IMPORT_PAGE, GIF_PAGE, CHAT_PAGE, MAP_PINS_PAGE, WORLD_PAGE, *PSWB_TOOLS}
    if set(lock.get('pages', {})) != expected:
        raise ValueError('generated page paths differ from the tool and world lists')
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
    payload[SHELL_PAGE] = render_shell(ui, {path: payload.pop(path) for path in PANEL_PAGES}, tool_panels(ui, output))
    for name, data in payload.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    # Publish the active asset provenance beside the generated files.
    (output / ASSET_BASE / 'generated.lock.json').write_bytes(
        (root / 'web-ui-assets.lock.json').read_bytes())


def copy_source(output: Path, root: Path = ROOT) -> None:
    """Copy the static files served verbatim. Generated and recorded assets can share this output tree."""
    root = root.resolve()
    validate_output(output, root)
    sources = [root / name for name in PUBLIC_SOURCE_FILES]
    for source in sources:
        if not source.is_file() or source.resolve() != source:
            raise ValueError(f'expected a regular public file: {source.relative_to(root)}')

    for source in sources:
        target = output / source.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def stage(output: Path, root: Path = ROOT) -> None:
    """Stage the public static files and generated files for tests and local previews."""
    validate_output(output, root)
    generate(root)  # Fail closed before copying anything.
    copy_source(output, root)
    stage_tools(output, root)   # 🧰 first: the screen (build) takes in the tools that are its panels
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='write the generated assets under this directory')
    parser.add_argument('--copy-source', type=Path, metavar='DIR', help='copy the static files served verbatim by Pages')
    parser.add_argument('--stage', type=Path, help='write the whole site (source tree plus generated assets) under this directory')
    parser.add_argument('--refresh-lock', action='store_true',
                        help='rewrite web-ui-assets.lock.json from the installed generator')
    parser.add_argument('--record-samples', type=Path, metavar='DIR',
                        help="🎥 record a moving sample of every repository's Pages and of every 🧰 Tools card's page under DIR/media/pages/ (Chromium; best effort)")
    parser.add_argument('--record-flow', type=Path, metavar='DIR',
                        help='🌊 run FFSS and DRAgoWing (their default branches) and put the flow lab media under DIR/media/flow/')
    parser.add_argument('--record-tools', type=Path, metavar='DIR',
                        help='🧰 build the tools of TOOL_SOURCES (Ironmate, mcp-toolcall-lab, DRAgoWing; their default branches) under DIR/tools/')
    parser.add_argument('--record-map', type=Path, metavar='DIR',
                        help="🧠 read every repository's vendor.lock.json (and Aoi's subtrees) and draw the map under DIR/media/map/")
    parser.add_argument('--record-chat', type=Path, metavar='DIR',
                        help="💬 index every repository's JSON / JSONL, mcp-toolcall-lab's tools and TalkCompress's compressor under DIR/media/chat/")
    args = parser.parse_args(argv)
    for target in (args.output, args.stage, args.copy_source):
        if target:
            validate_output(target)
    if args.copy_source:
        copy_source(args.copy_source)
    if args.record_samples:
        # 🎥 this portfolio too: its card shows the front page as Pages serves it now (the deploy before this one), and so do the 🧰 Tools
        tools = tools_samples()
        print('\n'.join(record_samples(args.record_samples, {**pages_urls(), **{name: url for name, (url, _) in tools.items()}},
                                       captions={name: title for name, (_, title) in tools.items()},
                                       stand_ins={name: sample_stand_in(title) for name, (_, title) in tools.items()})))
    if args.record_map:
        print('\n'.join(record_map(args.record_map)))
    if args.record_chat:
        print('\n'.join(record_chat(args.record_chat)))
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
    if not (args.refresh_lock or args.output or args.stage or args.copy_source or args.record_samples or args.record_flow or args.record_map
            or args.record_tools or args.record_chat):
        parser.error('give --output DIR, --stage DIR, --refresh-lock and/or a --record-… DIR')


if __name__ == '__main__':
    raise SystemExit(main())
