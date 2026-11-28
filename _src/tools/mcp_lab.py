"""🔌 MCP 実験室 (tools/mcp/): the portfolio's publication of mcp-toolcall-lab's tools; the lab supplies the built pages.

A build-time adapter like studio_routes.py, run by ``scripts/project_pages.py --record-tools`` on the lab's default
branch: the shared-UI adoption (a thin consumer adapter around the pinned PySaiyanWeBoo; report ownership stays in the
lab), the portfolio's own additions (the Niconico tab, the Pixiv wrapper in ``mcp/``) and the approved lab artwork.
No Docker runs here, so the page records no run: its test results are the lab's Actions.
"""
from __future__ import annotations
import hashlib, re, shutil
from collections.abc import Callable
from pathlib import Path

import pysaiyanweboo as ui

# ── shared UI adoption ──

CLASS_MAP = {
    'term-page': 'ui-page',
    'term-title': 'ui-title',
    'term-muted': 'ui-muted',
    'term-tag': 'ui-tag',
    'term-panel': 'ui-panel',
    'term-card': 'ui-card',
    'term-output': 'ui-output',
    'term-input': 'ui-input',
    'term-button': 'ui-button',
}

NAVIGATION_BINDING = (
    b"globalThis.webUiNavigation.bindViews(globalThis,{"
    b"viewAttribute:'data-pages-view',navAttribute:'data-pages-nav',queryAliases:{wiki:'wiki',pixiv:'pixiv',niconico:'niconico',pokemon:'pokemon'}});\n"
)
# The Niconico tab the portfolio adds before the Pixiv view; its behaviour is tools/niconico/search.js.
NICONICO_PANEL = '''<section id="niconico" data-pages-view="niconico" data-testid="pages-niconico" hidden><h2>Niconico Search: Snapshot Search API v2</h2><p>Try the official Niconico Snapshot Search API v2. Direct browser requests may be blocked by CORS. If results cannot be loaded, use the official search below.</p><div id="pages-niconico-app" data-testid="pages-niconico-app"><form id="pages-niconico-form" data-testid="pages-niconico-form"><p><label for="pages-niconico-query">Keyword</label> <input id="pages-niconico-query" name="q" value="初音ミク" placeholder="Search query" data-testid="pages-niconico-query" class="ui-input"></p><p><label for="pages-niconico-sort">Sort</label> <select id="pages-niconico-sort" name="sort" data-testid="pages-niconico-sort" class="ui-input"><option value="-viewCounter" selected>Views (High to Low)</option><option value="-startTime">Newest</option><option value="-likeCounter">Likes (High to Low)</option><option value="-mylistCounter">Mylists (High to Low)</option></select> <button type="submit" data-testid="pages-niconico-search" class="ui-button">Search</button></p></form><p><a id="pages-niconico-official" data-testid="pages-niconico-official" href="https://www.nicovideo.jp/search/%E5%88%9D%E9%9F%B3%E3%83%9F%E3%82%AF?sort=v&amp;order=d" target="_blank" rel="noopener noreferrer">Search on Niconico ↗</a></p><p id="pages-niconico-status" data-testid="pages-niconico-status" class="ui-muted"></p><p role="alert" id="pages-niconico-error" data-testid="pages-niconico-error" hidden></p><div id="pages-niconico-results" data-testid="pages-niconico-results"></div></div><script src="../niconico/search.js"></script><p><a href="#" data-pages-nav="home" data-testid="pages-nav-back">Back to report</a></p></section>'''


def apply_shared_ui(page: str) -> str:
    page = ui.adopt_document(
        page,
        asset_base='../vendor/web-ui',
        class_aliases=CLASS_MAP,
        remove_stylesheets=('terminal.css',),
    )
    page = re.sub(r'<script\s+src="pages-hash\.js(?:\?[^"]*)?"\s*></script>', '', page)
    if 'src="../vendor/web-ui/js/navigation.js"' not in page:
        page = page.replace('</head>', '<script src="../vendor/web-ui/js/navigation.js"></script></head>', 1)
    if 'src="shared-navigation.mjs"' not in page:
        page = page.replace('</body>', '<script type="module" src="shared-navigation.mjs"></script></body>', 1)
    page = apply_pixiv_controls(page)
    page = apply_prose_extracts(page)
    if 'data-testid="pages-nav-niconico"' not in page:
        anchor = re.search(r'<a\b[^>]*data-pages-nav="pixiv"[^>]*>.*?</a>', page)
        if anchor:
            nav = '<a href="#niconico" data-pages-nav="niconico" data-testid="pages-nav-niconico">Niconico</a>'
            page = page[:anchor.end()] + ' ' + nav + page[anchor.end():]
    if 'data-pages-view="niconico"' not in page:
        anchor = re.search(r'<section\b[^>]*data-pages-view="pixiv"[^>]*>', page)
        if anchor:
            page = page[:anchor.start()] + NICONICO_PANEL + page[anchor.start():]
    # The lab's own styling note (its terminal.css is not published here), in whichever wording the lab uses.
    return re.sub(r'Styling: (?:(?!</p>).)*?\(no external stylesheet chain\)\.',
                  'Styling: pinned local <code>web-ui</code> modern theme; the lab tools keep their source behavior.', page)


def apply_prose_extracts(page: str) -> str:
    """Article extracts are prose; reserve the shared monospace rule for code.

    ui-output already preserves whitespace and wraps text, without needing pre.
    Keep the imported content and all controller hooks unchanged.
    """
    return re.sub(
        r'<pre\b(?P<attrs>[^>]*\bdata-testid="pages-(?:pixiv|wiki)-extract"[^>]*)>'
        r'(?P<body>.*?)</pre>',
        r'<div\g<attrs>>\g<body></div>',
        page,
        flags=re.DOTALL,
    )


def apply_shared_navigation(payload: dict) -> None:
    payload['index.html'] = apply_shared_ui(payload['index.html'].decode('utf-8')).encode('utf-8')
    # Provider-specific title/URL builders remain in lab. Only the generic new-tab
    # validation/policy is delegated to the shared primitive.
    pixiv = payload['pages-pixiv.js'].decode('utf-8').replace(
        'win.open(url, "_blank", "noopener");', 'win.webUiNavigation.openExternalURL(url, win);'
    )
    # The consumer wrapper owns mounting; retain the imported URL/HTML helpers.
    pixiv = pixiv.replace('api.autoMount(root);', '/* Portfolio wrapper owns mounting. */')
    payload['pages-pixiv.js'] = pixiv.encode('utf-8')
    # The portfolio's own Pixiv wrapper is kept once, beside this file (mcp/), and published with the lab's pages.
    payload['pixiv-markup.js'] = (WRAPPER / 'pixiv-markup.js').read_bytes()
    payload['pixiv-panel.js'] = (WRAPPER / 'pixiv-panel.js').read_bytes()
    payload['shared-navigation.mjs'] = NAVIGATION_BINDING


def apply_pixiv_controls(page: str) -> str:
    """Generate the native dropdown from canonical web-ui, preserving report data."""
    if 'data-testid="pages-pixiv-app"' not in page:
        return page
    if 'id="pages-pixiv-heading"' not in page:
        control = ui.select((("", "(全文)"),), id="pages-pixiv-heading", label="見出し", disabled=True)
        marker = re.search(r'<p\b[^>]*data-testid="pages-pixiv-status"[^>]*>', page)
        if not marker:
            raise ValueError('Pixiv panel is missing its status anchor')
        page = page[:marker.start()] + '<p>' + control + '</p>' + page[marker.start():]
    if 'src="pixiv-panel.js"' not in page:
        marker = re.search(r'<script src="pages-pixiv\.js(?:\?[^"]*)?"></script>', page)
        if not marker:
            raise ValueError('Pixiv panel is missing its source helper')
        scripts = (
            '<script src="../vendor/web-ui/js/controls.js"></script>'
            '<script src="pixiv-markup.js"></script>' + marker[0] + '<script src="pixiv-panel.js"></script>'
        )
        page = page[:marker.start()] + scripts + page[marker.end():]
    page = page.replace(
        'Plain Pixiv source is also passed through the same conservative normalization contract as the MCP path:',
        'Plain Pixiv source is normalized by the portfolio wrapper:',
    )
    return page.replace(
        'labelled star headings, wiki links, pixivimage tokens, unspaced list items, and NEXT navigation',
        'star headings, wiki links, row-header tables, media links, and unspaced list items',
    )


# ── lab artwork ──
# Same-origin published lab assets. Absolute paths resolve from both nested pages.
ASSET_BASE = '/tools/mcp/execution/assets/'
FAVICON = ASSET_BASE + 'mcp-toolcall-lab-favicon-artwork.png'
LOGO = ASSET_BASE + 'mcp-toolcall-lab-logo.png'


def stage_lab_branding(built: Path, checkout: Path) -> None:
    """Keep the Tool Lab's artwork available when the separate execution build is paused."""
    assets = built / 'execution' / 'assets'
    assets.mkdir(parents=True, exist_ok=True)
    for name in (Path(LOGO).name, Path(FAVICON).name):
        target = assets / name
        if not target.exists():
            shutil.copyfile(checkout / 'docs' / 'assets' / name, target)


def apply_lab_branding(page: str) -> str:
    """Idempotently wire existing approved artwork without importing new data."""
    # An upstream export can already contain its own relative branding links.
    page = re.sub(r'<link\b[^>]*\brel=[\"\']icon[\"\'][^>]*>', '', page, flags=re.I)
    icon = f'<link rel="icon" type="image/png" sizes="180x180" href="{FAVICON}" data-lab-brand="favicon">'
    page = re.sub(r'<link\b[^>]*\brel=["\']apple-touch-icon["\'][^>]*>', '', page, flags=re.I)
    touch = f'<link rel="apple-touch-icon" sizes="180x180" href="{FAVICON}" data-lab-brand="touch-icon">'
    page = page.replace('</head>', icon + touch + '</head>', 1)
    if 'mcp-toolcall-lab-logo.png' in page:
        page = re.sub(r'(src=[\"\'])[^\"\']*mcp-toolcall-lab-logo\.png([\"\'])',
                      lambda match: match[1] + LOGO + match[2], page)
    else:
        logo = (f'<img data-lab-brand="logo" src="{LOGO}" '
                'alt="mcp-toolcall-lab logo: a robot and MCP flask, with the tagline Explore · Test · Trust" '
                'width="138" height="150">')
        if '<header' in page:
            page = re.sub(r'(<header\b[^>]*>)', lambda match: match[1] + logo, page, count=1)
        else:
            page = re.sub(r'(<h1\b[^>]*class="ui-title"[^>]*>.*?</h1>(?:\s*<p\b[^>]*class="ui-muted"[^>]*>.*?</p>)?)',
                          rf'<header>{logo}\1</header>', page, count=1, flags=re.DOTALL)
    return page


# ── 🧪 the report: no run here, the lab's Actions instead ──
ACTIONS = 'https://github.com/myon-bioinformatics/mcp-toolcall-lab/actions/workflows/stub-pages.yml'
_SUMMARY = re.compile(r'<h2>Last Actions summary</h2>\s*<p>.*?</p>\s*<pre><code\b[^>]*>.*?</code></pre>', re.DOTALL)


def apply_actions_report(page: str) -> str:
    """The lab's "Last Actions summary" needs a Docker run (stub + MCP mock + CPU-class model) that this build does not
    make, so its empty snapshot becomes a link to the lab's stub-pages runs; the local / Actions / MCP notes stay."""
    if 'Last Actions summary' not in page:
        return page
    page, count = _SUMMARY.subn('<h2>🧪 Test results</h2><p data-testid="lab-actions-report">Built here at deploy time without Docker, '
                                'so this page records no run. The stub + MCP mock + CPU-class model round-trip runs in the '
                                f'lab\'s <a href="{ACTIONS}">stub-pages Actions</a>.</p>', page, count=1)
    if not count:
        raise ValueError('the lab summary changed shape; update apply_actions_report')
    return page.replace('the actual round-trip is the "Last Actions summary" below.',
                        'the actual round-trip runs in the lab\'s Actions (🧪 Test results below).')


# ── the stage ──
FILES = ('index.html', 'pages-hash.js', 'pages-wiki.js', 'pages-pixiv.js', 'source.js', 'mcp.js', 'build_meta.json')   # mcp.js: 🤝 the #protocol panel
OPTIONAL = ('repository-diagnostics.json', 'repository-diagnostics.jsonl')   # 🩺 what the page's #diagnostics panel reads
WRAPPER = Path(__file__).with_name('mcp')     # the portfolio's Pixiv wrapper (pixiv-markup.js, pixiv-panel.js)
EXECUTION_URL = "https://myon-bioinformatics.github.io/tools/#mcp-execution"   # 🖼️ a framed #panel of the one screen
LABELS = {'index.html': '🧪 MCP Lab'}   # home-screen shortcut names


def apply_public_examples(payload: dict) -> None:
    """Keep editable example defaults empty without changing article/report data."""
    page = payload['index.html'].decode('utf-8')
    page = re.sub(r'(<input\b[^>]*\bid="pages-wiki-title"[^>]*\bvalue=")[^"]*(")',
                  r'\1\2', page)
    page = re.sub(r'CI screenshots of the local stub still use <code>fixtures/wikipedia/[^<]+</code>\. ', '', page)
    if 'data-testid="lab-execution-link"' not in page:
        page = page.replace('</header>', '</header><p><a data-testid="lab-execution-link" href="' +
                            EXECUTION_URL + '">Open Execution Lab →</a> (lab-hosted browser interface)</p>', 1)
    payload['index.html'] = page.encode('utf-8')
    script = payload['pages-wiki.js'].decode('utf-8')
    script = re.sub(r'(var DEFAULT_TITLE = )"[^"]*";', r'\1"";', script)
    payload['pages-wiki.js'] = script.encode('utf-8')
    version = hashlib.sha256(payload['pages-wiki.js']).hexdigest()[:10]
    payload['index.html'] = re.sub(
        rb'(src="pages-wiki\.js)(?:\?[^"]*)?(")',
        lambda match: match[1] + b'?v=' + version.encode('ascii') + match[2],
        payload['index.html'],
    )


def stage_lab_tools(built: Path, source_sha: str, checkout: Path, add_navigation: Callable[[str, str], str],
                    add_label: Callable[[str, str], str], folder: str = 'tools/mcp') -> None:
    """Turn the lab's built pages in ``built`` (``stub_front pages`` and its repository diagnostics, at ``source_sha``)
    into the 🔌 MCP 実験室 in place: only the allowlisted files stay (no raw logs, no empty summary), each page gets the
    shared UI, the portfolio's additions, the artwork, the way back (``add_navigation(page, path)``) and its home-screen
    name (``add_label``). Everything is read and checked before anything is written."""
    if not re.fullmatch(r'[0-9a-f]{40}', source_sha or ''):
        raise ValueError('the lab tools need the full source commit SHA')
    payload = {name: (built / name).read_bytes() for name in FILES}
    payload.update({name: (built / name).read_bytes() for name in OPTIONAL if (built / name).is_file()})
    page = payload['index.html'].decode('utf-8')
    if any(name in page and name not in payload for name in OPTIONAL):
        raise ValueError('referenced diagnostics must be built beside the page')
    if '</header>' not in page:
        raise ValueError('the lab page has no header')
    banner = ('<aside aria-label="Publication ownership"><p>🔌 Portfolio-hosted lab tools, built here at deploy time from '
              f'<a href="https://github.com/myon-bioinformatics/mcp-toolcall-lab/commit/{source_sha}">mcp-toolcall-lab@{source_sha[:7]}</a>. '
              f'🧪 Test results: <a href="{ACTIONS}">lab Actions</a>.</p></aside>')
    payload['index.html'] = apply_actions_report(page.replace('</header>', '</header>' + banner, 1)).encode('utf-8')
    apply_public_examples(payload)
    apply_shared_navigation(payload)
    for name, label in LABELS.items():
        if name in payload:
            page = apply_lab_branding(add_navigation(payload[name].decode('utf-8'), f'{folder}/{name}'))
            payload[name] = add_label(page, label).encode('utf-8')
    payload['LICENSE'] = (checkout / 'LICENSE').read_bytes()
    for leftover in built.iterdir():                # e.g. summary.json, terminal.css: not published
        if leftover.is_file() and leftover.name not in payload:
            leftover.unlink()
    for name, data in payload.items():
        (built / name).write_bytes(data)
