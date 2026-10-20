"""Thin consumer adapter around pinned web-ui; report ownership stays in lab."""

from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vendor_loader import load_module

ui = load_module('publication_web_ui', 'tools/vendor/web-ui/web_ui.py')

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
    b"viewAttribute:'data-pages-view',navAttribute:'data-pages-nav',queryAliases:{wiki:'wiki'}});\n"
)


def presentation_identity() -> dict:
    lock = json.loads((ROOT / 'tools/html-import/vendor.lock.json').read_text(encoding='utf-8'))
    return {
        'owner': 'myon-bioinformatics/web-ui',
        'theme': 'modern',
        'assets': [x for x in lock['sources'] if x['repository'].endswith('/web-ui')],
    }


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
    return page.replace(
        'Styling: single lab-owned <code>terminal.css</code> (no external stylesheet chain).',
        'Styling: pinned local <code>web-ui</code> modern theme; imported report and lab tool behavior retain their source identity.',
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
    payload['pixiv-markup.js'] = (ROOT / 'tools/pixiv/markup.js').read_bytes()
    payload['pixiv-panel.js'] = (ROOT / 'tools/pixiv/panel.js').read_bytes()
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
