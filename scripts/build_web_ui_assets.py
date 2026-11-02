"""Generate locked browser assets, retaining checked-in legacy snapshots.

Only build output is replaced. All source/output hashes are verified before writes.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ASSET_BASE = 'tools/vendor/web-ui/'
ASSETS = ('css/base.css', 'css/components.css', 'css/themes/modern.css',
          'css/tokens.css', 'js/navigation.js', 'js/ui.js', 'js/controls.js',
          'js/collection.js')


def generate(root: Path = ROOT) -> dict[str, bytes]:
    lock = json.loads((root / 'web-ui-assets.lock.json').read_text(encoding='utf-8'))
    if lock['schema'] != 'web-ui-generated/1':
        raise ValueError('unsupported generated asset lock')
    # The generator must also be an ordinary immutable vendor-lock/1 source.
    vendor = json.loads((root / 'vendor.lock.json').read_text(encoding='utf-8'))
    sources = [x for x in vendor['files'] if x.get('destination') == lock['generator']]
    if len(sources) != 1:
        raise ValueError('vendor lock must contain exactly one generator entry')
    source = sources[0]
    if (source['repository'] != 'myon-bioinformatics/web-ui'
            or source['source'] != 'web_ui.py'
            or source['ref'] != source['commit'] or source['commit'] != lock['commit']
            or source['sha256'] != lock['sha256']):
        raise ValueError('generator provenance mismatch')
    path = root / lock['generator']
    raw = path.read_bytes()
    blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if hashlib.sha256(raw).hexdigest() != lock['sha256'] or blob != source['blob_sha']:
        raise ValueError('generator hash mismatch')
    if set(lock['outputs']) != {ASSET_BASE + name for name in ASSETS}:
        raise ValueError('generated output paths differ from public URL contract')
    spec = importlib.util.spec_from_file_location('locked_web_ui_generator', path)
    ui = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ui)
    with tempfile.TemporaryDirectory() as directory:
        ui.write_js(directory)
        result = {}
        for name in ASSETS:
            data = (ui.css_source(name[4:]).encode('utf-8') if name.startswith('css/')
                    else (Path(directory) / name).read_bytes())
            target = ASSET_BASE + name
            if hashlib.sha256(data).hexdigest() != lock['outputs'][target]:
                raise ValueError(f'generated asset hash mismatch: {target}')
            result[target] = data
    return result


def build(output: Path, root: Path = ROOT) -> None:
    output = output.resolve()
    if output == root.resolve() or root.resolve().is_relative_to(output):
        raise ValueError('output must not overwrite the source snapshot')
    payload = generate(root)  # Fail closed before touching any output.
    for name, data in payload.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    # Publish the active asset provenance beside the generated files.
    (output / ASSET_BASE / 'generated.lock.json').write_bytes(
        (root / 'web-ui-assets.lock.json').read_bytes())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.output)
