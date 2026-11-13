"""🧰 Tooling: vendor lock and loader, parent workflow pins, callable entrypoints, the generated PySaiyanWeBoo assets and the repos API builder."""

import hashlib
import importlib.util
import io
import json
import re
import shutil
import sys
import unittest
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


# ═══ 🔒 vendor lock ═══════════════════════════════════════════════════════════════════════════════════════

def test_vendor_lock_matches_checked_in_bytes() -> None:
    lock = json.loads((ROOT / "vendor.lock.json").read_text(encoding="utf-8"))
    assert lock["schema"] == "vendor-lock/1"
    for entry in lock["files"]:
        assert re.fullmatch(r"[0-9a-f]{40}", entry["ref"]), entry["destination"]
        assert entry["ref"] == entry["commit"], entry["destination"]
        data = (ROOT / entry["destination"]).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        assert blob == entry["blob_sha"], entry["destination"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["destination"]


def test_root_vendor_lock_agrees_with_html_import_lock() -> None:
    root_lock = json.loads((ROOT / "vendor.lock.json").read_text(encoding="utf-8"))
    html_lock = json.loads((ROOT / "tools/html-import/vendor.lock.json").read_text(encoding="utf-8"))
    assert html_lock["schema"] == "html-import-vendor/1"

    root_by_path = {entry["destination"]: entry for entry in root_lock["files"]}
    html_by_path = {entry["path"]: entry for entry in html_lock["sources"]}

    assert set(root_by_path) == set(html_by_path)
    for path in root_by_path:
        root_entry = root_by_path[path]
        html_entry = html_by_path[path]
        assert root_entry["commit"] == html_entry["commit"], path
        assert root_entry["sha256"] == html_entry["sha256"], path


@pytest.mark.parametrize("major", [24, 25])
@pytest.mark.parametrize("explicit", [False, True])
def test_pinned_web_ui_reports_rejected_node_version(monkeypatch, major, explicit):
    import pysaiyanweboo as ui  # the pinned PySaiyanWeBoo from requirements-pages.txt
    launcher = ui._node_launch_module()
    message = f"node_launch: Node must be 26 or newer (found {major})"
    if explicit:
        error = launcher.NodeNotFoundError(message)
        node = "node-test"
    else:
        error = launcher.NodeNotFoundError("node executable not found")
        node = None
        monkeypatch.setattr(ui.shutil, "which", lambda _: "node-test")

        def reject(*args):
            raise launcher.NodeNotFoundError(message)

        monkeypatch.setattr(launcher, "_probe_node_once", reject)
    with pytest.raises(RuntimeError, match=rf"Node 26 or newer; found Node {major}"):
        ui._raise_node_not_found(error, node)


# ═══ 📦 vendor loader ═════════════════════════════════════════════════════════════════════════════════════

_scripts = str(ROOT / 'scripts')
sys.path.insert(0, _scripts)
try:
    from vendor_loader import load_module
finally:
    if sys.path and sys.path[0] == _scripts:
        sys.path.pop(0)


def test_load_module_relative_path():
    pillow_min = load_module('test_pillow_min', 'tools/vendor/ironmate/pillow_min.py')
    assert hasattr(pillow_min, 'paeth')


def test_load_module_absolute_path():
    abs_path = ROOT / 'tools/vendor/lab/html_snapshot.py'
    html_snapshot = load_module('test_html_snapshot_abs', abs_path)
    assert hasattr(html_snapshot, 'Parser')


def test_load_module_not_found():
    with pytest.raises(FileNotFoundError) as exc_info:
        load_module('nonexistent', 'tools/vendor/nonexistent.py')
    assert 'Vendor module file not found' in str(exc_info.value)


def test_lab_shared_ui_import_does_not_mutate_sys_path():
    import importlib.util

    before = sys.path.copy()
    path = ROOT / 'scripts' / 'lab_shared_ui.py'
    spec = importlib.util.spec_from_file_location('lab_shared_ui_path_test', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert sys.path == before


# ═══ 📍 parent workflow pins ══════════════════════════════════════════════════════════════════════════════
# Local rollout contract; adopted vendor locks are deliberately independent.

PARENT = "myon-bioinformatics/myon-bioinformatics"
PARENT_WORKFLOW_PIN = "9e3da7ae1846e9604ebc24bb5178f7de094a4e77"


def test_parent_workflow_references_use_reviewed_rollout_commit():
    pins = []
    for path in sorted((ROOT / ".github/workflows").glob("*")):
        if path.suffix not in (".yml", ".yaml"):
            continue
        text = path.read_text(encoding="utf-8")
        # Capture mutable and shortened references too, rather than ignoring them.
        pins.extend(re.findall(r"uses:\s*['\"]?" + re.escape(PARENT) + r"/[^\s@'\"]+@([^\s'\"]+)", text))
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if re.fullmatch(r"\s+repository:\s*['\"]?" + re.escape(PARENT) + r"['\"]?\s*", line):
                refs = [re.fullmatch(r"\s+ref:\s*['\"]?([^\s'\"]+)['\"]?\s*", item) for item in lines[i + 1:i + 12]]
                if not any(re.fullmatch(r"\s+path:\s*['\"]?\.vendor-sync-tools['\"]?\s*", item) for item in lines[i + 1:i + 12]):
                    pins.append(next((m.group(1) for m in refs if m), None))
    assert pins, "shared parent references must remain observable"
    assert set(pins) == {PARENT_WORKFLOW_PIN}, pins


def test_browser_lane_installs_locked_python_capture_dependencies():
    import tomllib

    workflow = (ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8')
    browser = workflow.split('\n  browser:', 1)[1].split('\n  failure-identity:', 1)[0]
    install = 'uv sync --locked --only-group browser'
    assert install in browser
    assert browser.index(install) < browser.index('npx playwright test')
    assert 'activate-environment: true' in browser
    groups = tomllib.loads((ROOT / 'pyproject.toml').read_text())['dependency-groups']
    assert any(isinstance(item, str) and item.startswith('playwright>=') for item in groups['browser'])
    assert 'scripts/capture_portfolio_evidence.py' in (ROOT / 'tests/capture-evidence.spec.js').read_text()


def test_vendor_asset_checks_use_installed_pinned_generator():
    workflow = (ROOT / ".github/workflows/vendor-lock.yml").read_text(encoding="utf-8")
    install = "uv pip install -r requirements-pages.txt"
    generate = "python scripts/build_web_ui_assets.py --output"
    assert "activate-environment: true" in workflow
    assert workflow.index(install) < workflow.index(generate)
    assert workflow.count(generate) == 2
    assert "python -S scripts/build_web_ui_assets.py" not in workflow
    assert 'diff -r "$RUNNER_TEMP/web-ui-assets" "$RUNNER_TEMP/web-ui-assets-repeat"' in workflow
    assert "python -S .vendor-sync-tools/vendor_sync.py check" in workflow
    assert "python -S .vendor-sync-tools/vendor_sync.py recreate" in workflow


# ═══ 📞 callable entrypoints ══════════════════════════════════════════════════════════════════════════════
# Imported entry points accept argv without consuming the caller's CLI.

PARSERS = [
    'scripts/build_web_ui_assets.py',
    'scripts/capture_portfolio_evidence.py',
    'scripts/generate_apng.py',
    'scripts/import_lab_pages.py',
    'scripts/probe_niconico_live.py',
    'scripts/record_demo.py',
    'tools/build_repos_api.py',
]


def load(path):
    spec = importlib.util.spec_from_file_location('entrypoint_under_test', ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('path', PARSERS)
def test_import_then_named_main_uses_explicit_arguments(path, monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['host', '--invalid-host-argument'])
    module = load(path)
    assert not capsys.readouterr().out
    with pytest.raises(SystemExit) as result:
        getattr(module, 'main')(['--help'])
    assert result.value.code == 0
    assert 'usage:' in capsys.readouterr().out


def test_tooling_metadata_import_is_quiet_and_main_is_callable(monkeypatch, capsys):
    module = load('scripts/myon_bioinformatics_github_io_tooling_meta.py')
    assert not capsys.readouterr().out
    monkeypatch.setattr(module, 'collect', lambda: {'sha': 'verified'})
    getattr(module, 'main')([])
    assert '"sha": "verified"' in capsys.readouterr().out


# ═══ 🐉 generated PySaiyanWeBoo assets ════════════════════════════════════════════════════════════════════

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
        assert hashlib.sha256(data).hexdigest() == {**lock['outputs'], **lock['pages']}[name]   # assets and the demo pages
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
    shutil.copyfile(ROOT / 'scripts/portfolio_nav.py', root / 'scripts/portfolio_nav.py')   # the demos get the way back
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


# ═══ ⏱️ repos API timeout ════════════════════════════════════════════════════════════════════════════════
# fetch-guard: GitHub API reads in tools/build_repos_api.py always pass a timeout.

spec_build_repos_api_timeout = importlib.util.spec_from_file_location("build_repos_api", ROOT / "tools" / "build_repos_api.py")
api = importlib.util.module_from_spec(spec_build_repos_api_timeout)
spec_build_repos_api_timeout.loader.exec_module(api)


def test_every_api_read_has_a_timeout(monkeypatch):
    seen = []

    def fake_urlopen(request, timeout=None):
        seen.append(timeout)
        if request.full_url.endswith("/readme"):
            raise urllib.error.HTTPError(request.full_url, 404, "nf", {}, io.BytesIO(b""))
        return io.BytesIO(json.dumps([]).encode())

    monkeypatch.setattr(api.urllib.request, "urlopen", fake_urlopen)
    assert api.fetch_all_repos("o") == []
    assert api.fetch_readme("o", "r") == (None, None)
    assert seen == [api.TIMEOUT_SECONDS, api.TIMEOUT_SECONDS] and api.TIMEOUT_SECONDS > 0


# ═══ 🐍 repos API python selection ════════════════════════════════════════════════════════════════════════
# Static guard: keep catalog refresh on provider-latest managed Python 3.

WORKFLOW = ROOT / ".github/workflows/repos-api.yml"


def check_latest_python_setup(workflow):
    # Isolate YAML step blocks so a later step's env cannot satisfy this guard.
    steps = re.split(r"(?m)^      - ", workflow)[1:]
    setups = [step for step in steps if step.startswith("uses: astral-sh/setup-uv@")]
    assert len(setups) == 1, "exactly one setup-uv step is required"
    setup = setups[0]
    assert re.search(r'(?m)^          python-version: "3"$', setup), "preserve latest Python 3"
    assert re.search(r"(?m)^        env:\n          UV_PYTHON_PREFERENCE: only-managed$", setup), (
        "managed-only selection must apply while setup-uv creates the venv"
    )
    assert re.search(r"(?m)^          activate-environment: true$", setup), "activate plain Python"
    consumer = next(step for step in steps if "python tools/build_repos_api.py" in step)
    assert steps.index(setup) < steps.index(consumer), "set up Python before catalog refresh"


class ReposApiPythonSelectionTests(unittest.TestCase):
    def test_latest_managed_python_is_selected_before_catalog_refresh(self):
        check_latest_python_setup(WORKFLOW.read_text(encoding="utf-8"))

    def test_guard_rejects_fixed_system_or_late_selection(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        setup_env = "        env:\n          UV_PYTHON_PREFERENCE: only-managed\n"
        mutations = {
            "fixed minor": workflow.replace('python-version: "3"', 'python-version: "3.15"'),
            "runner default": workflow.replace(setup_env, ""),
            "preference too late": workflow.replace(setup_env, "").replace(
                "          GITHUB_TOKEN:",
                "          UV_PYTHON_PREFERENCE: only-managed\n          GITHUB_TOKEN:",
            ),
            "inactive venv": workflow.replace("activate-environment: true", "activate-environment: false"),
        }
        steps = re.split(r"(?m)(?=^      - )", workflow)
        setup_index = next(i for i, step in enumerate(steps) if "uses: astral-sh/setup-uv@" in step)
        setup = steps.pop(setup_index)
        steps.append(setup)
        mutations["setup too late"] = "".join(steps)
        for name, mutation in mutations.items():
            with self.subTest(name=name), self.assertRaises(AssertionError):
                check_latest_python_setup(mutation)


if __name__ == "__main__":
    unittest.main()
