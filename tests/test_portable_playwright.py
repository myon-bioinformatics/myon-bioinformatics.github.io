"""Portable runner contract tests; no browser install required."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
PY = REPO / "tools/portable_playwright.py"
JS = REPO / "tools/portable_playwright.mjs"

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
                              env={**os.environ, "PYTHON": sys.executable, **(env or {})})

    def test_python_node_equivalent(self):
        a = self.call([sys.executable, "-S", str(PY)])
        b = self.call(["node", str(JS)])
        self.assertEqual(a.returncode, 0, a.stderr)
        self.assertEqual(b.returncode, 0, b.stderr)
        self.assertEqual({k: v for k, v in json.loads(a.stdout).items() if k != 'browser'},
                         {k: v for k, v in json.loads(b.stdout).items() if k != 'browser'})

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
