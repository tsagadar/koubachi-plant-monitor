#!/usr/bin/env python3
"""Bump version, run checks, commit, tag, and push.

Usage:
    uv run scripts/release.py patch
    uv run scripts/release.py minor
    uv run scripts/release.py major
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

MANIFEST = Path("custom_components/koubachi/manifest.json")
REMOTE = "origin"


def bump(version: str, part: str) -> str:
    major, minor, patch = map(int, version.split("."))
    match part:
        case "major":
            return f"{major + 1}.0.0"
        case "minor":
            return f"{major}.{minor + 1}.0"
        case "patch":
            return f"{major}.{minor}.{patch + 1}"


def run(*cmd: str) -> None:
    result = subprocess.run(list(cmd))
    if result.returncode != 0:
        sys.exit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("part", choices=["major", "minor", "patch"], nargs="?", default="minor")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text())
    old_version = manifest["version"]
    new_version = bump(old_version, args.part)

    print(f"Bumping {old_version} → {new_version}")

    manifest["version"] = new_version
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")

    run("ruff", "check", "custom_components/")
    run("ruff", "format", "--check", "custom_components/")

    run("git", "add", str(MANIFEST))
    run("git", "commit", "-m", f"Bump version to {new_version}")
    run("git", "tag", f"v{new_version}")
    run("git", "push", REMOTE, "main")
    run("git", "push", REMOTE, f"v{new_version}")

    print(f"Released v{new_version}")


if __name__ == "__main__":
    main()
