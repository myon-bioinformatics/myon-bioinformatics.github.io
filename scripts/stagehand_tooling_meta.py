"""Emit advisory dual-SDK tooling metadata; never a freshness gate."""
import importlib.metadata, json, os, platform, re, shutil, subprocess
from datetime import datetime, timezone

COMMAND_TIMEOUT = float(os.environ.get("STAGEHAND_TOOL_TIMEOUT", "10"))


def version(command, *args):
    exe = shutil.which(command)
    if not exe:
        return None
    try:
        result = subprocess.run([exe, *args], capture_output=True, text=True, timeout=COMMAND_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode:
        return None
    lines = result.stdout.strip().splitlines()
    return lines[0] if lines else None


def package(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def git(*args):
    try:
        result = subprocess.run(["git", *args], capture_output=True, text=True, timeout=COMMAND_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    sha = result.stdout.strip()
    if result.returncode or not re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", sha):
        return None
    return sha


def collect():
    return {
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
    }


def main(argv=None):
    print(json.dumps(collect(), indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
