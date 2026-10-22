"""Portable runner contract tests; no browser install required."""
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
PY = REPO / "tools/portable_playwright.py"
JS = REPO / "tools/portable_playwright.mjs"
NODE = shutil.which("node") or "node"

class PortablePlaywrightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "playwright.config.js").write_text("module.exports = {}\n")
        cli = self.root / "node_modules/@playwright/test/cli.js"
        cli.parent.mkdir(parents=True)
        cli.write_text("console.log('1 passed'); console.error('Error: simulated'); process.exit(Number(process.env.FAKE_EXIT || 0));\n")

    def call(self, cmd, *args, env=None):
        return subprocess.run([*cmd, "--root", str(self.root), *args], capture_output=True, text=True,
                              env={**os.environ, "PYTHON": sys.executable, **(env or {})}, cwd=self.root)

    def assert_equivalent(self, *args, dry_run=False):
        argv = ("--node", NODE, *args, *(("--dry-run",) if dry_run else ()))
        runs = [self.call([sys.executable, "-S", str(PY)], *argv),
                self.call(["node", str(JS)], *argv)]
        receipts = []
        for result in runs:
            self.assertEqual(result.returncode, 0, result.stderr)
            receipts.append(json.loads(result.stdout))
        self.assertEqual(receipts[0], receipts[1])
        return receipts[0]

    def test_relative_explicit_browser_receipts(self):
        browser = self.root / "browser cache/chrome"
        browser.parent.mkdir(parents=True)
        browser.write_bytes(b"fake")
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run):
                receipt = self.assert_equivalent("--browser", "browser cache/chrome", dry_run=dry_run)
                self.assertEqual(receipt["browser"], str(browser))

    def test_relative_discovered_browser_receipts(self):
        browser = self.root / "cache/chromium-1194/chrome-linux/chrome"
        browser.parent.mkdir(parents=True)
        browser.write_bytes(b"fake")
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run):
                receipt = self.assert_equivalent("--browser-root", "cache", dry_run=dry_run)
                self.assertEqual(receipt["browser"], str(browser))

    def test_discovery_uses_revision_directory_not_ancestor_name(self):
        older = self.root / "chromium-9999-cache/chromium-1193/chrome-linux/chrome"
        newer = self.root / "cache/chromium-1194/chrome-linux/chrome"
        for file in (older, newer):
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(b"fake")
        receipt = self.assert_equivalent(
            "--browser-root", "chromium-9999-cache", "--browser-root", "cache", dry_run=True)
        self.assertEqual(receipt["browser"], str(newer))

    def test_discovery_skips_invalid_cache_entries(self):
        cache = self.root / "cache"
        cache.mkdir()
        (cache / "chromium-9999").write_bytes(b"not a directory")
        valid = cache / "chromium-1194/chrome-linux/chrome"
        valid.parent.mkdir(parents=True)
        valid.write_bytes(b"fake")
        receipt = self.assert_equivalent("--browser-root", "cache", dry_run=True)
        self.assertEqual(receipt["browser"], str(valid))

    def test_python_node_equivalent(self):
        a = self.call([sys.executable, "-S", str(PY)])
        b = self.call(["node", str(JS)])
        self.assertEqual(a.returncode, 0, a.stderr)
        self.assertEqual(b.returncode, 0, b.stderr)
        self.assertEqual(json.loads(a.stdout), json.loads(b.stdout))

    def test_same_revision_browser_tie_break(self):
        browser_root = self.root / "browsers"
        for name in ("chrome-linux-a", "chrome-linux-A"):
            chrome = browser_root / "chromium-1194" / name / "chrome"
            chrome.parent.mkdir(parents=True)
            chrome.write_bytes(b"fake")
        receipt = self.assert_equivalent("--browser-root", str(browser_root), dry_run=True)
        self.assertTrue(receipt["browser"].endswith("chrome-linux-A/chrome"))

    def test_failure_exit_code(self):
        result = self.call([sys.executable, "-S", str(PY)], env={"FAKE_EXIT": "7"})
        self.assertEqual(result.returncode, 7)
        self.assertEqual(json.loads(result.stdout)["exit_code"], 7)

    def test_filter_and_limit(self):
        result = self.call([sys.executable, "-S", str(PY)], "--match", "passed", "--limit", "1")
        self.assertEqual(json.loads(result.stdout)["lines"], ["1 passed"])

    def test_dry_run(self):
        result = self.call([sys.executable, "-S", str(PY)], "--dry-run")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["cwd"], str(self.root))

if __name__ == "__main__":
    unittest.main()
