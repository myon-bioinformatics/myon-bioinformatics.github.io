import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from generate_apng import create_apng, _make_chunk, PNG_SIGNATURE


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
