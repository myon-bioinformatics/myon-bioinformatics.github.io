import pytest


def test_stagehand_v4_python_surface():
    # Python may expose sync and/or async entry points; this differs intentionally from Node.
    stagehand = pytest.importorskip("stagehand")
    assert hasattr(stagehand, "Stagehand") or hasattr(stagehand, "AsyncStagehand")
