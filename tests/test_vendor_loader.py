from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from vendor_loader import load_module


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
