from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PAGES = {
    "https://myon-bioinformatics.github.io/Ironmate/mcp-stub.html",
    "https://myon-bioinformatics.github.io/mcp-toolcall-lab/",
    "https://myon-bioinformatics.github.io/flutter_navigation_basic/",
    "https://myon-bioinformatics.github.io/web-ui/",
}

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.links = []
    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            self.ids.add(values["id"])
        if tag == "a" and values.get("href"):
            self.links.append(values["href"])

def test_portal_exposes_expected_pages():
    parser = LinkParser()
    parser.feed((ROOT / "index.html").read_text(encoding="utf-8"))
    assert "tools" in parser.ids
    assert EXPECTED_PAGES <= set(parser.links)

def test_portal_pages_stay_under_owned_pages_host():
    for url in EXPECTED_PAGES:
        parsed = urlparse(url)
        assert parsed.scheme == "https"
        assert parsed.netloc == "myon-bioinformatics.github.io"
        assert parsed.path.startswith("/")
