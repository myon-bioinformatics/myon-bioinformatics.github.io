"""Decode exported images independently, including real PNG filter encodings."""
import io
from pathlib import Path
import struct
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from vendor_loader import load_module
from generate_apng import create_apng, _parse_png_chunks
from record_demo import stitch_png_grid

Image = load_module('pillow_min', 'tools/vendor/ironmate/pillow_min.py').Image


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
