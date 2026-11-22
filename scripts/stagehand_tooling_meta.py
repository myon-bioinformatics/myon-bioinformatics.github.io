"""Advisory dual-SDK tooling metadata. Portable versions are normalized by gh_identity."""
import importlib.metadata
import json
import math
import os
from datetime import datetime, timezone

import gh_identity


def package(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def probe_timeout():
    default = 10.0
    try:
        seconds = float(os.environ.get("STAGEHAND_TOOL_TIMEOUT", default))
    except ValueError:
        return default
    return seconds if math.isfinite(seconds) and seconds > 0 else default


def collect():
    timeout = probe_timeout()
    commands = ("node", "npm", "npx", "git", "gh")
    versions = gh_identity.tool_versions(commands, include_python=True, stdout_only=True,
                                         timeout=timeout)
    try:
        sha = gh_identity.checkout_sha(timeout=timeout)
    except (OSError, ValueError, gh_identity.GitInspectionError):
        sha = None
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sha": sha,
        "python": versions.get("python"),
        "python_stagehand": package("stagehand"),
        "pytest": package("pytest"),
        **{name: versions.get(name) for name in commands},
    }


def main(argv=None):
    print(json.dumps(collect(), indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
