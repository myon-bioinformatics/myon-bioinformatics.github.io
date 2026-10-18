"""fetch-guard: GitHub API reads in tools/build_repos_api.py always pass a timeout."""
import importlib.util
import io
import json
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_repos_api", ROOT / "tools" / "build_repos_api.py")
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


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
