from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PAGES = {
    "https://myon-bioinformatics.github.io/flutter_navigation_basic/",
    "https://myon-bioinformatics.github.io/web-ui/",
    "https://myon-bioinformatics.github.io/Ironmate/",
    "https://myon-bioinformatics.github.io/Ironmate/tools/",
    "https://myon-bioinformatics.github.io/Ironmate/slides/",
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


def test_ironmate_metadata_lives_with_the_portfolio():
    import json
    metadata = json.loads((ROOT / "project-ironmate.json").read_text())
    assert metadata["schema"] == "project-metadata/1"
    assert metadata["repository"] == "https://github.com/myon-bioinformatics/Ironmate"
    parser = LinkParser()
    parser.feed((ROOT / "index.html").read_text())
    assert metadata["repository"] not in parser.links
    # The former repository fallback is removed; metadata remains machine-readable.
    assert "./project-ironmate.json" not in parser.links
    assert (ROOT / "project-ironmate.json").is_file()
    assert not any("/Ironmate/mcp-stub.html" in url for url in parser.links)


def test_ironmate_pptx_status_is_prototype_not_product_ready():
    import json

    metadata = json.loads((ROOT / "project-ironmate.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "prototype_implemented"
    assert metadata["pptx"]["status"] == "prototype"
    conversion = metadata["pptx"]["markdown_to_pptx"]
    editing = metadata["pptx"]["existing_pptx_editing"]
    assert conversion["cli"] == "pptx_pipeline.py"
    assert conversion["input_modes"] == ["Markdown file", "inline --text", "stdin -"]
    assert "preinstalled Marp CLI" in conversion["requires"]
    assert "Marp-generated slides may not have editable text" in conversion["limitations"]
    assert editing["cli"] == "pptx_replace.py"
    assert "text replacement within each text run" in editing["supported"]
    assert "explicit solid RGB slide background" in editing["supported"]
    assert "theme/inherited text colors and slide backgrounds" in editing["unsupported"]
    assert "arrow attributes and advanced formatting" in editing["unsupported"]

    html = (ROOT / "index.html").read_text(encoding="utf-8")
    card_start = html.index('<h3 id="ironmate">Ironmate</h3>')
    card = html[card_start:html.index("</article>", card_start)]
    assert "PPTX対応は計画段階" not in card
    assert "Markdown→PPTX" in card
    assert "試作実装" in card
    assert "ブラウザでスライドを作成" in card
    assert "Open Repository" not in card
    assert "Ironmate/slides/" in card


def test_lab_pages_are_hosted_by_portfolio():
    parser = LinkParser()
    parser.feed((ROOT / "index.html").read_text())
    assert "mcp-toolcall-lab" in parser.ids
    assert "./tools/mcp-toolcall-lab/" in parser.links
    assert (ROOT / "tools/mcp-toolcall-lab/index.html").is_file()


def test_every_tool_page_has_the_same_back_link_first_in_main():
    import re
    pages = [ROOT / "tools/html-import/index.html", ROOT / "tools/mcp-toolcall-lab/index.html",
             ROOT / "tools/mcp-toolcall-lab/repository-diagnostics.html"]
    for page in pages:
        html = page.read_text(encoding="utf-8")
        main = re.search(r"<main[^>]*>", html)
        assert main, page
        after = html[main.end():]
        assert after.startswith('<nav class="portfolio-back" aria-label="Portfolio">'
                                '<a href="../../index.html#tools" data-testid="portfolio-back">'), page
        assert html.count('data-testid="portfolio-back"') == 1, page
        assert "Back to portfolio" not in html, page
