import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_assets', ROOT / 'scripts/build_web_ui_assets.py')
assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assets)


def test_reproducible_build_preserves_legacy_snapshot(tmp_path):
    before = {name: (ROOT / name).read_bytes() for name in assets.generate()}
    assets.build(tmp_path)
    for name, data in assets.generate().items():
        assert (tmp_path / name).read_bytes() == data
        assert (ROOT / name).read_bytes() == before[name]
    assets.build(tmp_path)
    assert json.loads((tmp_path / assets.ASSET_BASE / 'generated.lock.json').read_text())['commit']


@pytest.mark.parametrize('tamper', ['source', 'output', 'path', 'commit'])
def test_tampering_fails_before_writing(tmp_path, tamper):
    root = tmp_path / 'source'
    root.mkdir()
    for name in ('vendor.lock.json', 'web-ui-assets.lock.json', 'tools/vendor/web-ui-generator/web_ui.py'):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    lock_path = root / 'web-ui-assets.lock.json'
    lock = json.loads(lock_path.read_text())
    if tamper == 'source':
        with (root / lock['generator']).open('a') as handle:
            handle.write('\n# changed\n')
    elif tamper == 'output':
        lock['outputs'][assets.ASSET_BASE + 'css/base.css'] = '0' * 64
    elif tamper == 'path':
        lock['outputs']['../escape.js'] = lock['outputs'].pop(assets.ASSET_BASE + 'js/ui.js')
    else:
        lock['commit'] = '0' * 40
    lock_path.write_text(json.dumps(lock))
    output = tmp_path / 'built'
    with pytest.raises(ValueError):
        assets.build(output, root)
    assert not output.exists()


def test_source_output_is_rejected():
    with pytest.raises(ValueError, match='source snapshot'):
        assets.build(ROOT)
