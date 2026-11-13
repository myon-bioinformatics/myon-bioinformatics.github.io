"""Generate the shared browser assets from the pinned PySaiyanWeBoo dependency.

The generator is the ``pysaiyanweboo`` module installed from ``requirements-pages.txt`` (a git
dependency pinned by commit). ``web-ui-assets.lock.json`` records that commit and the
SHA-256 of every output, so a build fails closed when the installed module is not the
pinned commit or when its output drifted from the lock. ``--refresh-lock`` rewrites the
lock and the checked-in copies under ``tools/vendor/web-ui/`` after the pin moves.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET_BASE = 'tools/vendor/web-ui/'
ASSETS = ('css/base.css', 'css/components.css', 'css/themes/modern.css',
          'css/tokens.css', 'js/navigation.js', 'js/ui.js', 'js/controls.js',
          'js/collection.js')
DISTRIBUTION = 'pysaiyanweboo'


def installed_commit(distribution: str = DISTRIBUTION) -> str:
    """The git commit the installed generator came from (pysaiyanweboo.installed_commit, i.e. pip's install record)."""
    if distribution != DISTRIBUTION:
        raise ValueError(f'{distribution} is not installed (pip install -r requirements-pages.txt)')
    try:
        import pysaiyanweboo
    except ImportError as exc:
        raise ValueError(f'{distribution} is not installed (pip install -r requirements-pages.txt)') from exc
    commit = pysaiyanweboo.installed_commit()
    if not commit:
        raise ValueError(f'{distribution} was not installed from its git source')
    return commit


def pinned_commit(root: Path = ROOT) -> str:
    """Read the immutable dependency pin; refresh must never adopt another install."""
    requirement = (root / 'requirements-pages.txt').read_text(encoding='utf-8')
    pins = re.findall(r'^pysaiyanweboo @ git\+https://github\.com/myon-bioinformatics/PySaiyanWeBoo@([0-9a-f]{40})$',
                      requirement, re.MULTILINE)
    if len(pins) != 1:
        raise ValueError('expected one full PySaiyanWeBoo commit pin')
    return pins[0]


def verify_pin(commit: str, root: Path = ROOT) -> None:
    if commit != pinned_commit(root):
        raise ValueError('installed generator differs from requirements-pages.txt pin')


def render(ui) -> dict[str, bytes]:
    """Every public asset rendered by the generator module, keyed by its published path."""
    with tempfile.TemporaryDirectory() as directory:
        ui.write_js(directory)
        result = {}
        for name in ASSETS:
            data = (ui.css_source(name[4:]).encode('utf-8') if name.startswith('css/')
                    else (Path(directory) / name).read_bytes())
            result[ASSET_BASE + name] = data
    return result


def generate(root: Path = ROOT, ui=None, commit: str | None = None) -> dict[str, bytes]:
    lock = json.loads((root / 'web-ui-assets.lock.json').read_text(encoding='utf-8'))
    if lock['schema'] != 'web-ui-generated/2':
        raise ValueError('unsupported generated asset lock')
    commit = commit or installed_commit()
    verify_pin(commit, root)
    if commit != lock['commit']:
        raise ValueError(f'generator provenance mismatch: installed {commit[:8]}, lock {lock["commit"][:8]}')
    if set(lock['outputs']) != {ASSET_BASE + name for name in ASSETS}:
        raise ValueError('generated output paths differ from public URL contract')
    if ui is None:
        import pysaiyanweboo as ui
    result = render(ui)
    for target, data in result.items():
        if hashlib.sha256(data).hexdigest() != lock['outputs'][target]:
            raise ValueError(f'generated asset hash mismatch: {target}')
    return result


def validate_output(output: Path, root: Path = ROOT) -> None:
    output = output.resolve()
    if output == root.resolve() or root.resolve().is_relative_to(output):
        raise ValueError('output must not overwrite the source snapshot')


def build(output: Path, root: Path = ROOT) -> None:
    validate_output(output, root)
    payload = generate(root)  # Fail closed before touching any output.
    for name, data in payload.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    # Publish the active asset provenance beside the generated files.
    (output / ASSET_BASE / 'generated.lock.json').write_bytes(
        (root / 'web-ui-assets.lock.json').read_bytes())


def refresh_lock(root: Path = ROOT) -> dict:
    """After moving the pin: rewrite the lock and the checked-in copies from the installed generator."""
    import pysaiyanweboo as ui
    commit = installed_commit()
    verify_pin(commit, root)
    payload = render(ui)
    lock = {
        'schema': 'web-ui-generated/2',
        'generator': 'pysaiyanweboo (requirements-pages.txt)',
        'commit': commit,
        'outputs': {target: hashlib.sha256(data).hexdigest() for target, data in payload.items()},
    }
    (root / 'web-ui-assets.lock.json').write_text(json.dumps(lock, indent=2) + '\n', encoding='utf-8')
    for target, data in payload.items():
        (root / target).parent.mkdir(parents=True, exist_ok=True)
        (root / target).write_bytes(data)
    return lock


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='write the generated assets under this directory')
    parser.add_argument('--refresh-lock', action='store_true',
                        help='rewrite web-ui-assets.lock.json and tools/vendor/web-ui/ from the installed generator')
    args = parser.parse_args(argv)
    if args.output:
        validate_output(args.output)
    if args.refresh_lock:
        print(json.dumps(refresh_lock(), indent=2))
    if args.output:
        build(args.output)
    if not args.refresh_lock and not args.output:
        parser.error('give --output DIR and/or --refresh-lock')


if __name__ == '__main__':
    raise SystemExit(main())
