import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_assets', ROOT / 'scripts/build_web_ui_assets.py')
assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assets)


def test_installed_generator_is_the_pinned_commit():
    lock = json.loads((ROOT / 'web-ui-assets.lock.json').read_text())
    pin = (ROOT / 'requirements-pages.txt').read_text()
    assert lock['schema'] == 'web-ui-generated/2'
    assert assets.installed_commit() == lock['commit']
    assert f'PySaiyanWeBoo@{lock["commit"]}' in pin


def test_checked_in_copies_match_the_lock_and_the_generator(tmp_path):
    payload = assets.generate()
    lock = json.loads((ROOT / 'web-ui-assets.lock.json').read_text())
    for name, data in payload.items():
        assert (ROOT / name).read_bytes() == data, name           # tools/vendor/web-ui/ is the generated output, nothing older
        assert hashlib.sha256(data).hexdigest() == lock['outputs'][name]
    assets.build(tmp_path)
    for name, data in payload.items():
        assert (tmp_path / name).read_bytes() == data
    assert json.loads((tmp_path / assets.ASSET_BASE / 'generated.lock.json').read_text())['commit'] == lock['commit']


@pytest.mark.parametrize('tamper', ['output', 'path', 'commit', 'installed', 'schema'])
def test_tampering_fails_before_writing(tmp_path, tamper, monkeypatch):
    root = tmp_path / 'source'
    root.mkdir()
    shutil.copyfile(ROOT / 'web-ui-assets.lock.json', root / 'web-ui-assets.lock.json')
    lock_path = root / 'web-ui-assets.lock.json'
    lock = json.loads(lock_path.read_text())
    if tamper == 'output':
        lock['outputs'][assets.ASSET_BASE + 'css/base.css'] = '0' * 64
    elif tamper == 'path':
        lock['outputs']['../escape.js'] = lock['outputs'].pop(assets.ASSET_BASE + 'js/ui.js')
    elif tamper == 'commit':
        lock['commit'] = '0' * 40
    elif tamper == 'installed':
        monkeypatch.setattr(assets, 'installed_commit', lambda distribution=assets.DISTRIBUTION: '1' * 40)
    else:
        lock['schema'] = 'web-ui-generated/1'
    lock_path.write_text(json.dumps(lock))
    output = tmp_path / 'built'
    with pytest.raises(ValueError):
        assets.build(output, root)
    assert not output.exists()


def test_missing_or_non_git_install_is_rejected():
    with pytest.raises(ValueError, match='not installed'):
        assets.installed_commit('no-such-distribution-for-this-test')


def test_source_output_is_rejected():
    with pytest.raises(ValueError, match='source snapshot'):
        assets.build(ROOT)
