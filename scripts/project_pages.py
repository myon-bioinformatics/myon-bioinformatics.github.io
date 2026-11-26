"""Generate the shared browser assets from the pinned PySaiyanWeBoo dependency.

The generator is the ``pysaiyanweboo`` module from the ``pages`` dependency group (a git dependency
pinned by commit in ``pyproject.toml``; ``uv run --locked --only-group pages`` installs it). ``web-ui-assets.lock.json`` records that commit and the
SHA-256 of every output, so a build fails closed when the installed module is not the
pinned commit or when its output drifted from the lock. The generated files are not kept in git: ``--output DIR``
writes them (Pages overlays them on its build), ``--stage DIR`` writes the whole site for tests and local previews,
and ``--refresh-lock`` rewrites the lock after the pin moves.

The 🧰 Tools cards (scripts/front_page.py ``PORTAL``) list the practical pages, each one working on what the visitor brings:
the 💬 cross-repo chat (scripts/chat.py, run by Pyodide in the page; ``--record-chat`` indexes the other repositories at deploy
time) and PySaiyanWeBoo's own tool documents (``PSWB_TOOLS``: 🧾 the JUnit reader, 🤝 the MCP connection test), published with
the portfolio's way back, shortcut label and icons. The 🌍 world pages (scripts/world.py: the travel world, 🏫 the school,
🗼 the parallel cities, 🎬 the camera; tools/demos/) are built the same way for PySaiyanWeBoo's 🎞 GIF demo and are not among
the cards. Each repository's own Pages carry its 🧩 機能一覧 / 🔬 検証ガイド / 🎞 GIF デモ; nothing here copies them.

``tools/html-import/index.html`` (the HTML import tool page) is built here too and hash-locked with the other pages.
Every generated or imported tool page gets the same way back, chrome and shortcut label: ``add_back_nav()`` (the way back and
🧰 the chrome of scripts/world.py: the board with the clock, 🏠 ⭐ ⚙️ and each page's own ☰ ⋯, built by ``tools_chrome()``, and
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

ROOT = Path(__file__).resolve().parents[1]
ASSET_BASE = 'tools/vendor/web-ui/'
ASSETS = ('css/base.css', 'css/components.css', 'css/themes/modern.css',
          'css/tokens.css', 'js/navigation.js', 'js/ui.js', 'js/controls.js',
          'js/coordinates.js')
STYLESHEET_BUNDLES = {'css/bundle.css': 'bundled_css', 'css/core.css': 'core_css'}
DISTRIBUTION = 'pysaiyanweboo'
DEMO_BASE = 'tools/demos/'
HTML_IMPORT_PAGE = 'tools/html-import/index.html'
HTML_IMPORT_MODULE = 'tools/html-import/extract.mjs'
MAP_PAGES = {'tools/maps/index.html', 'tools/maps/tokyo.html'}

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
    'tools/mcp-protocol/index.html': (lambda ui: ui.mcp_document(), '🤝 MCP接続'),
}
# 🌍 name -> (how it is built, shortcut label, title, summary), for PySaiyanWeBoo's 🎞 GIF demo; not in the 🧰 Tools cards: they show, they are not tools
WORLD_PAGES = {
    'world': (lambda ui: world_page('overworld'), '🌍 ワールド', 'World',
              '🚪 で土地をわたる旅のワールド：絵文字のキャラで歩き、時刻・お気に入り・地図・言語を切り替える'),
    'school': (lambda ui: world_page('school'), '🏫 スクール', 'School',
               '教室を歩く：絵文字を選び、タップ・矢印キー・パッドで机のあいだを移動（机・黒板・棚には入らない）'),
    'cities': (lambda ui: world_page('cities'), '🗼 パラレル', 'Parallel cities',
               'パラレル東京・リバースロンドン・フェイクパリ：緯度・経度から、駅から駅へ歩く'),
    'world-shots': (lambda ui: world_page('world'), '🎬 カメラ', 'World camera',
                    'ページ遷移なしの1ページ：スクロールで場面、ドラッグ・ホイール・ピンチで地図を動かしスポットを開く'),
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


def tools_places(prefix: str = '../../') -> list[dict]:
    """🧰 Every link of the 🧰 Tools cards (front_page.py ``PORTAL``, so a new card is a new row) as ``{'id', 'label', 'href'}``, for
    a page ``prefix`` below the site root: the doors of 🚪 Door-to-Door. ``text`` is the card's own description (the board shows it).

    Every label is ``emoji words``, one emoji per page (the door knows a page by its emoji): the card's own, or the one named here
    for a link that has none or shares its card's."""
    site, places = 'https://myon-bioinformatics.github.io/tools/', {}
    marks = {'html-import': '📄', 'maps': '🗺️', 'maps-tokyo': '🗼', 'browser-tools': '🎨', 'slide-studio': '📽️', 'mcp-execution': '🧪', 'mcp-protocol': '🤝'}
    for card in load_module('front_page', 'scripts/front_page.py').PORTAL:
        mark, _, title = card['title'].partition(' ')
        if not title or any(c.isalnum() for c in mark):                  # a title without an emoji: all of it is words
            mark, title = '🚪', card['title']
        for label, href in card['links']:
            href = prefix + href[2:] if href.startswith('./') else prefix + 'tools/' + href[len(site):] if href.startswith(site) else href
            name = re.sub(r'[^a-z0-9]+', '-', href.partition('tools/')[2].removesuffix('.html').lower()).strip('-') or card['id']
            words = title if len(card['links']) == 1 else label.removesuffix(' →').removeprefix('Open ')   # several links: each link's own words
            places.setdefault(href, {'id': name, 'href': href, 'label': f'{marks.get(name, mark)} {words}', 'text': card['text']})
    return list(places.values())


def tools_chrome(prefix: str = '../../', tools: dict | None = None, description: str = '', *, title: str = 'TOOLS', home: bool = True) -> dict:
    """🧰 The chrome every page of the site carries (scripts/world.py ``chrome_validate``), for a page ``prefix`` below the site root:
    the board (``title``, the clock, then ``description`` — what this page is, a sentence per item — and the cards' titles), 🏠 back
    to the cards (``home=False``: the front page itself) and ``tools``, the emoji this page adds (``{'🗼': {'label': …, 'href': …}}``).
    ☰ is each page's own (itself and its sections, listed in the page); the tools themselves are 🚪 Door-to-Door's rows (``tools_places``)."""
    cards = load_module('front_page', 'scripts/front_page.py').PORTAL
    about = [{'text': part if len(part) <= 120 else part[:119] + '…'}
             for part in (p.strip() for p in re.split(r'(?<=[。！？])|(?<=[.!?])\s+', html.unescape(description))) if part][:3]
    return {'id': 'tools', **({'home': prefix + 'index.html#tools'} if home else {}), 'tools': tools or {},
            'board': {'title': title, 'items': (about + [{'text': card['title']} for card in cards])[:12]}}


def tools_door(ui, prefix: str = '../../', here: str | None = None, title: str = '', tokens: str = '') -> tuple[str, str, str]:
    """🚪 PySaiyanWeBoo's Door-to-Door (``door_html``, door.css, door.js) for a tool page, as ``(html, css, js)``: 🏠 the cards, then
    every tool (``tools_places``); ``here`` (this page's href) is the door you came in by, and a page that is no tool is added as 📌 ``title``.

    The part is PySaiyanWeBoo's whole panel; the sheet here shows its pull-down alone, in a 56px row that stays at the window's foot
    (the label reads 🚪, the rest of the panel is not drawn), followed by the site's own line: 🐦 the X account and 📦 this page's
    size (``stamp_size`` writes it once the page is whole). The one line after door.js puts the pull-down back on this page when the
    browser's own way back restores it."""
    pages = [{'emoji': '🏠', 'label': 'Tools', 'href': prefix + 'index.html#tools'},
             *({'emoji': mark, 'label': words, 'href': place['href']} for place in tools_places(prefix) for mark, _, words in [place['label'].partition(' ')])]
    if here and here not in {page['href'] for page in pages}:
        pages.append({'emoji': '📌', 'label': title[:40] or here, 'href': here})
    door = {'schema': ui.DOOR_SCHEMA, 'k': 0, 'pages': pages, **({'current': here} if here else {})}
    css = ((f'.ui-door-foot{{{tokens}}}' if tokens else '') + ui.css_source('door.css') +
           '.ui-door-foot{position:sticky;bottom:0;z-index:32;margin:0;padding:0;border-top:1px solid var(--ui-border);background:var(--ui-panel);'
           'color:var(--ui-fg);font-family:var(--ui-font);font-size:1rem;line-height:1.5}.ui-door-foot *{box-sizing:border-box}'
           '.ui-door-foot{display:flex;align-items:center}.ui-door-foot .ui-door{flex:1;min-width:0}'
           '.ui-foot-info{display:flex;align-items:center;gap:8px;margin:0;padding:0 8px;font-size:.75rem;white-space:nowrap}'
           '.ui-foot-info a{display:inline-flex;align-items:center;justify-content:center;width:40px;height:40px;font-size:1.25rem;text-decoration:none}'
           '.ui-door-foot .ui-door{display:flex;align-items:center;gap:8px;min-height:56px;margin:0;padding:8px;border:0;background:none}'
           '.ui-door-foot .ui-door>:not(label[for=door-select],.ui-door-row),.ui-door-foot [data-door-draw]{display:none}'
           '.ui-door-foot label[for=door-select]{margin:0;font-size:0}.ui-door-foot label[for=door-select]::before{content:"🚪";font-size:1.25rem}'
           '.ui-door-foot .ui-door-row{flex:1;min-width:0;flex-wrap:nowrap}'
           '.ui-door-foot .ui-door-row select{flex:1;min-width:0;max-width:384px;min-height:40px;margin:0;padding:0 8px;font:inherit;color:var(--ui-fg);'
           'background:var(--ui-bg);border:1px solid var(--ui-border);border-radius:var(--ui-radius)}')
    js = (ui.js_source('door.js') + 'addEventListener("pageshow",()=>{for(const s of document.querySelectorAll("[data-door-select]"))'
          's.selectedIndex=Math.max(0,[...s.options].findIndex(o=>o.disabled))});\n')
    info = (f'<p class="ui-foot-info"><a href="{X_URL}" target="_blank" rel="noopener noreferrer" title="X (Twitter) @{X_URL.rpartition("/")[2]}" '
            f'aria-label="X (Twitter) @{X_URL.rpartition("/")[2]}">🐦</a><span class="ui-foot-size" title="このページの HTML の大きさ">📦</span></p>')
    return '<div class="ui-door-foot">' + ui.door_html(door) + info + '</div>', css, js


X_URL = 'https://twitter.com/myonitbusiness'
def stamp_size(page: str) -> str:
    """📦 The foot's size reads this page's own HTML, in KB (what the browser downloads first; shared sheets, scripts and media are apart).
    Call it once more after a step that changes the page's size: it rewrites the number."""
    return re.sub(r'(<span class="ui-foot-size"[^>]*>)[^<]*(</span>)', lambda m: f'{m[1]}📦 {len(page.encode("utf-8")) / 1024:.0f} KB{m[2]}', page)


def add_site_chrome(page: str, path: str | None = None, tools: dict | None = None, description: str | None = None, *,
                    title: str = 'TOOLS', home: bool = True) -> str:
    """🧰 The parts every page of the site shares, for the page published at ``path`` (``tools/gif/index.html``; left out: two folders
    below the root, and no door marked as this page): the header (``tools_chrome``: the board with ``description``, 🫧 the round face
    that follows the pointer, 🏠 ⭐ ⚙️), the side
    (☰ ⋯) and the foot (``tools_door``: 🚪 every tool as a pull-down, 🐦 X, 📦 the page's size). ``description`` left out is the text
    of the 🧰 Tools card that leads here, else the page's own ``<meta name="description">``.

    🎨 Every page is published in one look: the shared sheet's ``modern`` theme, the front page's default. A page built with
    another palette on its ``<body>`` (Ironmate's studios: green; the MCP lab: terminal or github-like) is switched to it, and the
    chrome then takes the page's own colours; a page with no ``data-ui-theme`` keeps it and gets the chrome's colours with the chrome.
    The way back spans a grid ``<main>``'s whole first row, so it never takes the place of a column (Ironmate's three-column studio).
    A page whose CSP lists its scripts or styles without ``'unsafe-inline'`` (HTML import, Ironmate's studios) gets
    the modules and sheets of the chrome and the door listed too: their hashes, nothing wider."""
    import pysaiyanweboo as ui
    prefix = ('../' * path.count('/') or './') if path else '../../'
    here = prefix + re.sub(r'index\.html$', '', path) if path else None
    if description is None:
        meta = re.search(r'<meta name="description" content="([^"]*)"', page)
        description = next((place['text'] for place in tools_places(prefix) if place['href'] == here), meta[1] if meta else '')
    world = _world()
    body = re.search(r'<body\b[^>]*>', page)
    if body and 'data-ui-theme="' in body[0]:
        page = page[:body.start()] + re.sub(r'data-ui-theme="[^"]*"', 'data-ui-theme="modern"', body[0], count=1) + page[body.end():]
    tokens = '' if 'data-ui-theme="modern"' in page else re.search(r':root\{([^}]*)\}', ui.css_source('tokens.css'))[1]
    chrome, heading = tools_chrome(prefix, tools, description, title=title, home=home), re.search(r'<title>(.*?)</title>', page, re.S)
    door, door_css, door_js = tools_door(ui, prefix, here if path and '/' in path else None, html.unescape(heading[1]).strip() if heading else '', tokens)
    face = ui.component_parts('gaze-avatar')      # 🫧 PySaiyanWeBoo's round face that follows the pointer: in the header, after the board
    head = world.chrome_html(chrome).replace('<nav class="ui-world-tools">', face['html'] + '<nav class="ui-world-tools">', 1)
    for part, css, js in (({}, face['css'] + '.ui-chrome .ui-gaze{flex:none;margin:0 4px}main>nav.ui-back{grid-column:1/-1}', face['js']),
                          ({'top': head}, world.chrome_css(tokens), world.SHELL_JS + 'bindChrome();\n'),
                          ({'bottom': door}, door_css, door_js)):
        page = world.add_part(page, css=css, js=js, **part)
        for directive, block in (('script-src', js), ('style-src', css)):
            listed = re.search(r'Content-Security-Policy"\s+content="[^"]*?\b' + directive + r'([^;"]*)', page.partition('</head>')[0])
            if listed and "'unsafe-inline'" not in listed[1]:
                page = page[:listed.end()] + ' ' + ui.module_csp_hash(block) + page[listed.end():]
    return stamp_size(page)


def add_back_nav(page: str, path: str | None = None, tools: dict | None = None) -> str:
    """🏠 PySaiyanWeBoo's way back (``back_nav_html``) to the 🧰 Tools cards, right after <main> (else <body>), then the site's
    shared header, side and foot (``add_site_chrome``); a page that already has them keeps them. A 🌍 world page has its own header
    and side (the same parts), so it gets the way back only, and so does a fragment without <head> and <body>."""
    import pysaiyanweboo as ui
    prefix = '../' * path.count('/') if path else '../../'
    page = ui.add_back_nav(page, [{'label': '← 🧰 Tools', 'href': prefix + 'index.html#tools'}], test_id='portfolio-back')
    if 'data-ui-world="' in page or '<div class="ui-chrome ' in page or '</head>' not in page or '<body' not in page:
        return page                               # a world, a page that has it, or a fragment with no <head> and <body> to carry it
    return add_site_chrome(page, path, tools)


def add_home_label(page: str, label: str, *, icons_from: str | None = None) -> str:
    """📱 PySaiyanWeBoo's ``home_label``: the home-screen shortcut is named ``label``; ``icons_from`` (the way back to the site
    root, ``'../../'``) also gives the page the portfolio's tab icon and home-screen icon. Idempotent."""
    import pysaiyanweboo as ui
    icons = {} if icons_from is None else {'icon': f'{icons_from}assets/brand/favicon-32x32.png',
                                           'touch_icon': f'{icons_from}assets/brand/myon-profile-icon.png'}
    return ui.home_label(page, label, **icons)


def render_front(root: Path = ROOT, samples=frozenset()) -> dict[str, bytes]:
    """The portfolio's own front page (scripts/front_page.py), built from profile.json, api/repos.json and projects.json, with the
    site's shared header, side and foot (``add_site_chrome``: the board reads the page's description, ☰ lists its sections).

    It is not in the lock: api/repos.json is refreshed by a workflow, and the page must follow it without a lock refresh."""
    front = load_module('front_page', 'scripts/front_page.py')
    return {'index.html': add_site_chrome(front.document(root, samples=samples), 'index.html', front.LINKS, title='MYON', home=False).encode('utf-8')}


def render_demos(ui) -> dict[str, bytes]:
    """Every 🌍 world page (``WORLD_PAGES``), keyed by published path (two levels below the site root)."""
    return {DEMO_BASE + name + '.html': add_home_label(add_back_nav(build(ui), DEMO_BASE + name + '.html'), label, icons_from='../../').encode('utf-8')
            for name, (build, label, _, _) in WORLD_PAGES.items()}


def render_pswb_tools(ui) -> dict[str, bytes]:
    """🧾 🤝 PySaiyanWeBoo's own tool documents (``PSWB_TOOLS``), each with the way back, the chrome and the home-screen name."""
    return {path: add_home_label(add_back_nav(build(ui), path), label, icons_from='../../').encode('utf-8')
            for path, (build, label) in PSWB_TOOLS.items()}


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
    page = ui.gif_maker_document(filename='gif-kobo.gif', css=ui.bundled_css())   # the shared sheet (render_pages links it as css/bundle.css)
    return {GIF_PAGE: add_home_label(add_back_nav(page, GIF_PAGE), '🎞 GIF工房', icons_from='../../').encode('utf-8')}


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


def render_flow(ui, output: Path | None = None) -> dict[str, bytes]:
    """The 🌊 lab page from what this build recorded under ``output/media/flow/`` (not in the lock, like the front page:
    the media change with the two repositories): every FFSS scene in FFSS's own order with the DRAgoWing figures that
    belong to it (FLOW_FIGURES), then every other figure, so nothing that was made is left out."""
    path = Path(output) / FLOW / 'receipt.json' if output else None
    receipt = json.loads(path.read_text(encoding='utf-8')) if path and path.is_file() else {}
    commits, demos, figures = receipt.get('commits', {}), receipt.get('demos', []), receipt.get('figures', [])
    link = lambda key: (f"https://github.com/{FLOW_REPOSITORIES[key]}/tree/{commits[key]}"
                        if key in commits else f"https://github.com/{FLOW_REPOSITORIES[key]}")
    named = {figure.split('_', 1)[1]: figure for figure in figures}
    svg = lambda figure: {'type': 'image', 'src': f'../../{FLOW}{figure}.svg', 'alt': f'📊 DRAgoWing {figure}'}
    blocks = [{'type': 'text', 'text': 'FFSS の全場面を 🌊 動く像（流れと遅れ）で、その記録から描ける DRAgoWing の全図を 📊 静止図（行き先の内訳）で。'
                                       'どちらも公開のたびに、そのとき最新のコミットで作り直す。'},
              {'type': 'kv', 'rows': [['🌊', f"FFSS {commits.get('ffss', '—')[:7]} · 🎞 {len(demos)} 場面"],
                                      ['📊', f"DRAgoWing {commits.get('dragowing', '—')[:7]} · {len(figures)} 図"]]}]
    if not demos and not figures:
        blocks.append({'type': 'text', 'text': '⏸ このビルドでは記録していない'})
    used = set()
    for demo in demos:
        inner = [{'type': 'image', 'src': f"../../{FLOW}{demo['id']}.gif", 'alt': f"🌊 FFSS {demo['id']}: {demo['scene']}"}]
        for name in FLOW_FIGURES.get(demo['scene'], ()):
            if name in named:
                inner.append(svg(named[name]))
                used.add(named[name])
        fluid = '' if demo['fluid'] == 'water' else f" · {demo['fluid']}"
        blocks.append({'type': 'section', 'title': f"{demo['icon']} {demo['id']} {demo['scene']}{fluid}", 'blocks': inner})
    rest = [figure for figure in figures if figure not in used]
    if rest:
        blocks.append({'type': 'section', 'title': '📊 ほかの図', 'blocks': [svg(figure) for figure in rest]})
    blocks.append({'type': 'links', 'items': [{'label': '🌊 FFSS', 'href': link('ffss')}, {'label': '📊 DRAgoWing', 'href': link('dragowing')}]})
    page = ui.page_document({'schema': 'web-ui-page/1', 'title': '🌊 流れの実験室', 'blocks': blocks}).replace(
        '</head>', '<style>.ui-page img{max-width:100%;height:auto}</style></head>', 1)       # 📱 the GIF and SVG fit a phone
    page = page.replace('<img src="../../media/flow/', '<img loading="lazy" src="../../media/flow/')   # 🐢 40-odd GIFs: load on scroll
    return {FLOW_PAGE: add_home_label(add_back_nav(page, FLOW_PAGE), '🌊 流れ実験', icons_from='../../').encode('utf-8')}   # fits an 80 px tile


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
    return {MAP_PAGE: add_home_label(add_back_nav(page, MAP_PAGE), '🧠 地図', icons_from='../../').encode('utf-8')}


# ── 💬 横断チャット: scripts/chat.py in Pyodide with the pinned markdown.py · ascii_artist.py · cli_args.py (pages group);
# what it knows of the other repositories is recorded at deploy time (media/chat/, not kept in git) ──
CHAT = 'media/chat/'
_CHAT_SLOT = '💬chat-slot'
CHAT_CSS = '.ui-step [data-chat-say]{margin-top:8px}'    # 📇 the index's "💬 送る"; the chat itself is PySaiyanWeBoo's (chat.css)
# 💬 the page's part of the chat: the bubbles, Enter, chips and 😀 reactions are PySaiyanWeBoo's chat component (chat.js, webUiChat);
# here are only the bot (chat.py in Pyodide), 🤖 /ask (wllama) and the index's buttons
CHAT_JS = r"""const $ = (s) => document.querySelector(s);
const cfg = JSON.parse($("#chat-config").textContent);
const [chat] = webUiChat.bindChat(document);
let bot = null, llm = null;
async function ask(text, reply) {                      // 🤖 /ask: llama.cpp in WebAssembly (wllama), the model loaded once
  if (!llm) {
    reply.text("⏳ 🤖 llama.cpp…");
    const {Wllama} = await import(cfg.runtime.wllama + "index.js");
    llm = new Wllama({default: cfg.runtime.wllama + "wasm/wllama.wasm"});
    await llm.loadModelFromUrl(cfg.runtime.model, {n_ctx: 2048, progressCallback: ({loaded, total}) => {
      reply.text(`⏳ 🤖 ${total ? Math.round(loaded / total * 100) : 0}% · ${Math.round(loaded / 2 ** 20)} / ${Math.round(total / 2 ** 20)} MB`);
    }});
  }
  let output = "", tokens = 0;
  const started = performance.now();
  await llm.createChatCompletion({messages: JSON.parse(bot.ask_messages(text)), max_tokens: 256, temperature: 0.3, stream: true,
    chat_template_kwargs: {enable_thinking: false}, onData: (chunk) => {
      output += chunk.choices?.[0]?.delta?.content ?? "";
      tokens += 1;
      reply.text(output);
    }});
  return bot.ask_html.callKwargs(output, tokens, (performance.now() - started) / 1000,
                                 {threads: llm.isMultithread() ? navigator.hardwareConcurrency : 1, webgpu: llm.isSupportWebGPU()});
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
  for (const [name, text] of Object.entries(JSON.parse($("#chat-sources").textContent))) py.FS.writeFile("/chat/" + name, text);
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
    parts = ui.component_parts('chat', chat_id='chat', placeholder='/help · /flow a > b · onto', ready=False,     # 💬 PySaiyanWeBoo's chat
                               chips=[(f'{icon} /{name}', example) for name, (icon, _, _, (example, *_)) in chat.COMMANDS.items()],
                               status='⏳ 🐍 Python（Pyodide）を読み込み中…')
    body = (parts['html'] + '<noscript><p>⏸ このチャットは JavaScript と Pyodide で動く。📇 索引のコマンドは scripts/chat.py でも試せる。</p></noscript>')
    data = lambda value: json.dumps(value, ensure_ascii=False).replace('<', '\\u003c')
    config = {'runtime': chat.RUNTIME, 'index': f'../../{CHAT}index.json', 'base': f'../../{CHAT}'}
    body += (f'<script type="application/json" id="chat-config">{data(config)}</script>'
             f'<script type="application/json" id="chat-sources">{data(chat_sources())}</script>'
             + ui.module_script(parts['js']) + ui.module_script(CHAT_JS))
    slot = f'<p>{_CHAT_SLOT}</p>'
    if page.count(slot) != 1:
        raise ValueError('chat page has no single slot')
    return page.replace(slot, body, 1).replace('</head>', f'<style>{parts["css"]}{CHAT_CSS}</style></head>', 1)


CHAT_PAGE = 'tools/chat/index.html'   # 💬 a tool of its own (a 🧰 Tools card), not one of the 🤖 stubs
def render_chat_tool(ui) -> dict[str, bytes]:
    """💬 横断チャット: ``chat_document`` with the way back and the home-screen name."""
    return {CHAT_PAGE: add_home_label(add_back_nav(chat_document(ui), CHAT_PAGE), '💬 チャット', icons_from='../../').encode('utf-8')}


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
                'dragowing': ('myon-bioinformatics/DRAgoWing', 'tools/heatmap', ('',))}
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
                    page.write_text(_back_to_tools(page.read_text(encoding='utf-8'), f'{folder}/{entry}index.html'), encoding='utf-8')
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
            page = ui.page_document({'schema': 'web-ui-page/1', 'title': f'🧰 {repository.split("/")[1]}', 'blocks': [
                {'type': 'text', 'text': f'⏸ この道具は、公開のたびに {repository} の最新のコミットから作り直す。このビルドでは作っていない。'},
                {'type': 'links', 'items': [{'label': '🐙 GitHub リポジトリ', 'href': f'https://github.com/{repository}'}]}]})
            pages[name] = _back_to_tools(page, name).encode('utf-8')
    return pages


def render_pages(ui, root: Path = ROOT) -> dict[str, bytes]:
    """Every hash-locked page: the demos and world pages, HTML import, map tools and the GIF workshop, keyed by published path."""
    cities = {'🗼': {'label': 'パラレル都市', 'label_en': 'Parallel cities', 'links': [
        {'label': '🗼 パラレル東京', 'href': './tokyo.html'}, {'label': '🌍 東京・ロンドン・パリ', 'href': '../demos/cities.html'}]}}
    maps = {path: add_home_label(add_back_nav(document, path, cities), '地図・ピン', icons_from='../../').encode('utf-8')
            for path, document in load_module('map_tool', 'scripts/map_tool.py').render(ui, _world()).items()}
    pages = {**render_demos(ui), **render_pswb_tools(ui), **render_html_import(ui), **maps, **render_gif_tool(ui), **render_chat_tool(ui)}
    for sheet, builder in STYLESHEET_BUNDLES.items():
        prefix = b'<style>' + getattr(ui, builder)().encode()
        for path, page in pages.items():
            head, end, body = page.partition(b'</head>')
            if prefix in head:
                href = os.path.relpath(ASSET_BASE + sheet, os.path.dirname(path)).replace(os.sep, '/')
                link = f'<link rel="stylesheet" href="{href}">'.encode()
                head = head.replace(prefix, link + b'<style>', 1).replace(link + b'<style></style>', link, 1)
                pages[path] = stamp_size((head + end + body).decode('utf-8')).encode('utf-8')   # 📦 the page is smaller now
    return pages


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
    expected = ({HTML_IMPORT_PAGE, GIF_PAGE, CHAT_PAGE, *PSWB_TOOLS} | MAP_PAGES | {DEMO_BASE + name + '.html' for name in WORLD_PAGES})
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
    build(output, root)
    stage_tools(output, root)


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
                        help="🎥 record a moving sample of every repository's Pages under DIR/media/pages/ (Chromium; best effort)")
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
        # 🎥 this portfolio too: its card shows the front page as Pages serves it now (the deploy before this one)
        print('\n'.join(record_samples(args.record_samples, pages_urls())))
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
