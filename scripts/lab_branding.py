"""Apply approved lab artwork to the portfolio presentation, not report data."""
import re

# Same-origin published lab assets. Absolute paths resolve from both nested pages.
ASSET_BASE = '/mcp-toolcall-lab/execution/assets/'
FAVICON = ASSET_BASE + 'mcp-toolcall-lab-favicon-artwork.png'
LOGO = ASSET_BASE + 'mcp-toolcall-lab-logo.png'


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
        page = re.sub(r'(<header\b[^>]*>)', lambda match: match[1] + logo, page, count=1)
    return page
