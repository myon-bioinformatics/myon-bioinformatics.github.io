"""🧰 Tooling: the module loader, callable entrypoints, the generated PySaiyanWeBoo assets and the repos API builder (fleet contracts: test_fleet.py)."""

import hashlib
import importlib.util
import io
import json
import re
import shutil
import subprocess
import sys
import unittest
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


# ═══ 🟢 Node version message ═══════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("major", [24, 25])
@pytest.mark.parametrize("explicit", [False, True])
def test_pinned_web_ui_reports_rejected_node_version(monkeypatch, major, explicit):
    import pysaiyanweboo as ui  # the pinned PySaiyanWeBoo (pyproject.toml pages group)
    launcher = ui._njs_launch_module()
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


# ═══ 📦 module loader ═════════════════════════════════════════════════════════════════════════════════════

# One bootstrap: the site builder is loaded by path; every other repository file goes through its load_module().
spec = importlib.util.spec_from_file_location('build_assets', ROOT / 'scripts/project_pages.py')
assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assets)
load_module = assets.load_module


def test_load_module_relative_path():
    pillow_min = load_module('test_pillow_min', 'vendor/pillow_min.py')
    assert hasattr(pillow_min, 'paeth')


def test_load_module_absolute_path():
    abs_path = ROOT / 'tools/vendor/lab/html_snapshot.py'
    html_snapshot = load_module('test_html_snapshot_abs', abs_path)
    assert hasattr(html_snapshot, 'Parser')


def test_load_module_not_found():
    with pytest.raises(FileNotFoundError) as exc_info:
        load_module('nonexistent', 'tools/vendor/nonexistent.py')
    assert 'Vendor module file not found' in str(exc_info.value)


def test_mcp_lab_adapter_does_not_mutate_sys_path():
    import importlib.util

    before = sys.path.copy()
    path = ROOT / '_src' / 'tools' / 'mcp_lab.py'
    spec = importlib.util.spec_from_file_location('mcp_lab_path_test', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert sys.path == before


# ═══ 📞 callable entrypoints ══════════════════════════════════════════════════════════════════════════════
# Imported entry points accept argv without consuming the caller's CLI.

PARSERS = [
    'scripts/project_pages.py',
    'scripts/chat.py',
    'scripts/probe_niconico_live.py',
    'scripts/repos_catalog.py',
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
    module = load('scripts/stagehand_tooling_meta.py')
    assert not capsys.readouterr().out
    monkeypatch.setattr(module, 'collect', lambda: {'sha': 'verified'})
    getattr(module, 'main')([])
    assert '"sha": "verified"' in capsys.readouterr().out


@pytest.mark.parametrize("returncode, stdout, stderr", [
    (1, "private diagnostic", "private diagnostic"),
    (0, "", "private diagnostic"),
])
def test_tooling_metadata_omits_command_diagnostics(monkeypatch, tmp_path, returncode, stdout, stderr):
    module = load("scripts/stagehand_tooling_meta.py")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module.gh_identity.shutil, "which", lambda name: name)
    monkeypatch.setattr(module.gh_identity.subprocess, "run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args, returncode, stdout, stderr))
    result = module.collect()
    assert all(result[key] is None for key in ("sha", "node", "npm", "npx", "git", "gh"))
    assert "private diagnostic" not in json.dumps(result)


@pytest.mark.parametrize(("configured", "expected"), [
    ("0.03", 0.03), ("invalid", 10.0), ("nan", 10.0), ("inf", 10.0), ("0", 10.0),
])
def test_tooling_metadata_uses_one_finite_timeout(monkeypatch, configured, expected):
    module = load("scripts/stagehand_tooling_meta.py")
    monkeypatch.setenv("STAGEHAND_TOOL_TIMEOUT", configured)

    def versions(commands, *, include_python, stdout_only, timeout):
        assert timeout == expected
        return {"python": "3.15.2"}

    def unavailable(*, timeout):
        assert timeout == expected
        raise module.gh_identity.GitInspectionError("private diagnostic")

    monkeypatch.setattr(module.gh_identity, "tool_versions", versions)
    monkeypatch.setattr(module.gh_identity, "checkout_sha", unavailable)
    result = module.collect()
    assert result["sha"] is None and result["python"] == "3.15.2"
    assert "private diagnostic" not in json.dumps(result)


def test_tooling_metadata_reports_detached_head(tmp_path, monkeypatch):
    module = load("scripts/stagehand_tooling_meta.py")
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True)
    subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                    "commit", "-qm", "", "--allow-empty", "--allow-empty-message"], check=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    subprocess.run(["git", "checkout", "-q", "--detach", sha], check=True)
    result = module.collect()
    assert result["sha"] == sha
    assert set(result) == {"sha", "generated_at_utc", "python", "python_stagehand", "pytest",
                           "node", "npm", "npx", "git", "gh"}


def test_tooling_metadata_source_and_license():
    from importlib.metadata import distribution
    import tomllib

    dist = distribution("gh-identity-dev")
    source = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["uv"]["sources"]["gh-identity-dev"]
    installed = json.loads(dist.read_text("direct_url.json"))
    assert installed["url"] == source["git"]
    assert installed["vcs_info"]["commit_id"] == source["rev"]
    license_file, = [f for f in dist.files if f.parts[-2:] == ("licenses", "LICENSE")]
    assert hashlib.sha256(license_file.locate().read_bytes()).hexdigest() == (
        "15f66204c4a6a1ce0c94f0ed4319ff9400f872e85fd32c95f21695c2f231af59")


def test_stagehand_v4_python_surface():
    # The Stagehand v4 reference lane (stagehand-v4-reference.yml) selects this test; the Node side is `npm run stagehand:surface`.
    # Python may expose sync and/or async entry points; this differs intentionally from Node.
    stagehand = pytest.importorskip("stagehand")
    assert hasattr(stagehand, "Stagehand") or hasattr(stagehand, "AsyncStagehand")


# ═══ 🐉 generated PySaiyanWeBoo assets ════════════════════════════════════════════════════════════════════


def test_installed_generator_is_the_pinned_commit():
    lock = json.loads((ROOT / 'web-ui-assets.lock.json').read_text())
    assert lock['schema'] == 'web-ui-generated/2'
    assert assets.installed_commit() == lock['commit'] == assets.pinned_commit()


def test_generated_files_match_the_lock_and_are_not_committed(tmp_path):
    payload = assets.generate()
    lock = json.loads((ROOT / 'web-ui-assets.lock.json').read_text())
    ignored = [line for line in (ROOT / '.gitignore').read_text().splitlines() if line.startswith('tools/')]
    assert set(payload) == set(lock['outputs']) | set(lock['pages'])
    for name, data in payload.items():
        assert not (ROOT / name).exists() or name.startswith(tuple(ignored)), name   # generated at build time, never committed
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
    shutil.copyfile(ROOT / 'pyproject.toml', root / 'pyproject.toml')
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
    lock = tomllib.loads((ROOT / 'uv.lock').read_text())
    [package] = [p for p in lock['package'] if p['name'] == assets.DISTRIBUTION]
    assert package['source']['git'].endswith('#' + assets.pinned_commit())   # uv.lock resolves the one pyproject pin


def test_malformed_pin_is_rejected(tmp_path):
    (tmp_path / 'pyproject.toml').write_text('[tool.uv.sources]\npysaiyanweboo = { git = "https://github.com/myon-bioinformatics/PySaiyanWeBoo", rev = "main" }\n')
    with pytest.raises(ValueError, match='full PySaiyanWeBoo commit pin'):
        assets.pinned_commit(tmp_path)


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
    shutil.copyfile(ROOT / 'pyproject.toml', root / 'pyproject.toml')
    shutil.copyfile(ROOT / 'scripts/project_pages.py', root / 'scripts/project_pages.py')
    (root / '_src/tools').mkdir(parents=True)
    shutil.copyfile(ROOT / '_src/tools/studio_routes.py', root / '_src/tools/studio_routes.py')
    shutil.copyfile(ROOT / 'scripts/front_page.py', root / 'scripts/front_page.py')         # the front page is generated too
    shutil.copyfile(ROOT / 'scripts/map_tool.py', root / 'scripts/map_tool.py')
    shutil.copyfile(ROOT / 'scripts/world.py', root / 'scripts/world.py')                 # 🌍 the world pages and Parallel Tokyo
    shutil.copyfile(ROOT / 'scripts/chat.py', root / 'scripts/chat.py')                   # 💬 the chat page runs it in Pyodide
    (root / 'docs').mkdir()
    shutil.copyfile(ROOT / 'docs/weekly-view.md', root / 'docs/weekly-view.md')
    (root / 'api').mkdir()
    for name in ('profile.json', 'api/repos.json', 'site.config.json', 'services.json'):                                       # ... from these and projects.json
        shutil.copyfile(ROOT / name, root / name)
    shutil.copyfile(ROOT / 'projects.json', root / 'projects.json')                       # the project cards' curation
    output = tmp_path / 'cli-output'
    result = subprocess.run([sys.executable, str(root / 'scripts/project_pages.py'),
                             '--refresh-lock', '--output', str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == json.loads((ROOT / 'web-ui-assets.lock.json').read_text())
    assets.build(tmp_path / 'function-output', root)
    for name, data in assets.generate(root).items():
        assert not (root / name).exists()                         # refresh rewrites the lock only
        assert (output / name).read_bytes() == data
        assert (tmp_path / 'function-output' / name).read_bytes() == data
    # The old CLI without refresh uses the same validated generation path.
    result = subprocess.run([sys.executable, str(root / 'scripts/project_pages.py'),
                             '--output', str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('failure', ['commit', 'render'])
def test_failed_refresh_preserves_previous_snapshot(tmp_path, monkeypatch, failure):
    root = tmp_path / 'source'
    shutil.copytree(ROOT / 'tools/vendor/web-ui', root / 'tools/vendor/web-ui')
    for name in ['pyproject.toml', 'web-ui-assets.lock.json']:
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
# fetch-guard: GitHub API reads in scripts/repos_catalog.py always pass a timeout.

spec_repos_catalog_timeout = importlib.util.spec_from_file_location("repos_catalog", ROOT / "scripts" / "repos_catalog.py")
api = importlib.util.module_from_spec(spec_repos_catalog_timeout)
spec_repos_catalog_timeout.loader.exec_module(api)


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
    consumer = next(step for step in steps if "python scripts/repos_catalog.py" in step)
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


def test_copy_source_copies_only_public_files_verbatim(tmp_path):
    root = tmp_path / 'checkout'
    development = ('AGENTS.md', 'README.md', '.coverage', 'pyproject.toml', 'uv.lock', '.git/HEAD',
                   '.github/workflows/pages.yml', 'tests/test_sample.py', 'scripts/chat.py',
                   '_src/tools/panel.js', 'vendor/pillow_min.py', 'tools/vendor/lab/html_snapshot.py',
                   'docs/weekly-view.md', 'docs/evidence/scratch.gif', 'api/private.json',
                   'assets/brand/.cache/preview.png', 'tools/niconico/__pycache__/sample.pyc')
    for name in (*assets.PUBLIC_SOURCE_FILES, *development):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name, encoding='utf-8')

    output = root / '_site'
    generated = output / 'media/chat/index.json'
    generated.parent.mkdir(parents=True)
    generated.write_text('{}', encoding='utf-8')
    assets.copy_source(output, root)

    copied = {path.relative_to(output).as_posix(): path.read_text(encoding='utf-8')
              for path in output.rglob('*') if path.is_file()}
    expected = {name: name for name in assets.PUBLIC_SOURCE_FILES}
    assert expected.keys().isdisjoint(development)
    assert copied == {**expected, 'media/chat/index.json': '{}'}


def test_copy_source_rejects_a_symlink_in_the_public_list(tmp_path):
    root = tmp_path / 'checkout'
    root.mkdir()
    outside = tmp_path / 'outside'
    outside.write_text('outside the checkout', encoding='utf-8')
    (root / '.nojekyll').symlink_to(outside)
    output = tmp_path / 'public'

    with pytest.raises(ValueError, match=r'regular public file: \.nojekyll'):
        assets.copy_source(output, root)

    assert not output.exists()
