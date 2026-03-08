#!/usr/bin/env python3
"""Run ruff (lint + format check) and pytest.

Usage:
    uv run scripts/check.py
"""

import subprocess
import sys


def run(*cmd: str) -> None:
    result = subprocess.run(list(cmd))
    if result.returncode != 0:
        sys.exit(result.returncode)


def main() -> None:
    run("ruff", "check", "custom_components/")
    run("ruff", "format", "--check", "custom_components/")
    run("pytest")


if __name__ == "__main__":
    main()
