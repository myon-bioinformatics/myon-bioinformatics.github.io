import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from record_demo import stitch_png_grid
from generate_apng import PNG_SIGNATURE, _make_chunk


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
