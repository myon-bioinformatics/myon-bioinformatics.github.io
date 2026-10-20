"""Combine matching PNG frames into APNG using only the standard library."""
import argparse
from math import gcd
from pathlib import Path
import struct
import zlib

PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


def _make_chunk(ctype: bytes, data: bytes) -> bytes:
    return (struct.pack('>I', len(data)) + ctype + data
            + struct.pack('>I', zlib.crc32(ctype + data) & 0xFFFFFFFF))


def _parse_png_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError('Invalid PNG signature')
    chunks = []
    idx = 8
    while idx < len(data):
        if len(data) - idx < 12:
            raise ValueError('Truncated PNG chunk')
        length, kind = struct.unpack_from('>I4s', data, idx)
        end = idx + 8 + length
        if end + 4 > len(data):
            raise ValueError('Truncated PNG data')
        payload = data[idx + 8:end]
        crc, = struct.unpack_from('>I', data, end)
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != crc:
            raise ValueError('Invalid PNG CRC')
        chunks.append((kind, payload))
        idx = end + 4
        if kind == b'IEND':
            if payload or idx != len(data):
                raise ValueError('Invalid PNG end')
            break
    if (not chunks or chunks[0][0] != b'IHDR' or len(chunks[0][1]) != 13
            or chunks[-1][0] != b'IEND' or not any(k == b'IDAT' for k, _ in chunks)
            or sum(k == b'IHDR' for k, _ in chunks) != 1):
        raise ValueError('Missing or invalid PNG structure')
    width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', chunks[0][1])
    depths = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
    if (not width or not height or depth not in depths.get(color, ())
            or compression or filtering or interlace not in (0, 1)):
        raise ValueError('Unsupported PNG header')
    if any(k in (b'acTL', b'fcTL', b'fdAT') for k, _ in chunks):
        raise ValueError('Input frames must be static PNG images')
    return chunks


def create_apng(frame_paths: list[str | Path], output_path: str | Path,
                delay_ms: int = 500, loops: int = 0) -> Path:
    """Combine static frames with identical IHDR, palette and transparency."""
    if not frame_paths:
        raise ValueError('No frame paths provided')
    if not isinstance(delay_ms, int) or delay_ms <= 0:
        raise ValueError('Frame delay must be a positive integer')
    if not isinstance(loops, int) or not 0 <= loops <= 0xFFFFFFFF:
        raise ValueError('Loop count must be a uint32')
    divisor = gcd(delay_ms, 1000)
    numerator, denominator = delay_ms // divisor, 1000 // divisor
    if numerator > 65535:
        raise ValueError('Frame delay is too large')
    frames = [_parse_png_chunks(Path(p).read_bytes()) for p in frame_paths]
    ihdr = frames[0][0][1]
    palette = [(k, d) for k, d in frames[0] if k in (b'PLTE', b'tRNS')]
    for frame in frames:
        if frame[0][1] != ihdr or [(k, d) for k, d in frame if k in (b'PLTE', b'tRNS')] != palette:
            raise ValueError('Frames must have matching dimensions, format, palette and transparency')
    if ihdr[9] == 3 and not any(k == b'PLTE' for k, _ in palette):
        raise ValueError('Indexed PNG requires a palette')
    width, height = struct.unpack('>II', ihdr[:8])
    out = bytearray(PNG_SIGNATURE + _make_chunk(b'IHDR', ihdr))
    out.extend(_make_chunk(b'acTL', struct.pack('>II', len(frames), loops)))
    # Preserve the first frame's color profile and ancillary metadata before IDAT.
    for kind, data in frames[0][1:]:
        if kind == b'IDAT':
            break
        out.extend(_make_chunk(kind, data))
    sequence = 0
    for index, frame in enumerate(frames):
        out.extend(_make_chunk(b'fcTL', struct.pack('>IIIIIHHBB', sequence, width, height,
                                                  0, 0, numerator, denominator, 0, 0)))
        sequence += 1
        for kind, data in frame:
            if kind == b'IDAT':
                if index == 0:
                    out.extend(_make_chunk(kind, data))
                else:
                    out.extend(_make_chunk(b'fdAT', struct.pack('>I', sequence) + data))
                    sequence += 1
    out.extend(_make_chunk(b'IEND', b''))
    path = Path(output_path)
    path.write_bytes(out)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('frames', nargs='+')
    parser.add_argument('-o', '--output', required=True)
    parser.add_argument('-d', '--delay', type=int, default=500)
    parser.add_argument('-l', '--loops', type=int, default=0)
    args = parser.parse_args()
    try:
        create_apng(args.frames, args.output, args.delay, args.loops)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(f'Successfully created APNG at {args.output}')


if __name__ == '__main__':
    main()
