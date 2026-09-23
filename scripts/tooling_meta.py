"""Emit advisory dual-SDK tooling metadata; never a freshness gate."""
import importlib.metadata
import json
import platform
import shutil
import subprocess
from datetime import datetime, timezone


def version(command, *args):
    exe = shutil.which(command)
    if not exe:
        return None
    try:
        result = subprocess.run([exe, *args], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    lines = (result.stdout or result.stderr).strip().splitlines()
    return lines[0] if lines else None


def package(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def git(*args):
    try:
        result = subprocess.run(["git", *args], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


print(json.dumps({
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "sha": git("rev-parse", "HEAD"),
    "python": platform.python_version(),
    "python_stagehand": package("stagehand"),
    "pytest": package("pytest"),
    "node": version("node", "--version"),
    "npm": version("npm", "--version"),
    "npx": version("npx", "--version"),
    "git": version("git", "--version"),
    "gh": version("gh", "--version"),
}, indent=2))
