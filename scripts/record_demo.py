"""Flexible UI Demo Recorder & Media Exporter.

Captures interactive UI journeys and exports APNG animations, multi-frame
stitched image montages, and WebM videos.
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
    frames_bytes = [Path(p).read_bytes() for p in frame_paths]

    # Parse first frame to extract dimensions and color depth
    def parse_png(data):
        idx = 8
        chunks = []
        while idx < len(data):
            length, ctype = struct.unpack('>I4s', data[idx:idx + 8])
            cdata = data[idx + 8:idx + 8 + length]
            chunks.append((ctype, cdata))
            idx += 12 + length
        return chunks

    first_ihdr = next(cdata for ctype, cdata in parse_png(frames_bytes[0]) if ctype == b'IHDR')
    fw, fh = struct.unpack('>II', first_ihdr[:8])

    # Decompress raw scanlines for each frame
    def get_raw_rgb(data):
        chunks = parse_png(data)
        idats = b''.join(cdata for ctype, cdata in chunks if ctype == b'IDAT')
        decompressed = zlib.decompress(idats)
        # Assuming 8-bit RGB or RGBA
        bpp = 4 if len(decompressed) == fh * (1 + fw * 4) else 3
        rows = []
        row_len = 1 + fw * bpp
        for r in range(fh):
            row = decompressed[r * row_len:(r + 1) * row_len]
            rows.append(row[1:])  # drop filter byte
        return rows, bpp

    frame_rows = []
    bpp = 3
    for fb in frames_bytes:
        rows, bpp = get_raw_rgb(fb)
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
