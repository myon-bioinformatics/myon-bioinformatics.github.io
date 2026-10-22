#!/usr/bin/env python3
"""Portable Playwright runner (Python stdlib only)."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

def browsers(roots):
    """Find Chromium by revision descending, then absolute path ascending."""
    found = set()
    for root in roots:
        for cache in Path(root).glob("chromium-*"):
            revision = re.fullmatch(r"chromium-(\d+)", cache.name)
            if not revision or not cache.is_dir():
                continue
            for sub in cache.glob("chrome-linux*"):
                if not sub.is_dir():
                    continue
                for exe in ("chrome", "chrome.exe"):
                    candidate = sub / exe
                    if candidate.is_file():
                        found.add((int(revision.group(1)), str(candidate.resolve())))
    return [path for _, path in sorted(found, key=lambda pair: (-pair[0], pair[1]))]

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--browser-root", action="append", default=[])
    parser.add_argument("--browser")
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--match", default=r"passed|failed|skipped|^\s+\d+\) |Error:")
    parser.add_argument("--node", default="node")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("specs", nargs="*")
    args = parser.parse_args(argv)
    if args.timeout <= 0 or args.limit < 0:
        parser.error("timeout must be positive and limit nonnegative")
    root = Path(args.root).resolve()
    config = root / "playwright.config.js"
    if not config.is_file():
        parser.error(f"missing {config}")
    if args.browser and not Path(args.browser).is_file():
        parser.error(f"browser not found: {args.browser}")
    browser = str(Path(args.browser).resolve()) if args.browser else next(iter(browsers(args.browser_root or ["/opt/pw-browsers"])), None)
    env = dict(os.environ, PORTABLE_PW_BASE_CONFIG=str(config), PORTABLE_PW_TEST_DIR=str(root / "tests"))
    if browser:
        env["PORTABLE_PW_BROWSER"] = str(Path(browser).resolve())
    else:
        env.pop("PORTABLE_PW_BROWSER", None)
    bridge = Path(__file__).with_name("portable_playwright_config.cjs")
    cmd = [args.node, str(root / "node_modules/@playwright/test/cli.js"), "test", "-c", str(bridge), *args.specs, "--reporter=line"]
    if args.dry_run:
        print(json.dumps({"command": cmd, "browser": browser, "cwd": str(root), "config": str(config)}, ensure_ascii=False))
        return 0
    try:
        result = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True, errors="replace", timeout=args.timeout)
        lines = [line for line in (result.stdout + "\n" + result.stderr).splitlines() if re.search(args.match, line)]
        print(json.dumps({"exit_code": result.returncode, "timed_out": False, "browser": browser, "lines": lines[:args.limit] if args.limit else lines}, ensure_ascii=False))
        return result.returncode if result.returncode >= 0 else 128 - result.returncode
    except subprocess.TimeoutExpired:
        print(json.dumps({"exit_code": 124, "timed_out": True, "browser": browser, "lines": []}))
        return 124
    except OSError as exc:
        print(json.dumps({"exit_code": 127, "timed_out": False, "browser": browser, "lines": [], "error": str(exc)}))
        return 127

if __name__ == "__main__":
    sys.exit(main())
