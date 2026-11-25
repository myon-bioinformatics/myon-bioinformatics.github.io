"""Markdown Base64 transport and HTML render-cache contract (stdlib only)."""
import base64
import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("markdown_transport", ROOT / "scripts/markdown_transport.py")
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)


@pytest.mark.parametrize("raw", [b"", b"# title\\r\\n", "# 日本語 😀\\n".encode(), b"\\x00\\xff\\x01"])
def test_base64_is_byte_exact(raw):
    assert transport.decode_markdown(transport.encode_markdown(raw), hashlib.sha256(raw).hexdigest()) == raw


def test_rejects_corruption():
    with pytest.raises(ValueError):
        transport.decode_markdown(transport.encode_markdown(b"first"), hashlib.sha256(b"second").hexdigest())
    with pytest.raises(ValueError):
        transport.decode_markdown("%%%invalid")


def test_html_rendered_once_until_source_or_renderer_changes():
    calls = []
    def renderer(source):
        calls.append(source)
        return "<p>" + source + "</p>"
    cache = {}
    source = b"# Weekly"
    encoded = transport.encode_markdown(source)
    for _ in range(3):
        assert transport.render_cached(transport.decode_markdown(encoded), renderer, "markdown@rev1:default", cache) == "<p># Weekly</p>"
    assert len(calls) == 1
    transport.render_cached(source, renderer, "markdown@rev2:default", cache)
    transport.render_cached(b"# Next", renderer, "markdown@rev2:default", cache)
    assert len(calls) == 3


def test_empty_converter_id_rejected():
    with pytest.raises(ValueError):
        transport.cache_key(b"hi", "")
