"""Repository and default workspace paths."""

from __future__ import annotations

from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent


def repo_root() -> Path:
    for cand in [_PACKAGE_DIR, *_PACKAGE_DIR.parents]:
        if (cand / "pyproject.toml").exists() and (cand / "bakeoff").exists():
            return cand
        if (cand / "bakeoff" / "PROTOCOL.md").exists():
            return cand
    return Path.cwd()


def default_fixtures() -> Path:
    return repo_root() / "bakeoff" / "fixtures" / "v0"


def default_var() -> Path:
    return repo_root() / "var"
