import hashlib, importlib.util, json, shutil
from pathlib import Path

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
    shutil.copyfile(ROOT / 'requirements-pages.txt', root / 'requirements-pages.txt')
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


def test_dependency_pins_agree():
    import tomllib
    project = tomllib.loads((ROOT / 'pyproject.toml').read_text())
    assert project['tool']['uv']['sources']['pysaiyanweboo']['rev'] == assets.pinned_commit()


def test_explicit_main_ignores_process_arguments(tmp_path, monkeypatch):
    import sys
    monkeypatch.setattr(sys, 'argv', ['host', '--unrelated-host-option'])
    assets.main(['--output', str(tmp_path)])
    assert (tmp_path / assets.ASSET_BASE / 'generated.lock.json').is_file()


@pytest.mark.parametrize('flags', [[], ['--unknown']])
def test_invalid_main_arguments_do_not_write(flags, monkeypatch):
    monkeypatch.setattr(assets, 'build', lambda *a: pytest.fail('unexpected build'))
    monkeypatch.setattr(assets, 'refresh_lock', lambda *a: pytest.fail('unexpected refresh'))
    with pytest.raises(SystemExit) as error:
        assets.main(flags)
    assert error.value.code == 2


def test_refresh_and_cli_output_are_reproducible(tmp_path):
    import subprocess
    import sys
    root = tmp_path / 'source'
    (root / 'scripts').mkdir(parents=True)
    shutil.copyfile(ROOT / 'requirements-pages.txt', root / 'requirements-pages.txt')
    shutil.copyfile(ROOT / 'scripts/build_web_ui_assets.py', root / 'scripts/build_web_ui_assets.py')
    output = tmp_path / 'cli-output'
    result = subprocess.run([sys.executable, str(root / 'scripts/build_web_ui_assets.py'),
                             '--refresh-lock', '--output', str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == json.loads((ROOT / 'web-ui-assets.lock.json').read_text())
    assets.build(tmp_path / 'function-output', root)
    for name, data in assets.generate(root).items():
        assert (root / name).read_bytes() == (output / name).read_bytes() == data
        assert (tmp_path / 'function-output' / name).read_bytes() == data
    # The old CLI without refresh uses the same validated generation path.
    result = subprocess.run([sys.executable, str(root / 'scripts/build_web_ui_assets.py'),
                             '--output', str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('failure', ['commit', 'render'])
def test_failed_refresh_preserves_previous_snapshot(tmp_path, monkeypatch, failure):
    root = tmp_path / 'source'
    shutil.copytree(ROOT / 'tools/vendor/web-ui', root / 'tools/vendor/web-ui')
    for name in ['requirements-pages.txt', 'web-ui-assets.lock.json']:
        shutil.copyfile(ROOT / name, root / name)
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    if failure == 'commit':
        monkeypatch.setattr(assets, 'installed_commit', lambda: '0' * 40)
    else:
        def broken_render(ui):
            raise ValueError('render failure')
        monkeypatch.setattr(assets, 'render', broken_render)
    with pytest.raises(ValueError):
        assets.refresh_lock(root)
    assert {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()} == before


def test_invalid_output_does_not_refresh(monkeypatch):
    monkeypatch.setattr(assets, 'refresh_lock', lambda: pytest.fail('unexpected refresh'))
    with pytest.raises(ValueError, match='source snapshot'):
        assets.main(['--refresh-lock', '--output', str(ROOT)])
