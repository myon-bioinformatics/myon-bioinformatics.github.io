"""One way back from every portfolio-hosted tool page.

Every page under tools/<name>/ gets the same link, as the first element inside
<main>, so returning after a transition never depends on where a page put it.
Builders (tools/build_html_import.py) and the lab import (scripts/import_lab_pages.py)
both call add_back_nav(), so regenerated or re-imported pages keep it.
"""
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
