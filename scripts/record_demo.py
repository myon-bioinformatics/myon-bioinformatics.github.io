"""Flexible UI Demo Recorder & Media Exporter.

Exports PNG screenshot frames as APNG animations or stitched image montages.
"""
import argparse
from pathlib import Path
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from generate_apng import create_apng, _make_chunk, PNG_SIGNATURE


def stitch_png_grid(frame_paths: list[str | Path], output_path: str | Path, columns: int = 2) -> Path:
    """Stitch a sequence of PNG frames into a single multi-frame PNG grid montage.

    Uses raw uncompressed RGB scanlines and zlib to create a valid PNG without external libraries.
    """
    if not frame_paths:
        raise ValueError('No frame paths provided')

    out_path = Path(output_path)
    if not isinstance(columns, int) or columns < 1:
        raise ValueError('Columns must be a positive integer')
    from generate_apng import _parse_png_chunks
    frames = [_parse_png_chunks(Path(p).read_bytes()) for p in frame_paths]
    first_ihdr = frames[0][0][1]
    fw, fh, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', first_ihdr)
    if depth != 8 or color not in (2, 6) or interlace:
        raise ValueError('Montage requires non-interlaced 8-bit RGB/RGBA PNG frames')
    if any(frame[0][1] != first_ihdr for frame in frames):
        raise ValueError('Montage frames must have identical dimensions and format')
    bpp = 4 if color == 6 else 3
    stride = fw * bpp
    expected = fh * (stride + 1)
    if expected * len(frames) > 256 * 1024 * 1024:
        raise ValueError('Montage exceeds 256 MiB pixel budget')

    def paeth(a, b, c):
        predictor = a + b - c
        distances = (abs(predictor - a), abs(predictor - b), abs(predictor - c))
        return (a, b, c)[distances.index(min(distances))]

    frame_rows = []
    for frame in frames:
        decoder = zlib.decompressobj()
        raw = decoder.decompress(b''.join(d for k, d in frame if k == b'IDAT'), expected + 1)
        if len(raw) != expected or not decoder.eof or decoder.unused_data:
            raise ValueError('Invalid PNG scanline data')
        rows = []
        previous = bytearray(stride)
        for y in range(fh):
            start = y * (stride + 1)
            kind = raw[start]
            if kind > 4:
                raise ValueError('Invalid PNG scanline filter')
            row = bytearray(raw[start + 1:start + stride + 1])
            if kind:
                for x in range(stride):
                    left = row[x - bpp] if x >= bpp else 0
                    above = previous[x]
                    upper_left = previous[x - bpp] if x >= bpp else 0
                    if kind == 1:
                        prediction = left
                    elif kind == 2:
                        prediction = above
                    elif kind == 3:
                        prediction = (left + above) // 2
                    else:
                        prediction = paeth(left, above, upper_left)
                    row[x] = (row[x] + prediction) & 255
            rows.append(bytes(row))
            previous = row
        frame_rows.append(rows)

    num_frames = len(frame_rows)
    cols = min(columns, num_frames)
    rows_count = (num_frames + cols - 1) // cols

    total_width = cols * fw
    total_height = rows_count * fh

    montage_scanlines = []
    for r_idx in range(rows_count):
        row_frames = frame_rows[r_idx * cols:(r_idx + 1) * cols]
        # Padding if incomplete row
        while len(row_frames) < cols:
            blank_rows = [b'\x00' * (fw * bpp) for _ in range(fh)]
            row_frames.append(blank_rows)

        for py in range(fh):
            line = b'\x00'  # filter byte
            for f_rows in row_frames:
                line += f_rows[py]
            montage_scanlines.append(line)

    compressed_idat = zlib.compress(b''.join(montage_scanlines))

    # Construct final PNG
    ihdr_new = struct.pack('>IIBBBBB', total_width, total_height, 8, 2 if bpp == 3 else 6, 0, 0, 0)
    out = bytearray(PNG_SIGNATURE)
    out.extend(_make_chunk(b'IHDR', ihdr_new))
    out.extend(_make_chunk(b'IDAT', compressed_idat))
    out.extend(_make_chunk(b'IEND', b''))

    out_path.write_bytes(out)
    return out_path


def main():
    parser = argparse.ArgumentParser(description='Export interactive UI demos as APNG animations or stitched grid montages.')
    parser.add_argument('frames', nargs='+', help='PNG screenshot frame file paths')
    parser.add_argument('-o', '--output', required=True, help='Output image path (.png)')
    parser.add_argument('-m', '--mode', choices=['apng', 'montage'], default='apng', help='Output format: apng (animation) or montage (stitched grid)')
    parser.add_argument('-d', '--delay', type=int, default=600, help='APNG frame delay in ms')
    parser.add_argument('-c', '--columns', type=int, default=2, help='Montage grid column count')

    args = parser.parse_args()
    if args.mode == 'apng':
        create_apng(args.frames, args.output, delay_ms=args.delay)
        print(f'Created APNG animation at {args.output}')
    else:
        stitch_png_grid(args.frames, args.output, columns=args.columns)
        print(f'Created stitched montage at {args.output}')


if __name__ == '__main__':
    main()
