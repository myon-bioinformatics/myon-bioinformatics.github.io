"""Advisory dual-SDK tooling metadata. Portable versions are normalized by gh_identity."""
import importlib.metadata
import json
import os
from datetime import datetime, timezone

import gh_identity


def package(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def collect():
    commands = ("node", "npm", "npx", "git", "gh")
    versions = gh_identity.tool_versions(commands, include_python=True, stdout_only=True,
                                         timeout=float(os.environ.get("STAGEHAND_TOOL_TIMEOUT", "10")))
    try:
        # The advisory record needs only the commit, including commits with an empty subject.
        sha = gh_identity._rm_sha(gh_identity._rev_commit(".", "HEAD"), "HEAD")
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
