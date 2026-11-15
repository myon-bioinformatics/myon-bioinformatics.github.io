"""🚢 Fleet contracts through the parent's shared checks (vendor/fleet_check.py): vendor lock, parent workflow pins and CI job order."""

import importlib.util
import tomllib
from pathlib import Path

spec = importlib.util.spec_from_file_location('portfolio_fleet_check', Path(__file__).resolve().parents[1] / 'vendor/fleet_check.py')
fleet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fleet)

ROOT = fleet.repo_root(__file__)
# Local rollout contract; adopted vendor locks are deliberately independent.
PARENT_WORKFLOW_PIN = "9e3da7ae1846e9604ebc24bb5178f7de094a4e77"
ACCEPTED = {"vendor/fleet_check.py": "6c29503cf17eda856766ddfdf4d66a5b0965a8b1"}


def test_vendor_lock_matches_checked_in_bytes_and_accepted_commits():
    rows = fleet.check_lock(ROOT, commits=ACCEPTED)      # the one lock: tools/vendor/ (HTML import, lab) and vendor/ (parent)
    assert {'tools/vendor/lab/html_snapshot.py', 'vendor/pillow_min.py', 'tools/vendor/web-ui/LICENSE'} <= set(rows)


def test_parent_workflow_references_use_reviewed_rollout_commit():
    assert set(fleet.parent_refs(ROOT, skip=(".vendor-sync-tools",))) == {PARENT_WORKFLOW_PIN}


def test_browser_lane_installs_locked_python_playwright():
    browser = fleet.workflow_job(ROOT, 'browser')
    install = 'uv sync --locked --only-group browser'
    assert install in browser
    assert browser.index(install) < browser.index('python -m pytest tests/test_front_page.py')
    assert 'npm ci' not in browser and 'npx ' not in browser            # the front page lane needs no Node
    assert 'activate-environment: true' in browser
    groups = tomllib.loads((ROOT / 'pyproject.toml').read_text())['dependency-groups']
    assert any(isinstance(item, str) and item.startswith('playwright>=') for item in groups['browser'])


def test_vendor_asset_checks_use_installed_pinned_generator():
    workflow = fleet.workflow_job(ROOT, 'vendor-locked', 'vendor-lock.yml')
    install = "uv pip install -r requirements-pages.txt"
    generate = "python scripts/project_pages.py --output"
    assert "activate-environment: true" in workflow
    assert workflow.index(install) < workflow.index(generate)
    assert workflow.count(generate) == 2
    assert "python -S scripts/project_pages.py" not in workflow
    assert 'diff -r "$RUNNER_TEMP/web-ui-assets" "$RUNNER_TEMP/web-ui-assets-repeat"' in workflow
    assert "python -S .vendor-sync-tools/vendor_sync.py check" in workflow
    assert "python -S .vendor-sync-tools/vendor_sync.py recreate" in workflow
