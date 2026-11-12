from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
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
