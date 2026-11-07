"""Local rollout contract; adopted vendor locks are deliberately independent."""
import re
from pathlib import Path

PARENT = "myon-bioinformatics/myon-bioinformatics"
PARENT_WORKFLOW_PIN = "9e3da7ae1846e9604ebc24bb5178f7de094a4e77"
ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".github/workflows").is_dir())


def test_parent_workflow_references_use_reviewed_rollout_commit():
    pins = []
    for path in sorted((ROOT / ".github/workflows").glob("*")):
        if path.suffix not in (".yml", ".yaml"):
            continue
        text = path.read_text(encoding="utf-8")
        # Capture mutable and shortened references too, rather than ignoring them.
        pins.extend(re.findall(r"uses:\s*['\"]?" + re.escape(PARENT) + r"/[^\s@'\"]+@([^\s'\"]+)", text))
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if re.fullmatch(r"\s+repository:\s*['\"]?" + re.escape(PARENT) + r"['\"]?\s*", line):
                refs = [re.fullmatch(r"\s+ref:\s*['\"]?([^\s'\"]+)['\"]?\s*", item) for item in lines[i + 1:i + 12]]
                pins.append(next((m.group(1) for m in refs if m), None))
    assert pins, "shared parent references must remain observable"
    assert set(pins) == {PARENT_WORKFLOW_PIN}, pins


def test_browser_lane_installs_locked_python_capture_dependencies():
    import tomllib

    workflow = (ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8')
    browser = workflow.split('\n  browser:', 1)[1].split('\n  failure-identity:', 1)[0]
    install = 'uv sync --locked --only-group browser'
    assert install in browser
    assert browser.index(install) < browser.index('npx playwright test')
    assert 'activate-environment: true' in browser
    groups = tomllib.loads((ROOT / 'pyproject.toml').read_text())['dependency-groups']
    assert any(isinstance(item, str) and item.startswith('playwright>=') for item in groups['browser'])
    assert 'scripts/capture_portfolio_evidence.py' in (ROOT / 'tests/capture-evidence.spec.js').read_text()
