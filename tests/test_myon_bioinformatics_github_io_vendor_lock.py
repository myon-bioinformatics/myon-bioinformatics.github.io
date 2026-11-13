import hashlib, importlib.util, json, re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


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
