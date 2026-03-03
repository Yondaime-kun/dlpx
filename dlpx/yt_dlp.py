#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import shutil
import subprocess
from typing import Dict, Any, List, Optional

from rich.console import Console
from rich.table import Table

from dlpx.utils import (
    MediaFormat, run_cmd, run_live, shell_join, human_size, sanitize_filename,
)

console = Console()


def ensure_yt():
    if not shutil.which("yt-dlp"):
        raise RuntimeError("yt-dlp not found")


def yt_base(cfg: Dict[str, Any]) -> List[str]:
    y = cfg.get("yt_dlp", {})
    cmd = ["yt-dlp"]
    if y.get("cookies"):
        cmd += ["--cookies", str(y["cookies"])]
    if y.get("cookies_from_browser"):
        cmd += ["--cookies-from-browser", str(y["cookies_from_browser"])]
    if y.get("proxy"):
        cmd += ["--proxy", str(y["proxy"])]
    if y.get("user_agent"):
        cmd += ["--user-agent", str(y["user_agent"])]
    if y.get("referer"):
        cmd += ["--referer", str(y["referer"])]
    if isinstance(y.get("headers"), dict):
        for k, v in y["headers"].items():
            cmd += ["--add-header", f"{k}:{v}"]
    if isinstance(y.get("extra_args"), list):
        cmd += [str(x) for x in y["extra_args"]]
    return cmd


def yt_info(url: str, cfg: Dict[str, Any]) -> dict:
    ensure_yt()
    r = run_cmd(yt_base(cfg) + ["-J", "--no-warnings", url], check=True)
    return json.loads(r.stdout)


def yt_parse(info: dict) -> List[MediaFormat]:
    out = []
    for f in info.get("formats", []):
        durl = f.get("url")
        if not durl:
            continue
        vcodec = str(f.get("vcodec", "none"))
        acodec = str(f.get("acodec", "none"))
        is_audio_only = vcodec == "none" and acodec != "none"
        is_progressive = vcodec != "none" and acodec != "none"
        h = int(f.get("height") or 0)
        res = f.get("resolution") or (f"{h}p" if h else ("audio" if is_audio_only else "-"))
        out.append(MediaFormat(
            format_id=str(f.get("format_id", "-")),
            ext=str(f.get("ext", "-")),
            resolution=res,
            height=h,
            fps=str(f.get("fps", "-")),
            vcodec=vcodec,
            acodec=acodec,
            filesize=f.get("filesize") or f.get("filesize_approx"),
            note=str(f.get("format_note", "-")),
            direct_url=durl,
            protocol=str(f.get("protocol", "-")),
            is_progressive=is_progressive,
            is_audio_only=is_audio_only,
            tbr=f.get("tbr"),
        ))
    return out


def yt_filter(formats: List[MediaFormat], show_all=False, audio_only=False) -> List[MediaFormat]:
    fs = formats[:] if show_all else [
        x for x in formats
        if x.protocol not in {"m3u8", "m3u8_native", "http_dash_segments"}
        and ((audio_only and x.is_audio_only) or (not audio_only and x.is_progressive))
    ]
    if not fs:
        fs = formats[:]
    fs.sort(key=lambda x: (0 if x.is_progressive else 1, -(x.height or 0), -(x.filesize or 0), -(x.tbr or 0.0)))
    return fs


def yt_smart_pick(formats: List[MediaFormat], cfg: Dict[str, Any], audio_only=False) -> Optional[MediaFormat]:
    if not formats:
        return None
    sp = cfg.get("yt_dlp", {}).get("smart_pick", {})
    prefer_ext = str(sp.get("prefer_ext", "mp4")).lower()
    prefer_progressive = bool(sp.get("prefer_progressive", True))
    allow_dash = bool(sp.get("allow_dash_if_needed", True))

    candidates = formats[:]
    if audio_only:
        candidates = [f for f in candidates if f.is_audio_only]
    elif prefer_progressive:
        prog = [f for f in candidates if f.is_progressive]
        if prog:
            candidates = prog
        elif not allow_dash:
            return None

    if prefer_ext != "any":
        ext_filtered = [f for f in candidates if f.ext.lower() == prefer_ext]
        if ext_filtered:
            candidates = ext_filtered

    candidates.sort(key=lambda x: (-(x.height or 0), -(x.filesize or 0), -(x.tbr or 0.0)))
    return candidates[0] if candidates else None


def yt_table(formats: List[MediaFormat], title: str):
    t = Table(title=title)
    for c in ["#", "ID", "Ext", "Res", "FPS", "VCodec", "ACodec", "Size", "Proto", "Type", "Note"]:
        t.add_column(c)
    for i, f in enumerate(formats, 1):
        typ = "AV" if f.is_progressive else ("AUDIO" if f.is_audio_only else "VIDEO")
        t.add_row(str(i), f.format_id, f.ext, f.resolution, f.fps, f.vcodec, f.acodec, human_size(f.filesize), f.protocol, typ, f.note)
    console.print(t)


def yt_download_cmd(url: str, cfg: Dict[str, Any], format_id: Optional[str], outtmpl: str) -> List[str]:
    cmd = yt_base(cfg)
    if cfg.get("_runtime_output_dir"):
        cmd += ["-P", str(cfg["_runtime_output_dir"])]
    if format_id:
        cmd += ["-f", format_id]
    cmd += ["-o", outtmpl, url]
    return cmd
