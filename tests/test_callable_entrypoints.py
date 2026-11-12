"""Imported entry points accept argv without consuming the caller's CLI."""
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
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
