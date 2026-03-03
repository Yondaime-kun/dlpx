#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from pathlib import Path
from typing import Dict, Any, List, Optional

from rich.console import Console

from dlpx.utils import deep_merge, ensure_parent

console = Console()

# =========================
# Paths / defaults
# =========================
APP_DIR = Path.home() / ".config" / "dlp-wrapper"
DEFAULT_CONFIG_PATH = APP_DIR / "config.json"
DEFAULT_HISTORY_PATH = APP_DIR / "url_history.txt"
DEFAULT_ARCHIVE_PATH = APP_DIR / "archive.txt"
DEFAULT_LOG_DIR = APP_DIR / "logs"
DEFAULT_REPORT_DIR = APP_DIR / "reports"

DEFAULT_CONFIG: Dict[str, Any] = {
    "engine": {"default": "auto"},
    "history": {
        "enabled": True,
        "file": str(DEFAULT_HISTORY_PATH),
        "max_entries": 1000
    },
    "archive": {
        "enabled": True,
        "file": str(DEFAULT_ARCHIVE_PATH)
    },
    "logging": {
        "enabled": True,
        "dir": str(DEFAULT_LOG_DIR)
    },
    "report": {
        "enabled": True,
        "dir": str(DEFAULT_REPORT_DIR)
    },
    "profiles": {
        "default": {"yt_dlp": {}, "gallery_dl": {}},
        "youtube": {"yt_dlp": {"extra_args": ["--no-playlist"]}},
        "danbooru": {"gallery_dl": {"extra_args": []}}
    },
    "yt_dlp": {
        "cookies": None,
        "cookies_from_browser": None,
        "proxy": None,
        "user_agent": None,
        "referer": None,
        "headers": {},
        "extra_args": [],
        "smart_pick": {
            "prefer_ext": "mp4",
            "prefer_progressive": True,
            "allow_dash_if_needed": True
        }
    },
    "gallery_dl": {
        "cookies": None,
        "cookies_from_browser": None,
        "proxy": None,
        "user_agent": None,
        "referer": None,
        "headers": {},
        "extra_args": [],
        "preview_limit": 100,
        "allowed_ext": ["jpg", "jpeg", "png", "webp", "gif", "mp4", "webm"]
    }
}


# =========================
# Config / profile / overrides
# =========================
def load_config(path: Optional[str]) -> Dict[str, Any]:
    cfg_path = Path(path).expanduser() if path else DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        return DEFAULT_CONFIG
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            user = json.load(f)
        return deep_merge(DEFAULT_CONFIG, user)
    except Exception as e:
        console.print(f"[red]Config load failed:[/red] {e}")
        return DEFAULT_CONFIG


def init_config(path: Optional[str]):
    cfg_path = Path(path).expanduser() if path else DEFAULT_CONFIG_PATH
    ensure_parent(cfg_path)
    if cfg_path.exists():
        console.print(f"[yellow]Config exists:[/yellow] {cfg_path}")
        return
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_CONFIG, f, indent=2)
    console.print(f"[green]Created config:[/green] {cfg_path}")


def apply_profile(cfg: Dict[str, Any], profile_name: Optional[str]) -> Dict[str, Any]:
    if not profile_name:
        return cfg
    profiles = cfg.get("profiles", {})
    prof = profiles.get(profile_name)
    if not isinstance(prof, dict):
        console.print(f"[yellow]Profile '{profile_name}' not found. Ignored.[/yellow]")
        return cfg
    return deep_merge(cfg, prof)


def parse_headers(header_list: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for h in header_list:
        if ":" in h:
            k, v = h.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def apply_cli_overrides(cfg: Dict[str, Any], args) -> Dict[str, Any]:
    c = json.loads(json.dumps(cfg))

    if args.cookie_file:
        c["yt_dlp"]["cookies"] = args.cookie_file
        c["gallery_dl"]["cookies"] = args.cookie_file
    if args.cookies_from_browser:
        c["yt_dlp"]["cookies_from_browser"] = args.cookies_from_browser
        c["gallery_dl"]["cookies_from_browser"] = args.cookies_from_browser
    if args.proxy:
        c["yt_dlp"]["proxy"] = args.proxy
        c["gallery_dl"]["proxy"] = args.proxy
    if args.ua:
        c["yt_dlp"]["user_agent"] = args.ua
        c["gallery_dl"]["user_agent"] = args.ua
    if args.referer:
        c["yt_dlp"]["referer"] = args.referer
        c["gallery_dl"]["referer"] = args.referer

    hdr = parse_headers(args.header or [])
    if hdr:
        c["yt_dlp"]["headers"] = deep_merge(c["yt_dlp"].get("headers", {}), hdr)
        c["gallery_dl"]["headers"] = deep_merge(c["gallery_dl"].get("headers", {}), hdr)

    if args.output_dir:
        c["_runtime_output_dir"] = args.output_dir

    if args.allowed_ext:
        c["gallery_dl"]["allowed_ext"] = [x.strip().lower() for x in args.allowed_ext.split(",") if x.strip()]

    return c
