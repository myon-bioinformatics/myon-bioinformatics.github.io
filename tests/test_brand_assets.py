"""Verify supplied brand artwork and the browser favicon contract."""
from html.parser import HTMLParser
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets" / "brand"


class BrandParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.icons = []
        self.images = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "link" and values.get("rel") == "icon":
            self.icons.append(values)
        if tag == "img":
            self.images.append(values)


def test_source_crops_preserve_dimensions_and_rgb_background():
    for name, size in (("myon-profile-icon.png", 384), ("myon-favicon-source.png", 160)):
        with Image.open(ASSETS / name) as image:
            image.load()
            assert image.format == "PNG"
            assert image.mode == "RGB"
            assert image.size == (size, size)


def test_favicons_have_expected_sizes_and_ico_frames_match_pngs():
    with Image.open(ROOT / "favicon.ico") as ico, Image.open(ASSETS / "myon-favicon-source.png") as source:
        assert ico.ico.sizes() == {(16, 16), (32, 32), (48, 48)}
        for size in (16, 32, 48):
            with Image.open(ASSETS / f"favicon-{size}x{size}.png") as png:
                assert png.size == (size, size)
                assert png.mode == "RGB"
                expected = source.resize((size, size), Image.Resampling.LANCZOS)
                assert png.tobytes() == expected.tobytes()
                assert ico.ico.getimage((size, size)).convert("RGB").tobytes() == png.tobytes()


def test_homepage_favicon_links_and_header_artwork_are_local():
    parser = BrandParser()
    parser.feed((ROOT / "index.html").read_text(encoding="utf-8"))
    assert {(item["href"], item["sizes"]) for item in parser.icons} == {
        ("./favicon.ico", "16x16 32x32 48x48"),
        ("./assets/brand/favicon-16x16.png", "16x16"),
        ("./assets/brand/favicon-32x32.png", "32x32"),
    }
    for item in parser.icons:
        assert (ROOT / item["href"]).is_file()
    brand = [item for item in parser.images if item.get("class") == "brand-icon"]
    assert len(brand) == 1
    assert brand[0]["src"] == "./assets/brand/myon-profile-icon.png"
    assert brand[0]["alt"] == ""  # Decorative beside the full brand name.
    assert brand[0]["width"] == brand[0]["height"] == "40"


def test_readme_uses_the_same_profile_artwork():
    parser = BrandParser()
    parser.feed((ROOT / "README.md").read_text(encoding="utf-8"))
    brand = [item for item in parser.images if item.get("src") == "assets/brand/myon-profile-icon.png"]
    assert len(brand) == 1
    assert brand[0]["alt"]
    assert brand[0]["width"] == brand[0]["height"] == "160"


def test_replacement_concept_diagram_is_preserved_and_linked():
    import hashlib

    diagram = ASSETS / "myon-concept-diagram.jpg"
    assert hashlib.sha256(diagram.read_bytes()).hexdigest() == "4b5f4673e1eabe737913828fa54ec101c12d7fb1e4883581b9e8cd96a3f00964"
    with Image.open(diagram) as image:
        assert image.format == "JPEG"
        assert image.size == (1536, 1024)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "](assets/brand/myon-concept-diagram.jpg)" in readme
