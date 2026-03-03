#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from rich.console import Console
from rich.table import Table

from dlpx.utils import (
    GalleryItem, run_cmd, run_live, shell_join, sanitize_filename,
)

console = Console()


def ensure_gallery():
    if not shutil.which("gallery-dl"):
        raise RuntimeError("gallery-dl not found")


def gallery_base(cfg: Dict[str, Any]) -> List[str]:
    g = cfg.get("gallery_dl", {})
    cmd = ["gallery-dl"]
    if g.get("cookies"):
        cmd += ["--cookies", str(g["cookies"])]
    if g.get("cookies_from_browser"):
        cmd += ["--cookies-from-browser", str(g["cookies_from_browser"])]
    if g.get("proxy"):
        cmd += ["--proxy", str(g["proxy"])]
    if g.get("user_agent"):
        cmd += ["--user-agent", str(g["user_agent"])]
    if g.get("referer"):
        cmd += ["-o", f"extractor.headers.Referer={g['referer']}"]
    if isinstance(g.get("headers"), dict):
        for k, v in g["headers"].items():
            cmd += ["-o", f"extractor.headers.{k}={v}"]
    if isinstance(g.get("extra_args"), list):
        cmd += [str(x) for x in g["extra_args"]]
    return cmd


def gallery_get_urls(url: str, cfg: Dict[str, Any]) -> List[str]:
    ensure_gallery()
    cmd = gallery_base(cfg) + ["--get-urls", url]
    r = run_cmd(cmd, check=True)
    urls: List[str] = []
    seen = set()
    for line in r.stdout.splitlines():
        s = line.strip()
        if s.startswith(("http://", "https://")) and s not in seen:
            seen.add(s)
            urls.append(s)
    return urls


def guess_name_ext_from_url(u: str, idx: int) -> Tuple[str, str]:
    base = u.split("?", 1)[0].rstrip("/")
    tail = base.rsplit("/", 1)[-1] if "/" in base else base
    if "." in tail:
        name, ext = tail.rsplit(".", 1)
        ext = ext.lower()
    else:
        name, ext = f"item_{idx}", ""
    return sanitize_filename(name or f"item_{idx}"), ext


def gallery_fetch_items(url: str, cfg: Dict[str, Any]) -> List[GalleryItem]:
    links = gallery_get_urls(url, cfg)
    allowed = {x.lower() for x in cfg.get("gallery_dl", {}).get("allowed_ext", [])}
    items: List[GalleryItem] = []
    idx = 1
    for u in links:
        name, ext = guess_name_ext_from_url(u, idx)
        if allowed and ext and ext.lower() not in allowed:
            continue
        items.append(GalleryItem(idx, u, name, ext, "-", "-"))
        idx += 1
    return items


def gallery_table(items: List[GalleryItem], title: str):
    t = Table(title=title)
    t.add_column("#")
    t.add_column("Filename")
    t.add_column("Ext")
    t.add_column("URL", overflow="fold")
    for it in items:
        t.add_row(str(it.index), it.filename, it.extension or "-", it.url)
    console.print(t)


def gallery_list_keys(url: str, cfg: Dict[str, Any]):
    cmd = gallery_base(cfg) + ["-K", url]
    console.print(shell_join(cmd))
    run_live(cmd)


def gallery_download_cmd(url: str, cfg: Dict[str, Any], directory: Optional[str]) -> List[str]:
    cmd = gallery_base(cfg)
    out_dir = directory or cfg.get("_runtime_output_dir")
    if out_dir:
        cmd += ["-D", str(out_dir)]
    cmd += [url]
    return cmd
