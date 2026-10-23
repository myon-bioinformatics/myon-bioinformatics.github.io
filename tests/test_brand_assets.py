"""Verify supplied brand artwork and the browser favicon contract."""
from html.parser import HTMLParser
from pathlib import Path
import hashlib
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from vendor_loader import load_module

Image = load_module('pillow_min', 'tools/vendor/ironmate/pillow_min.py').Image
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
    for name, size in (("myon-profile-icon.png", 170), ("myon-favicon-source.png", 77)):
        with Image.open(ASSETS / name) as image:
            image.load()
            assert (ASSETS / name).read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
            assert image.mode == "RGB"
            assert image.size == (size, size)


def test_favicons_have_expected_sizes_and_ico_frames_match_pngs():
    # Frozen RGB pixels from the reviewed Pillow LANCZOS exports. pillow_min
    # decodes PNG only; do not reintroduce Pillow for ICO or resampling here.
    expected_pixels = {16: '1c00e8a333b76ef0b844c3ba7f15c283b8898b5120bee12d2457f4232fe7910a', 32: 'a5db9cb07dc6bead53d116704fb4d186be146d1e4ca120f73d6e4e8e3c4978f4', 48: '4fc093c9f714a33d7c7dee668488bf1052a909ae6ed46ff1d0ae44a414db08bc'}
    with Image.open(ASSETS / 'myon-favicon-source.png') as source:
        assert hashlib.sha256(source.tobytes()).hexdigest() == '639ee9849ec9cb58c04fb44f4c073e65c4ad62c08b555f76e34d5f9433b1fd73'
    ico = (ROOT / 'favicon.ico').read_bytes()
    assert struct.unpack_from('<HHH', ico) == (0, 1, len(expected_pixels))
    sizes = set()
    for index in range(len(expected_pixels)):
        width, height, _, _, _, _, length, offset = struct.unpack_from('<BBBBHHII', ico, 6 + 16 * index)
        assert width == height
        assert width in expected_pixels
        sizes.add(width)
        assert offset >= 6 + 16 * len(expected_pixels)
        assert offset + length <= len(ico)
        png_path = ASSETS / f'favicon-{width}x{height}.png'
        assert ico[offset:offset + length] == png_path.read_bytes()
        with Image.open(png_path) as png:
            assert png.size == (width, height)
            assert png.mode == 'RGB'
            assert hashlib.sha256(png.tobytes()).hexdigest() == expected_pixels[width]
    assert sizes == set(expected_pixels)


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
    diagram = ASSETS / "myon-concept-diagram.jpg"
    # Full-file integrity also preserves the supplied JPEG's format/dimensions;
    # JPEG decoding is outside the PNG-only vendored helper's contract.
    assert hashlib.sha256(diagram.read_bytes()).hexdigest() == "4b5f4673e1eabe737913828fa54ec101c12d7fb1e4883581b9e8cd96a3f00964"
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "](assets/brand/myon-concept-diagram.jpg)" in readme


def test_brand_manifest_matches_exported_bytes_and_assignment():
    import json
    manifest = json.loads((ASSETS / 'portfolio-brand-manifest.json').read_text())
    assert manifest['assigned_to'] == 'portfolio'
    assert manifest['source_label'] == 'yourself'
    assert manifest['crop_coordinates'] == {'icon': [1232, 633, 1402, 803], 'favicon': [1423, 721, 1500, 798]}
    for name, expected in manifest['assets'].items():
        path = ROOT / name if name == 'favicon.ico' else ASSETS / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
