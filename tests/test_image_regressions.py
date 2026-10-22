"""Decode exported images independently, including real PNG filter encodings."""
import io
from pathlib import Path
import struct
import subprocess
import sys
import zlib

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from vendor_loader import load_module
from generate_apng import create_apng, _parse_png_chunks
from record_demo import stitch_png_grid

Image = load_module('pillow_min', 'tools/vendor/ironmate/pillow_min.py').Image


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
