"""🎨 Assets and generators: brand assets, image and APNG regressions, the demo recorder and pixiv markup."""

import hashlib
import importlib.util
import io
import json
import struct
import subprocess
import sys
import tempfile
import zlib
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from generate_apng import PNG_SIGNATURE, _make_chunk, _parse_png_chunks, create_apng
from record_demo import stitch_png_grid
from vendor_loader import load_module


# ═══ 🎨 brand assets ══════════════════════════════════════════════════════════════════════════════════════
# Verify supplied brand artwork and the browser favicon contract.

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


# ═══ 🖼️ image regressions ════════════════════════════════════════════════════════════════════════════════
# Decode exported images independently, including real PNG filter encodings.

def png_chunk(kind, payload):
    return (struct.pack('>I', len(payload)) + kind + payload
            + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff))


def independent_png(rows, color_type, filter_type=0, metadata=()):
    """Encode known samples without using the decoder or its PNG writer.

    Split the compressed stream so create_apng must emit and the decoder must
    join several fdAT chunks for one frame, including splits inside zlib headers.
    """
    channels = {0: 1, 2: 3, 3: 1, 6: 4}[color_type]
    width = len(rows[0]) // channels
    encoded = bytearray()
    previous = bytes(len(rows[0]))
    for row in rows:
        encoded.append(filter_type)
        for index, sample in enumerate(row):
            left = row[index - channels] if index >= channels else 0
            above = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            estimate = left + above - upper_left
            paeth = min((left, above, upper_left), key=lambda v: abs(estimate - v))
            prediction = (0, left, above, (left + above) // 2, paeth)[filter_type]
            encoded.append((sample - prediction) % 256)
        previous = row
    compressed = zlib.compress(encoded)
    header = struct.pack('>IIBBBBB', width, len(rows), 8, color_type, 0, 0, 0)
    parts = (compressed[:1], compressed[1:5], compressed[5:])
    return (b'\x89PNG\r\n\x1a\n' + png_chunk(b'IHDR', header)
            + b''.join(png_chunk(k, d) for k, d in metadata)
            + b''.join(png_chunk(b'IDAT', part) for part in parts)
            + png_chunk(b'IEND', b''))


@pytest.mark.parametrize('color_type,mode', [(2, 'RGB'), (6, 'RGBA')])
@pytest.mark.parametrize('filter_type', range(5))
def test_independent_filtered_pixels_frames_and_grid(tmp_path, color_type, mode, filter_type):
    channels = len(mode)
    paths, expected = [], []
    for frame in range(3):
        pixels = bytes((x * 61 + y * 43 + band * 79 + frame * 101) % 256
                       for y in range(5) for x in range(7) for band in range(channels))
        rows = [pixels[y * 7 * channels:(y + 1) * 7 * channels] for y in range(5)]
        path = tmp_path / f'independent{frame}.png'
        path.write_bytes(independent_png(rows, color_type, filter_type))
        assert Image.open(path).tobytes() == pixels
        paths.append(path)
        expected.append(pixels)
    animation = Image.open(create_apng(paths, tmp_path / 'filtered-apng.png', delay_ms=125, loops=4))
    assert animation.mode == mode
    assert animation.n_frames == 3 and animation.is_animated
    assert animation.info['loop'] == 4
    for index in (0, 1, 2, 0, 2):
        animation.seek(index)
        assert animation.tell() == index
        assert animation.convert(mode).tobytes() == expected[index]
        assert animation.info['duration'] == 125
    with pytest.raises(EOFError):
        animation.seek(3)
    grid = Image.open(stitch_png_grid(paths, tmp_path / 'filtered-grid.png', columns=2))
    for index, pixels in enumerate(expected):
        x, y = index % 2 * 7, index // 2 * 5
        assert grid.crop((x, y, x + 7, y + 5)).convert(mode).tobytes() == pixels


@pytest.mark.parametrize('color_type,rows,metadata,expected', [
    (0, [bytes([17, 18])], [(b'tRNS', struct.pack('>H', 17))],
     bytes([17, 17, 17, 0, 18, 18, 18, 255])),
    (2, [bytes([17, 23, 31, 17, 23, 32])], [(b'tRNS', struct.pack('>HHH', 17, 23, 31))],
     bytes([17, 23, 31, 0, 17, 23, 32, 255])),
    (3, [bytes([0, 1, 2])], [(b'PLTE', bytes([255, 0, 0, 0, 255, 0, 0, 0, 255])),
                            (b'tRNS', bytes([0, 128, 255]))],
     bytes([255, 0, 0, 0, 0, 255, 0, 128, 0, 0, 255, 255])),
])
def test_independent_transparency_in_png_and_apng(tmp_path, color_type, rows, metadata, expected):
    path = tmp_path / 'transparent.png'
    path.write_bytes(independent_png(rows, color_type, metadata=metadata))
    assert Image.open(path).convert('RGBA').tobytes() == expected
    animation = Image.open(create_apng([path, path], tmp_path / 'transparent-apng.png'))
    assert animation.n_frames == 2
    for index in range(2):
        animation.seek(index)
        assert animation.convert('RGBA').tobytes() == expected


def test_independent_decode_limits_and_invalid_payloads():
    png = independent_png([bytes([10, 20, 30])], 2)
    with pytest.raises(ValueError, match='limit'):
        Image.open(png, max_decompressed=3)  # row is 3 samples plus its filter byte
    large_header = struct.pack('>IIBBBBB', 1000, 1000, 8, 2, 0, 0, 0)
    large = png[:8] + png_chunk(b'IHDR', large_header) + png[33:]
    with pytest.raises(ValueError, match='limit'):
        Image.open(large, max_pixels=100)
    for bad in (png[:20], png[:-1], png[:25] + bytes([png[25] ^ 1]) + png[26:]):
        with pytest.raises((ValueError, OSError)):
            Image.open(bad)
    # Valid chunk CRC but more inflated samples than the IHDR permits.
    oversized = (png[:33] + png_chunk(b'IDAT', zlib.compress(bytes(100)))
                 + png_chunk(b'IEND', b''))
    with pytest.raises(ValueError, match='limit'):
        Image.open(oversized)


def frames(tmp_path, mode='RGBA'):
    paths = []
    for i in range(3):
        image = Image.new(mode, (19, 13))
        image.putdata([((x * 13 + i * 80) % 256, (y * 19) % 256, x + y, 128 + i * 40)
                       if mode == 'RGBA' else ((x * 13 + i * 80) % 256, (y * 19) % 256, x + y)
                       for y in range(13) for x in range(19)])
        path = tmp_path / f'{i}.png'
        image.save(path)
        paths.append(path)
    return paths


@pytest.mark.parametrize('mode', ['RGB', 'RGBA'])
def test_exported_pixels_match_original_frames(tmp_path, mode):
    paths = frames(tmp_path, mode)
    apng = create_apng(paths, tmp_path/'animation.png', delay_ms=70000, loops=2)
    with Image.open(apng) as animation:
        assert animation.n_frames == 3
        assert animation.info['loop'] == 2
        for i, path in enumerate(paths):
            animation.seek(i)
            assert animation.convert(mode).tobytes() == Image.open(path).tobytes()
            assert animation.info['duration'] == 70000
    montage = stitch_png_grid(paths, tmp_path/'grid.png', columns=2)
    with Image.open(montage) as grid:
        assert grid.size == (38, 26)
        for i, path in enumerate(paths):
            x, y = i % 2 * 19, i // 2 * 13
            assert grid.crop((x,y,x+19,y+13)).tobytes() == Image.open(path).tobytes()


def test_palette_and_transparency_are_preserved(tmp_path):
    paths = []
    for i in range(2):
        image = Image.new('P', (3, 2), i)
        image.putpalette([255,0,0, 0,255,0] + [0]*762)
        path = tmp_path/f'indexed{i}.png'
        image.save(path, transparency=0)
        paths.append(path)
    with Image.open(create_apng(paths, tmp_path/'indexed.png')) as animation:
        for i, path in enumerate(paths):
            animation.seek(i)
            assert animation.convert('RGBA').tobytes() == Image.open(path).convert('RGBA').tobytes()


@pytest.mark.parametrize('corrupt', [lambda b: b[:20], lambda b: b[:-1], lambda b: b[:25]+bytes([b[25]^1])+b[26:]])
def test_bad_png_is_rejected_before_overwriting_output(tmp_path, corrupt):
    paths = frames(tmp_path)
    paths[1].write_bytes(corrupt(paths[1].read_bytes()))
    output = tmp_path/'out.png'; output.write_bytes(b'existing')
    with pytest.raises(ValueError):
        create_apng(paths, output)
    assert output.read_bytes() == b'existing'


def test_mismatched_frames_and_invalid_options(tmp_path):
    paths = frames(tmp_path)
    Image.new('RGBA', (3,2)).save(paths[1])
    with pytest.raises(ValueError, match='matching'):
        create_apng(paths, tmp_path/'bad.png')
    with pytest.raises(ValueError, match='identical'):
        stitch_png_grid(paths, tmp_path/'bad.png')
    for options in ({'delay_ms':0}, {'delay_ms':-1}, {'loops':-1}):
        with pytest.raises(ValueError):
            create_apng(paths[:1], tmp_path/'bad.png', **options)
    with pytest.raises(ValueError, match='Columns'):
        stitch_png_grid(paths[:1], tmp_path/'bad.png', columns=0)


def test_image_clis_work_without_site_packages(tmp_path):
    paths = frames(tmp_path)
    root = Path(__file__).resolve().parents[1]
    for script in ('generate_apng.py', 'record_demo.py'):
        subprocess.run([sys.executable, '-S', str(root/'scripts'/script), *map(str,paths),
                        '-o', str(tmp_path/script.replace('.py','.png'))], check=True)


# ═══ 🎞️ APNG generator ═══════════════════════════════════════════════════════════════════════════════════

def _create_minimal_png(width: int = 10, height: int = 10, color_rgb: tuple = (255, 0, 0)) -> bytes:
    import struct, zlib
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    raw_rows = []
    for _ in range(height):
        row = b'\x00' + bytes(color_rgb) * width
        raw_rows.append(row)
    compressed = zlib.compress(b''.join(raw_rows))

    png = bytearray(PNG_SIGNATURE)
    png.extend(_make_chunk(b'IHDR', ihdr_data))
    png.extend(_make_chunk(b'IDAT', compressed))
    png.extend(_make_chunk(b'IEND', b''))
    return bytes(png)


def test_apng_generator_creates_valid_apng():
    with tempfile.TemporaryDirectory() as tmpdir:
        frame1 = Path(tmpdir) / 'frame1.png'
        frame2 = Path(tmpdir) / 'frame2.png'
        out_apng = Path(tmpdir) / 'output_animation.png'

        frame1.write_bytes(_create_minimal_png(20, 20, (255, 0, 0)))
        frame2.write_bytes(_create_minimal_png(20, 20, (0, 255, 0)))

        result_path = create_apng([frame1, frame2], out_apng, delay_ms=300, loops=0)
        assert result_path.is_file()

        data = out_apng.read_bytes()
        assert data.startswith(PNG_SIGNATURE)
        assert b'acTL' in data
        assert b'fcTL' in data
        assert b'fdAT' in data


# ═══ 📹 record demo ═══════════════════════════════════════════════════════════════════════════════════════

def _create_test_png(width: int = 10, height: int = 10, color_rgb: tuple = (255, 0, 0)) -> bytes:
    import struct, zlib
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    raw_rows = []
    for _ in range(height):
        row = b'\x00' + bytes(color_rgb) * width
        raw_rows.append(row)
    compressed = zlib.compress(b''.join(raw_rows))

    png = bytearray(PNG_SIGNATURE)
    png.extend(_make_chunk(b'IHDR', ihdr_data))
    png.extend(_make_chunk(b'IDAT', compressed))
    png.extend(_make_chunk(b'IEND', b''))
    return bytes(png)


def test_stitch_png_grid_creates_valid_montage():
    with tempfile.TemporaryDirectory() as tmpdir:
        f1 = Path(tmpdir) / 'f1.png'
        f2 = Path(tmpdir) / 'f2.png'
        f3 = Path(tmpdir) / 'f3.png'
        out_montage = Path(tmpdir) / 'montage.png'

        f1.write_bytes(_create_test_png(20, 20, (255, 0, 0)))
        f2.write_bytes(_create_test_png(20, 20, (0, 255, 0)))
        f3.write_bytes(_create_test_png(20, 20, (0, 0, 255)))

        res = stitch_png_grid([f1, f2, f3], out_montage, columns=2)
        assert res.is_file()
        data = out_montage.read_bytes()
        assert data.startswith(PNG_SIGNATURE)
        assert b'IDAT' in data


# ═══ ✍️ pixiv markup ═════════════════════════════════════════════════════════════════════════════════════

spec = importlib.util.spec_from_file_location('pixiv_markup', ROOT / 'scripts/pixiv_markup.py')
markup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(markup)
FIXTURES = json.loads((ROOT / 'tests/fixtures/pixiv-markup.json').read_text())


def test_python_and_browser_share_one_narrow_contract():
    js = "const m=require('./tools/pixiv/markup.js');const fs=require('fs');console.log(JSON.stringify(JSON.parse(fs.readFileSync(0,'utf8')).map(x=>m.extractSource(x.source,x.title||''))))"
    run = subprocess.run(['node', '-e', js], input=json.dumps(FIXTURES), text=True, capture_output=True, cwd=ROOT, check=True)
    assert json.loads(run.stdout) == [markup.extract_source(item['source'], item.get('title', '')) for item in FIXTURES]


def test_plain_star_headings_parent_scope_tables_and_media():
    result = markup.extract_source(FIXTURES[0]['source'])
    assert result['title'] == '試験記事'
    assert [h['heading'] for h in result['headings']] == ['概要', '世界観', '文明描写', '社会構成', '関連イラスト', '関連動画']
    world = result['sections'][1]['body']
    assert '## 文明描写' in world and '## 社会構成' in world
    assert '関連イラスト' not in world
    assert '| **火の国** | [里](里) |' in world
    assert '| **水の国** | 別の里 |' in world
    assert '- **用語**\n  - [下位](用語%28詳細%29)' in world
    assert 'https://www.pixiv.net/artworks/123' in result['body']
    assert 'https://www.youtube.com/watch?v=nlRxufviKuc' in result['body']


def test_fenced_code_emphasis_and_duplicate_sections():
    result = markup.extract_source(FIXTURES[2]['source'])
    assert [h['heading'] for h in result['headings']] == ['本物', '次']
    assert '**太字だけ**' in result['body']
    assert '`[[literal]]`' in result['body']
    assert '*not heading\n# not heading' in result['body']
    duplicate = markup.extract_source('*同名\nfirst\n*同名\nsecond')['sections']
    assert [item['value'] for item in duplicate] == ['0', '1']
    assert [item['body'] for item in duplicate] == ['first', 'second']


def test_normalization_is_idempotent_and_rejects_oversize_input():
    for fixture in FIXTURES:
        normalized = markup.pixiv_to_markdown(fixture['source'])
        assert markup.pixiv_to_markdown(normalized) == normalized
    with pytest.raises(ValueError):
        markup.extract_source('x' * 200001)
    # Many sibling headings must not require quadratic lookahead.
    result = markup.extract_source('*x\ny\n' * 15000)
    assert len(result['sections']) == 15000
    assert result['sections'][-1]['body'] == 'y'


def test_import_reapplies_wrapper_and_generated_select():
    sys.path.insert(0, str(ROOT / 'scripts'))
    from lab_shared_ui import apply_shared_navigation
    source = '<html><head></head><body><div data-testid="pages-pixiv-app"><p data-testid="pages-pixiv-status"></p></div><script src="pages-pixiv.js?v=old"></script></body></html>'
    payload = {'index.html': source.encode(), 'pages-pixiv.js': b'api.autoMount(root);'}
    apply_shared_navigation(payload)
    apply_shared_navigation(payload)
    html = payload['index.html'].decode()
    assert html.count('id="pages-pixiv-heading"') == 1
    assert html.count('src="pixiv-panel.js"') == 1
    assert b'api.autoMount(root);' not in payload['pages-pixiv.js']
    assert payload['pixiv-markup.js'] == (ROOT / 'tools/pixiv/markup.js').read_bytes()
    assert payload['pixiv-panel.js'] == (ROOT / 'tools/pixiv/panel.js').read_bytes()
