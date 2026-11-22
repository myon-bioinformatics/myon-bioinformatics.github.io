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
    import pysaiyanweboo as ui  # the pinned PySaiyanWeBoo from requirements-pages.txt
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


def test_lab_import_does_not_mutate_sys_path():
    import importlib.util

    before = sys.path.copy()
    path = ROOT / 'scripts' / 'lab_import.py'
    spec = importlib.util.spec_from_file_location('lab_import_path_test', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert sys.path == before


# ═══ 📞 callable entrypoints ══════════════════════════════════════════════════════════════════════════════
# Imported entry points accept argv without consuming the caller's CLI.

PARSERS = [
    'scripts/project_pages.py',
    'scripts/lab_import.py',
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
    pin = (ROOT / 'requirements-pages.txt').read_text()
    assert lock['schema'] == 'web-ui-generated/2'
    assert assets.installed_commit() == lock['commit']
    assert f'PySaiyanWeBoo@{lock["commit"]}' in pin


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
    shutil.copyfile(ROOT / 'scripts/project_pages.py', root / 'scripts/project_pages.py')
    shutil.copyfile(ROOT / 'scripts/front_page.py', root / 'scripts/front_page.py')         # the front page is generated too
    shutil.copyfile(ROOT / 'scripts/map_tool.py', root / 'scripts/map_tool.py')
    (root / 'api').mkdir()
    for name in ('profile.json', 'api/repos.json'):                                       # ... from these and projects.json
        shutil.copyfile(ROOT / name, root / name)
    shutil.copyfile(ROOT / 'projects.json', root / 'projects.json')                       # the project pages come from it
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


def test_record_reruns_the_showcase_at_its_commit_with_a_minimal_environment(tmp_path, monkeypatch):
    import subprocess
    checkout = tmp_path / 'tool'
    checkout.mkdir()
    (checkout / 'show.py').write_text('import os, sys\nprint(sorted(os.environ))\nsys.exit(3)\n')
    git = ['git', '-C', str(checkout), '-c', 'user.name=t', '-c', 'user.email=t@example.invalid']
    subprocess.run(['git', 'init', '-q', str(checkout)], check=True)
    subprocess.run(git + ['add', 'show.py'], check=True)
    subprocess.run(git + ['commit', '-q', '-m', 'x'], check=True)
    head = subprocess.run(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    root = tmp_path / 'site'
    root.mkdir()
    entry = {'name': 'Tool', 'desc': 'd', 'url': 'https://github.com/o/Tool',
             'showcase': {'label': 'T', 'repository': 'o/Tool', 'commit': '0' * 40, 'run': {'command': [sys.executable, '-S', 'show.py']}}}
    (root / 'projects.json').write_text(json.dumps([entry]))
    with pytest.raises(ValueError, match='showcase records 0000000'):
        assets.record('Tool', checkout, root)                    # 📌 only the commit the page names
    entry['showcase']['commit'] = head
    (root / 'projects.json').write_text(json.dumps([entry]))
    monkeypatch.setenv('SECRET_LOOKING_NAME', 'value')
    run = assets.record('Tool', checkout, root)['run']
    assert run['exit'] == 3
    assert run['output'] == "['HOME', 'LANG', 'PATH']"            # 🔒 no other variable of this machine
    assert json.loads((root / 'projects.json').read_text())[0]['showcase']['run'] == run


def test_record_catalogs_the_scripts_from_their_own_docstring_and_help(tmp_path):
    tools = tmp_path / 'tools'
    tools.mkdir()
    (tools / 'cli.py').write_text('"""Do one thing.\n\nMore words."""\nimport argparse\n'
                                  'p = argparse.ArgumentParser(prog="cli.py"); p.add_argument("--flag"); p.add_argument("--more", action="store_true")\n'
                                  'p.add_argument("--and-a-rather-long-option-name", metavar="SOMETHING_WIDE"); p.parse_args()\n')
    (tools / 'quiet.py').write_text('import sys\nopen(sys.argv[0] + ".ran", "w")\n')   # no docstring, no argparse: never run
    (tools / 'facts.mjs').write_text('#!/usr/bin/env node\nimport fs from "node:fs";\n\n// Facts without a browser.\n')
    (tools / 'notes.txt').write_text('not a script')
    items = assets.script_catalog(tmp_path, ['tools/*.py', 'tools/*.mjs', 'tools/*.py'])
    assert [i['path'] for i in items] == ['tools/cli.py', 'tools/facts.mjs', 'tools/quiet.py']   # sorted, once each
    cli, facts, quiet = items
    assert (cli['summary'], quiet['summary'], facts['summary']) == ('Do one thing.', '', 'Facts without a browser.')
    assert cli['usage'] == 'usage: cli.py [-h] [--flag FLAG] [--more] [--and-a-rather-long-option-name SOMETHING_WIDE]'  # wrapped
    assert quiet['usage'] == '' and not (tools / 'quiet.py.ran').exists()                    # 🔍 read, never run                        # 📝 the code is the source
    assert facts['usage'] == ''                                                                  # JS is never run


def test_advance_moves_each_showcase_to_the_tip_unless_that_breaks_its_page(tmp_path):
    git = lambda repo, *args: subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()
    def repository(name, files):
        repo = tmp_path / 'o' / name
        repo.mkdir(parents=True)
        git(repo, 'init', '-q')
        commits = []
        for step in files:                                  # one commit per dict: path -> text (None deletes)
            for path, text in step.items():
                (repo / path).unlink() if text is None else (repo / path).write_text(text)
            git(repo, 'add', '-A')
            git(repo, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-m', 'x')
            commits.append(git(repo, 'rev-parse', 'HEAD'))
        return commits
    run = {'command': [sys.executable, '-S', 'show.py'], 'exit': 0, 'output': 'old'}
    moved = repository('Moved', [{'show.py': 'print("v1")', 'icon.png': 'i'}, {'show.py': '"""Show."""\nprint("v2")'}])
    lost = repository('Lost', [{'show.py': 'print(1)', 'icon.png': 'i'}, {'icon.png': None}])
    broke = repository('Broke', [{'show.py': 'print(1)'}, {'show.py': 'raise SystemExit(3)'}])
    same = repository('Same', [{'show.py': 'print(1)'}])
    showcase = lambda repo, commit, **extra: {'label': repo, 'repository': f'o/{repo}', 'commit': commit,
                                               'run': dict(run), **extra}
    projects = [{'name': 'Moved', 'desc': 'd', 'showcase': showcase('Moved', moved[0], icon='icon.png', scripts={'match': ['*.py']})},
                {'name': 'Lost', 'desc': 'd', 'showcase': showcase('Lost', lost[0], icon='icon.png')},
                {'name': 'Broke', 'desc': 'd', 'showcase': showcase('Broke', broke[0])},
                {'name': 'Same', 'desc': 'd', 'showcase': showcase('Same', same[0])},
                {'name': 'Plain', 'desc': 'no showcase'}]
    root = tmp_path / 'site'
    root.mkdir()
    (root / 'projects.json').write_text(json.dumps(projects))
    log = assets.advance(root, remote=str(tmp_path) + '/')
    assert [line.split()[0] for line in log] == ['⏩', '⏸', '⏸', '=']
    assert 'icon.png missing' in log[1] and 'run exit 3' in log[2]
    after = {p['name']: p.get('showcase') for p in json.loads((root / 'projects.json').read_text())}
    assert after['Moved']['commit'] == moved[1] and after['Moved']['run']['output'] == 'v2'
    assert after['Moved']['scripts']['items'] == [{'path': 'show.py', 'summary': 'Show.', 'usage': ''}]
    assert (after['Lost']['commit'], after['Broke']['commit']) == (lost[0], broke[0])      # 📌 kept where the page works
    assert after['Broke']['run']['output'] == 'old' and after['Plain'] is None
