"""🚢 Fleet contracts through the parent's shared checks (vendor/fleet_check.py): vendor lock, parent workflow pins and CI job order."""

import unittest
import importlib.util
import tomllib
from pathlib import Path

spec = importlib.util.spec_from_file_location('portfolio_fleet_check', Path(__file__).resolve().parents[1] / 'vendor/fleet_check.py')
fleet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fleet)

ROOT = fleet.repo_root(__file__)
# Local rollout contract; adopted vendor locks are deliberately independent.
PARENT_WORKFLOW_PIN = "43cfe1df924ea96ca44f47a6771c18102c38f7f3"
ACCEPTED = {"vendor/fleet_check.py": "4748595d057e11477e0d62d76c92cb4658ed350c"}   # 📜 script_catalog (parent #385)


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
    assert {'include-group': 'samples'} in groups['browser']                         # Playwright comes with the 🎥 samples group
    assert any(isinstance(item, str) and item.startswith('playwright>=') for item in groups['samples'])


def test_vendor_asset_checks_use_installed_pinned_generator():
    workflow = fleet.workflow_job(ROOT, 'vendor-locked', 'vendor-lock.yml')
    generate = "uv run --locked --only-group pages python scripts/project_pages.py --output"   # the one pyproject pin
    assert "activate-environment: true" in workflow
    assert "requirements" not in workflow and "pip install" not in workflow
    assert workflow.count(generate) == 2
    assert "python -S scripts/project_pages.py" not in workflow
    assert 'diff -r "$RUNNER_TEMP/web-ui-assets" "$RUNNER_TEMP/web-ui-assets-repeat"' in workflow
    assert "python -S .vendor-sync-tools/vendor_sync.py check" in workflow
    assert "python -S .vendor-sync-tools/vendor_sync.py recreate" in workflow


# 🧰 Scripts: 📝 each one describes itself and ⌨️ one that reads sys.argv declares its arguments (argparse /
# cli_args). Read with ast, never run; the portfolio's script catalog reads the same facts.

class ScriptsDescribeThemselves(unittest.TestCase):
    def test_every_script_has_a_description_and_declared_arguments(self):
        fleet.check_scripts(fleet.repo_root(__file__))

    def test_pull_request_ci_stays_quick(self):
        # ⏱ push limited to branches, superseded PR runs cancelled, every job timed (fleet_check.check_ci)
        fleet.check_ci(fleet.repo_root(__file__))
