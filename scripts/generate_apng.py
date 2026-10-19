"""Zero-dependency pure-Python APNG (Animated PNG) generator.

Combines a list of PNG frame files into a single APNG file containing acTL,
fcTL, and fdAT chunks.
"""
import argparse
from pathlib import Path
import struct
import zlib

PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


def _make_chunk(ctype: bytes, data: bytes) -> bytes:
    length = len(data)
    crc = zlib.crc32(ctype + data) & 0xFFFFFFFF
    return struct.pack('>I', length) + ctype + data + struct.pack('>I', crc)


def _parse_png_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError('Invalid PNG signature')
    idx = 8
    chunks = []
    while idx < len(data):
        length, ctype = struct.unpack('>I4s', data[idx:idx + 8])
        cdata = data[idx + 8:idx + 8 + length]
        chunks.append((ctype, cdata))
        idx += 12 + length
    return chunks


def create_apng(frame_paths: list[str | Path], output_path: str | Path, delay_ms: int = 500, loops: int = 0) -> Path:
    """Combine a list of PNG image file paths into an APNG file.

    :param frame_paths: Paths to input PNG images (must be same dimensions and color depth).
    :param output_path: Path to write the output APNG file.
    :param delay_ms: Frame display delay in milliseconds.
    :param loops: Number of animation loops (0 = infinite).
    """
    if not frame_paths:
        raise ValueError('No frame paths provided')

    out_path = Path(output_path)
    frames_data = [Path(p).read_bytes() for p in frame_paths]
    parsed_frames = [_parse_png_chunks(d) for d in frames_data]

    # First frame's IHDR chunk defines width and height
    first_ihdr = next(cdata for ctype, cdata in parsed_frames[0] if ctype == b'IHDR')
    width, height = struct.unpack('>II', first_ihdr[:8])

    out = bytearray(PNG_SIGNATURE)
    out.extend(_make_chunk(b'IHDR', first_ihdr))

    # acTL chunk: num_frames (uint32), num_plays (uint32)
    num_frames = len(parsed_frames)
    out.extend(_make_chunk(b'acTL', struct.pack('>II', num_frames, loops)))

    seq = 0
    delay_num = delay_ms
    delay_den = 1000

    for i, frame in enumerate(parsed_frames):
        # fcTL chunk: sequence_number, width, height, x_offset, y_offset, delay_num, delay_den, dispose_op, blend_op
        fctl_data = struct.pack('>IIIIIHHBB', seq, width, height, 0, 0, delay_num, delay_den, 0, 0)
        out.extend(_make_chunk(b'fcTL', fctl_data))
        seq += 1

        idat_chunks = [cdata for ctype, cdata in frame if ctype == b'IDAT']
        for idat in idat_chunks:
            if i == 0:
                # First frame uses standard IDAT chunk
                out.extend(_make_chunk(b'IDAT', idat))
            else:
                # Subsequent frames use fdAT chunk: sequence_number + IDAT data
                fdat_data = struct.pack('>I', seq) + idat
                out.extend(_make_chunk(b'fdAT', fdat_data))
                seq += 1

    out.extend(_make_chunk(b'IEND', b''))
    out_path.write_bytes(out)
    return out_path


def main():
    parser = argparse.ArgumentParser(description='Create an Animated PNG (APNG) from PNG frames.')
    parser.add_argument('frames', nargs='+', help='Paths to input PNG frame files')
    parser.add_argument('-o', '--output', required=True, help='Output APNG file path')
    parser.add_argument('-d', '--delay', type=int, default=500, help='Frame delay in milliseconds (default: 500)')
    parser.add_argument('-l', '--loops', type=int, default=0, help='Animation loop count, 0 for infinite (default: 0)')

    args = parser.parse_args()
    create_apng(args.frames, args.output, delay_ms=args.delay, loops=args.loops)
    print(f'Successfully created APNG at {args.output}')


if __name__ == '__main__':
    main()
