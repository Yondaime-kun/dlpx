#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
from typing import Dict, Any

from dlpx.config import DEFAULT_HISTORY_PATH
from dlpx.utils import ensure_parent


def setup_readline_history(cfg: Dict[str, Any]):
    hcfg = cfg.get("history", {})
    if not hcfg.get("enabled", True):
        return
    hist_file = Path(hcfg.get("file", str(DEFAULT_HISTORY_PATH))).expanduser()
    ensure_parent(hist_file)
    max_entries = int(hcfg.get("max_entries", 1000))
    try:
        import readline  # type: ignore
        if hist_file.exists():
            readline.read_history_file(str(hist_file))
        readline.set_history_length(max_entries)
    except Exception:
        pass


def save_readline_history(cfg: Dict[str, Any]):
    hcfg = cfg.get("history", {})
    if not hcfg.get("enabled", True):
        return
    hist_file = Path(hcfg.get("file", str(DEFAULT_HISTORY_PATH))).expanduser()
    ensure_parent(hist_file)
    try:
        import readline  # type: ignore
        readline.write_history_file(str(hist_file))
    except Exception:
        pass


def ask_url_with_history(prompt_text: str = "Enter URL") -> str:
    try:
        return input(f"{prompt_text}: ").strip()
    except (EOFError, KeyboardInterrupt):
        return ""
