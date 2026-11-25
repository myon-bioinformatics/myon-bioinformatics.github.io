"""Reversible Markdown transport and content-addressed HTML build cache.

Base64 is transport, not compression. Markdown bytes remain canonical.
The HTML cache key includes converter identity; never cache by Markdown SHA alone.
"""
import base64
import hashlib


def encode_markdown(raw: bytes) -> str:
    """Encode exact Markdown bytes; preserve CRLF, Unicode and trailing newline."""
    return base64.b64encode(raw).decode("ascii")


def decode_markdown(encoded: str, expected_sha256: str | None = None) -> bytes:
    """Reject malformed Base64 and optionally verify source provenance."""
    raw = base64.b64decode(encoded, validate=True)
    if expected_sha256 is not None and hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Markdown SHA-256 mismatch")
    return raw


def cache_key(raw: bytes, converter_id: str) -> str:
    """Key HTML by source bytes AND pinned renderer version/options."""
    if not converter_id:
        raise ValueError("converter_id must identify renderer version and options")
    digest = hashlib.sha256(raw).hexdigest()
    return hashlib.sha256((digest + "\\0" + converter_id).encode("utf-8")).hexdigest()


def render_cached(raw: bytes, converter, converter_id: str, cache: dict[str, str]) -> str:
    """Reuse HTML when the source and renderer identity match.

    Cache is an explicit caller-owned mapping; no hidden disk writes.
    """
    key = cache_key(raw, converter_id)
    if key not in cache:
        cache[key] = converter(raw.decode("utf-8"))
    return cache[key]
