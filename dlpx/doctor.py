#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from rich.console import Console
from rich.table import Table

from dlpx.utils import run_cmd

console = Console()


def detect_engine(url: str, forced: Optional[str], cfg: Dict[str, Any]) -> str:
    if forced in {"yt-dlp", "gallery-dl"}:
        return forced
    d = cfg.get("engine", {}).get("default", "auto")
    if d in {"yt-dlp", "gallery-dl"}:
        return d
    u = url.lower()
    if any(x in u for x in ["danbooru", "gelbooru", "pixiv", "twitter.com", "x.com", "instagram.com", "reddit.com", "deviantart", "tumblr"]):
        return "gallery-dl"
    return "yt-dlp"


def open_in_1dm(url: str) -> Tuple[bool, str]:
    if shutil.which("am"):
        for pkg in ["idm.internet.download.manager.plus", "idm.internet.download.manager"]:
            r = run_cmd(["am", "start", "-a", "android.intent.action.VIEW", "-d", url, "-p", pkg])
            if r.returncode == 0:
                return True, f"Opened via {pkg}"
        r = run_cmd(["am", "start", "-a", "android.intent.action.VIEW", "-d", url])
        if r.returncode == 0:
            return True, "Opened via chooser"
    if shutil.which("termux-open-url"):
        r = run_cmd(["termux-open-url", url])
        if r.returncode == 0:
            return True, "Opened via termux-open-url"
    return False, "Failed to open URL"


def get_version(cmd: list) -> str:
    try:
        r = run_cmd(cmd, check=True)
        return (r.stdout.strip() or r.stderr.strip()).splitlines()[0]
    except Exception:
        return "N/A"


def doctor(cfg: Dict[str, Any], cookie_override: Optional[str], output_dir: Optional[str]):
    table = Table(title="Doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")

    yt = shutil.which("yt-dlp")
    gd = shutil.which("gallery-dl")
    ff = shutil.which("ffmpeg")
    am = shutil.which("am")
    tou = shutil.which("termux-open-url")

    table.add_row("yt-dlp", "OK" if yt else "MISSING", yt or "-")
    table.add_row("gallery-dl", "OK" if gd else "MISSING", gd or "-")
    table.add_row("ffmpeg", "OK" if ff else "MISSING", ff or "-")
    table.add_row("am", "OK" if am else "MISSING", am or "-")
    table.add_row("termux-open-url", "OK" if tou else "MISSING", tou or "-")

    table.add_row("yt-dlp version", "INFO", get_version(["yt-dlp", "--version"]) if yt else "-")
    table.add_row("gallery-dl version", "INFO", get_version(["gallery-dl", "--version"]) if gd else "-")
    table.add_row("ffmpeg version", "INFO", get_version(["ffmpeg", "-version"]) if ff else "-")

    cookie_file = cookie_override or cfg.get("yt_dlp", {}).get("cookies") or cfg.get("gallery_dl", {}).get("cookies")
    if cookie_file:
        p = Path(cookie_file).expanduser()
        table.add_row("cookies file", "OK" if p.exists() else "MISSING", str(p))
    else:
        table.add_row("cookies file", "INFO", "not set")

    out = Path(output_dir).expanduser() if output_dir else Path.cwd()
    writable = os.access(str(out), os.W_OK)
    table.add_row("output writable", "OK" if writable else "NO", str(out))

    console.print(table)
