#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
from typing import Dict, Any, Set

from dlpx.config import DEFAULT_ARCHIVE_PATH
from dlpx.utils import ensure_parent


def archive_path(cfg: Dict[str, Any]) -> Path:
    return Path(cfg.get("archive", {}).get("file", str(DEFAULT_ARCHIVE_PATH))).expanduser()


def load_archive(cfg: Dict[str, Any]) -> Set[str]:
    if not cfg.get("archive", {}).get("enabled", True):
        return set()
    p = archive_path(cfg)
    if not p.exists():
        return set()
    try:
        with open(p, "r", encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip()}
    except Exception:
        return set()


def add_archive(cfg: Dict[str, Any], key: str):
    if not cfg.get("archive", {}).get("enabled", True):
        return
    p = archive_path(cfg)
    ensure_parent(p)
    with open(p, "a", encoding="utf-8") as f:
        f.write(key + "\n")
