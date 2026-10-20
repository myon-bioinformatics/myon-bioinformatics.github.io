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
    web_ui = load_module('test_web_ui', 'tools/vendor/web-ui/web_ui.py')
    assert hasattr(web_ui, 'render_document')
    assert hasattr(web_ui, 'adopt_document')


def test_load_module_absolute_path():
    abs_path = ROOT / 'tools/vendor/web-ui/web_ui.py'
    web_ui = load_module('test_web_ui_abs', abs_path)
    assert hasattr(web_ui, 'render_document')


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
