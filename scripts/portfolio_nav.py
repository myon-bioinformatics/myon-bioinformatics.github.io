"""One way back from every portfolio-hosted tool page, and a short label for its shortcut.

Every page under tools/<name>/ gets the same link, as the first element inside
<main>, so returning after a transition never depends on where a page put it.
Builders (tools/build_html_import.py) and the lab import (scripts/import_lab_pages.py)
both call add_back_nav() and add_home_label(), so regenerated or re-imported pages keep them.
"""
import html
import re
BACK_NAV = ('<nav class="portfolio-back" aria-label="Portfolio">'
            '<a href="../../index.html#tools" data-testid="portfolio-back">← Tools &amp; Demos</a></nav>')


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


def add_home_label(page: str, label: str) -> str:
    """Name a home-screen shortcut of the page ``label`` (iOS reads apple-mobile-web-app-title, Chrome application-name).

    A long <title> is cut off under the icon; replaces any earlier label, so it is idempotent.
    """
    page = re.sub(r'<meta\b[^>]*\bname=["\'](?:apple-mobile-web-app-title|application-name)["\'][^>]*>', '', page, flags=re.I)
    value = html.escape(label, quote=True)
    tags = f'<meta name="apple-mobile-web-app-title" content="{value}"><meta name="application-name" content="{value}">'
    # Right after <title>, the name it shortens, so steps that append to </head> (lab branding) keep their place.
    for anchor in ('</title>', '</head>'):
        if anchor in page:
            return page.replace(anchor, anchor + tags if anchor == '</title>' else tags + anchor, 1)
    raise ValueError('page has no </title> or </head>')
