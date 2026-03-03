#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class MediaFormat:
    format_id: str
    ext: str
    resolution: str
    height: int
    fps: str
    vcodec: str
    acodec: str
    filesize: Optional[int]
    note: str
    direct_url: str
    protocol: str
    is_progressive: bool
    is_audio_only: bool
    tbr: Optional[float]


@dataclass
class GalleryItem:
    index: int
    url: str
    filename: str
    extension: str
    category: str
    extractor: str


@dataclass
class JobResult:
    url: str
    engine: str
    status: str
    reason: str
    started_at: str
    ended_at: str
    duration_sec: float
    output: Optional[str] = None


def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def run_cmd(cmd: List[str], check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def run_live(cmd: List[str]) -> int:
    p = subprocess.Popen(cmd)
    p.wait()
    return p.returncode


def shell_join(cmd: List[str]) -> str:
    return " ".join(shlex.quote(c) for c in cmd)


def human_size(num: Optional[int]) -> str:
    if not num:
        return "-"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num)
    for u in units:
        if size < 1024:
            return f"{size:.1f} {u}"
        size /= 1024
    return f"{size:.1f} PB"


def sanitize_filename(name: str, max_len: int = 120) -> str:
    name = re.sub(r'[\\/*?:"<>|]+', "_", name).strip()
    name = re.sub(r"\s+", " ", name)
    return (name[:max_len].rstrip() if len(name) > max_len else name) or "download"


def copy_to_clipboard(text: str) -> bool:
    try:
        import pyperclip  # type: ignore
        pyperclip.copy(text)
        return True
    except Exception:
        return False


def deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def ensure_parent(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
