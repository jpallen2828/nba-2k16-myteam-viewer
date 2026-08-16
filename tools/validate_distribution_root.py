#!/usr/bin/env python3
"""Validate the distribution-only outer directory without deleting anything."""

from __future__ import annotations

import argparse
import ctypes
from pathlib import Path


ALLOWED_DISTRIBUTABLES = frozenset(
    {
        "NBA 2K16 MyTEAM Viewer.exe",
        "NBA 2K16 MyTEAM Viewer.zip",
        "NBA 2K16 Card Studio.exe",
        "NBA 2K16 Card Studio.zip",
        "Diagnose NBA 2K16 Install.exe",
    }
)
INTERNAL_PROJECT_DIRECTORY = "_Project"
FILE_ATTRIBUTE_HIDDEN = 0x2


def _is_hidden(path: Path) -> bool:
    if not path.exists():
        return False
    if path.name.startswith("."):
        return True
    if hasattr(ctypes, "windll"):
        attributes = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        return attributes != -1 and bool(attributes & FILE_ATTRIBUTE_HIDDEN)
    return False


def distribution_root_problems(
    distribution_root: Path,
    *,
    require_all: bool = False,
    require_project_hidden: bool = False,
) -> list[str]:
    """Return actionable policy violations; never mutate the directory."""
    root = distribution_root.resolve()
    if not root.is_dir():
        return [f"Distribution root does not exist: {root}"]

    problems: list[str] = []
    present_distributables: set[str] = set()
    for child in root.iterdir():
        if child.name in ALLOWED_DISTRIBUTABLES:
            if child.is_file():
                present_distributables.add(child.name)
            else:
                problems.append(f"Approved distributable name is not a file: {child}")
            continue
        if child.name == INTERNAL_PROJECT_DIRECTORY and child.is_dir():
            continue
        problems.append(f"Unexpected outer-root item: {child}")

    if require_all:
        for name in sorted(ALLOWED_DISTRIBUTABLES - present_distributables):
            problems.append(f"Missing required distributable: {root / name}")

    project = root / INTERNAL_PROJECT_DIRECTORY
    if not project.is_dir():
        problems.append(f"Missing internal development directory: {project}")
    elif require_project_hidden and not _is_hidden(project):
        problems.append(f"Internal development directory is not Hidden: {project}")
    return problems


def validate_distribution_root(
    distribution_root: Path,
    *,
    require_all: bool = False,
    require_project_hidden: bool = False,
) -> None:
    problems = distribution_root_problems(
        distribution_root,
        require_all=require_all,
        require_project_hidden=require_project_hidden,
    )
    if problems:
        details = "\n".join(f"- {problem}" for problem in problems)
        raise RuntimeError(
            "Distribution-root cleanliness validation failed. No unexpected item was deleted.\n"
            f"{details}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("distribution_root", type=Path)
    parser.add_argument("--require-all", action="store_true")
    parser.add_argument("--require-project-hidden", action="store_true")
    args = parser.parse_args()
    validate_distribution_root(
        args.distribution_root,
        require_all=args.require_all,
        require_project_hidden=args.require_project_hidden,
    )
    print(f"Distribution root is clean: {args.distribution_root.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
