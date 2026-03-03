#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import concurrent.futures
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any, Set

from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.panel import Panel

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


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def ensure_parent(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)


# =========================
# Install / uninstall dlpx
# =========================
def _resolve_install_target(scope: str) -> Path:
    scope = scope.lower()
    if scope == "user":
        return Path.home() / ".local" / "bin" / "dlpx"
    if scope == "termux":
        prefix = os.environ.get("PREFIX")
        if not prefix:
            raise RuntimeError("TERMUX PREFIX not found. Use --install-scope user")
        return Path(prefix) / "bin" / "dlpx"
    if scope == "system":
        return Path("/usr/local/bin/dlpx")
    raise RuntimeError(f"Unknown install scope: {scope}")


def install_launcher(script_path: Path, scope: str = "user", force: bool = False):
    target = _resolve_install_target(scope)
    ensure_parent(target)

    if target.exists() and not force:
        console.print(f"[yellow]{target} already exists.[/yellow] Use --install-force to overwrite.")
        return

    py = sys.executable or "python3"
    launcher = f"""#!/usr/bin/env sh
# Auto-generated launcher for dlp wrapper
exec {shlex.quote(py)} {shlex.quote(str(script_path))} "$@"
"""

    with open(target, "w", encoding="utf-8") as f:
        f.write(launcher)

    os.chmod(target, 0o755)
    console.print(f"[green]Installed:[/green] {target}")

    # PATH hint
    path_env = os.environ.get("PATH", "")
    if str(target.parent) not in path_env.split(":"):
        console.print(f"[yellow]PATH hint:[/yellow] add this to shell rc:")
        console.print(f'export PATH="{target.parent}:$PATH"')

    console.print("[cyan]Try:[/cyan] dlpx --help")


def uninstall_launcher(scope: str = "user"):
    target = _resolve_install_target(scope)
    if not target.exists():
        console.print(f"[yellow]Not found:[/yellow] {target}")
        return
    target.unlink()
    console.print(f"[green]Removed:[/green] {target}")


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


# =========================
# History
# =========================
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


# =========================
# Archive
# =========================
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


# =========================
# Report
# =========================
def report_file_path(cfg: Dict[str, Any]) -> Path:
    d = Path(cfg.get("report", {}).get("dir", str(DEFAULT_REPORT_DIR))).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    return d / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"


def write_report(cfg: Dict[str, Any], results: List[JobResult]):
    if not cfg.get("report", {}).get("enabled", True):
        return
    p = report_file_path(cfg)
    data = {
        "generated_at": now_iso(),
        "summary": {
            "total": len(results),
            "success": sum(1 for r in results if r.status == "success"),
            "failed": sum(1 for r in results if r.status == "failed"),
            "skipped": sum(1 for r in results if r.status == "skipped"),
        },
        "results": [asdict(r) for r in results]
    }
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f=2)
 console.print(f"[green]Report saved:[/green] {p}")


# =========================
# Detect / doctor / opener
# =========================
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


def get_version(cmd: List[str]) -> str:
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


# =========================
# yt-dlp backend
# =========================
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


# =========================
# gallery-dl backend
# =========================
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


# =========================
# Interactive flows
# =========================
def interactive_yt(url: str, cfg: Dict[str, Any], show_all=False, audio_only=False):
    with console.status("[bold blue]Fetching yt metadata...[/bold blue]"):
        info = yt_info(url, cfg)
        allf = yt_parse(info)

    title = info.get("title", "Unknown")
    uploader = info.get("uploader", "Unknown")
    safe = sanitize_filename(title)

    console.print(Panel.fit(
        f"[bold]Engine:[/bold] yt-dlp\n[bold]Title:[/bold] {title}\n[bold]Uploader:[/bold] {uploader}",
        title="Video Info"
    ))

    fs = yt_filter(allf, show_all=show_all, audio_only=audio_only)
    if not fs:
        console.print("[red]No formats[/red]")
        return

    yt_table(fs, f"Formats ({len(fs)})")

    smart = yt_smart_pick(fs, cfg, audio_only=audio_only)
    default_idx = 1
    if smart:
        for i, f in enumerate(fs, 1):
            if f.format_id == smart.format_id:
                default_idx = i
                break

    pick = Prompt.ask("Choose format # (or 's' smart pick)", default=str(default_idx)).strip().lower()
    if pick == "s":
        chosen = smart or fs[0]
    elif pick.isdigit() and 1 <= int(pick) <= len(fs):
        chosen = fs[int(pick) - 1]
    else:
        console.print("[yellow]Invalid pick, using smart/default[/yellow]")
        chosen = smart or fs[0]

    while True:
        console.print("\n1) Open in 1DM+\n2) Copy URL\n3) Show command\n4) Download\n5) Back")
        a = Prompt.ask("Action", default="1").strip()
        if a == "1":
            ok, msg = open_in_1dm(chosen.direct_url)
            console.print(f"[green]{msg}[/green]" if ok else f"[red]{msg}[/red]")
        elif a == "2":
            if copy_to_clipboard(chosen.direct_url):
                console.print("[green]Copied[/green]")
            else:
                console.print(chosen.direct_url)
        elif a == "3":
            cmd = yt_download_cmd(url, cfg, chosen.format_id, f"{safe}.%(ext)s")
            console.print(shell_join(cmd))
        elif a == "4":
            cmd = yt_download_cmd(url, cfg, chosen.format_id, f"{safe}.%(ext)s")
            console.print(shell_join(cmd))
            run_live(cmd)
        elif a == "5":
            break
        else:
            console.print("[red]Invalid[/red]")


def interactive_gallery(url: str, cfg: Dict[str, Any]):
    with console.status("[bold blue]Fetching gallery direct URLs...[/bold blue]"):
        try:
            items = gallery_fetch_items(url, cfg)
        except subprocess.CalledProcessError as e:
            console.print("[red]Failed to fetch URLs via --get-urls[/red]")
            if e.stderr:
                console.print(e.stderr.strip())
            return

    console.print(Panel.fit(f"[bold]Engine:[/bold] gallery-dl\n[bold]Items:[/bold] {len(items)}", title="Gallery Info"))

    if not items:
        console.print("[yellow]No URLs from --get-urls.[/yellow]")
        if Confirm.ask("Run -K (list keys) for debugging?", default=True):
            gallery_list_keys(url, cfg)
        if Confirm.ask("Download anyway with gallery-dl?", default=True):
            cmd = gallery_download_cmd(url, cfg, None)
            console.print(shell_join(cmd))
            run_live(cmd)
        return

    preview_limit = int(cfg.get("gallery_dl", {}).get("preview_limit", 100))
    gallery_table(items[:preview_limit], f"Items Preview ({min(preview_limit, len(items))}/{len(items)})")

    while True:
        console.print("\n1) Open item in 1DM+\n2) Open first N links in 1DM+\n3) Copy item URL\n4) Export links txt\n5) Download all\n6) List keys (-K)\n7) Back")
        a = Prompt.ask("Action", default="5").strip()

        if a == "1":
            s = Prompt.ask("Item #", default="1").strip()
            if not s.isdigit():
                console.print("[red]Invalid number[/red]")
                continue
            target = next((x for x in items if x.index == int(s)), None)
            if not target:
                console.print("[red]Item not found[/red]")
                continue
            ok, msg = open_in_1dm(target.url)
            console.print(f"[green]{msg}[/green]" if ok else f"[red]{msg}[/red]")

        elif a == "2":
            n = Prompt.ask("Open first N", default="3").strip()
            if not n.isdigit():
                console.print("[red]Invalid N[/red]")
                continue
            nn = max(1, int(n))
            opened = 0
            for it in items[:nn]:
                ok, _ = open_in_1dm(it.url)
                if ok:
                    opened += 1
            console.print(f"[green]Opened {opened}/{min(nn, len(items))} links[/green]")

        elif a == "3":
            s = Prompt.ask("Item #", default="1").strip()
            if not s.isdigit():
                console.print("[red]Invalid number[/red]")
                continue
            target = next((x for x in items if x.index == int(s)), None)
            if not target:
                console.print("[red]Item not found[/red]")
                continue
            if copy_to_clipboard(target.url):
                console.print("[green]Copied[/green]")
            else:
                console.print(target.url)

        elif a == "4":
            out = Prompt.ask("Export file path", default=str(Path.cwd() / "links.txt")).strip()
            p = Path(out).expanduser()
            ensure_parent(p)
            with open(p, "w", encoding="utf-8") as f:
                for it in items:
                    f.write(it.url + "\n")
            console.print(f"[green]Exported:[/green] {p}")

        elif a == "5":
            cmd = gallery_download_cmd(url, cfg, None)
            console.print(shell_join(cmd))
            run_live(cmd)

        elif a == "6":
            gallery_list_keys(url, cfg)

        elif a == "7":
            break
        else:
            console.print("[red]Invalid action[/red]")


# =========================
# Batch
# =========================
def read_batch_file(path: str) -> List[str]:
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"Batch file not found: {p}")
    urls = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            urls.append(s)
    return urls


def process_single_job(url: str, cfg: Dict[str, Any], forced_engine: Optional[str], retries: int, mode_download: bool, archive_set: Set[str]) -> JobResult:
    start = time.time()
    started_at = now_iso()
    engine = detect_engine(url, forced_engine, cfg)
    key = f"{engine}|{url}"

    if key in archive_set:
        end = time.time()
        return JobResult(url, engine, "skipped", "archive-skip", started_at, now_iso(), round(end - start, 3))

    last_err = ""
    for attempt in range(1, retries + 2):
        try:
            if engine == "yt-dlp":
                info = yt_info(url, cfg)
                formats = yt_parse(info)
                chosen = yt_smart_pick(formats, cfg, audio_only=False)
                if not chosen:
                    raise RuntimeError("No suitable format")
                if mode_download:
                    title = sanitize_filename(info.get("title", "video"))
                    cmd = yt_download_cmd(url, cfg, chosen.format_id, f"{title}.%(ext)s")
                    rc = run_live(cmd)
                    if rc != 0:
                        raise RuntimeError(f"yt-dlp exit code {rc}")
                add_archive(cfg, key)
                end = time.time()
                return JobResult(url, engine, "success", "ok", started_at, now_iso(), round(end - start, 3), chosen.direct_url)

            else:
                if mode_download:
                    cmd = gallery_download_cmd(url, cfg, None)
                    rc = run_live(cmd)
                    if rc != 0:
                        raise RuntimeError(f"gallery-dl exit code {rc}")
                    add_archive(cfg, key)
                    end = time.time()
                    return JobResult(url, engine, "success", "ok", started_at, now_iso(), round(end - start, 3))
                else:
                    items = gallery_fetch_items(url, cfg)
                    if not items:
                        raise RuntimeError("No gallery items")
                    add_archive(cfg, key)
                    end = time.time()
                    return JobResult(url, engine, "success", "ok", started_at, now_iso(), round(end - start, 3), items[0].url)

        except Exception as e:
            last_err = str(e)
            if attempt <= retries:
                time.sleep(1.0)

    end = time.time()
    return JobResult(url, engine, "failed", last_err or "unknown", started_at, now_iso(), round(end - start, 3))


def run_batch(urls: List[str], cfg: Dict[str, Any], forced_engine: Optional[str], workers: int, retries: int, mode_download: bool):
    archive_set = load_archive(cfg)
    results: List[JobResult] = []

    console.print(f"[bold]Batch start[/bold] total={len(urls)} workers={workers} retries={retries} download={mode_download}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = [ex.submit(process_single_job, u, cfg, forced_engine, retries, mode_download, archive_set) for u in urls]
        for fut in concurrent.futures.as_completed(futs):
            r = fut.result()
            results.append(r)
            color = "green" if r.status == "success" else ("yellow" if r.status == "skipped" else "red")
            console.print(f"[{color}]{r.status.upper()}[/{color}] {r.url} ({r.reason})")

    t = Table(title="Batch Summary")
    t.add_column("Metric")
    t.add_column("Value")
    t.add_row("Total", str(len(results)))
    t.add_row("Success", str(sum(1 for x in results if x.status == "success")))
    t.add_row("Failed", str(sum(1 for x in results if x.status == "failed")))
    t.add_row("Skipped", str(sum(1 for x in results if x.status == "skipped")))
    console.print(t)

    write_report(cfg, results)


# =========================
# Main loop
# =========================
def process_url_interactive(url: str, cfg: Dict[str, Any], forced_engine: Optional[str]):
    engine = detect_engine(url, forced_engine, cfg)
    if engine == "gallery-dl":
        interactive_gallery(url, cfg)
    else:
        interactive_yt(url, cfg)


def interactive_main_loop(cfg: Dict[str, Any], forced_engine: Optional[str]):
    while True:
        url = ask_url_with_history("Enter URL (arrow up/down history, q=quit)")
        if not url:
            console.print("[yellow]Empty input[/yellow]")
            continue
        if url.lower() in {"q", "quit", "exit", "/q"}:
            break

        process_url_interactive(url, cfg, forced_engine)

        console.print("\n1) Input another URL\n2) Exit")
        nxt = Prompt.ask("Choose", default="1").strip()
        if nxt == "2":
            break


# =========================
# Parser
# =========================
def build_parser():
    p = argparse.ArgumentParser(description="Universal wrapper: yt-dlp + gallery-dl (+install dlpx)")
    p.add_argument("url", nargs="?", help="Target URL")
    p.add_argument("--engine", choices=["auto", "yt-dlp", "gallery-dl"], default="auto")
    p.add_argument("--config", help=f"Config path (default: {DEFAULT_CONFIG_PATH})")
    p.add_argument("--init-config", action="store_true")
    p.add_argument("--doctor", action="store_true")

    # install / uninstall
    p.add_argument("--install", action="store_true", help="Install launcher command 'dlpx'")
    p.add_argument("--uninstall", action="store_true", help="Uninstall launcher command 'dlpx'")
    p.add_argument("--install-scope", choices=["user", "termux", "system"], default="user")
    p.add_argument("--install-force", action="store_true", help="Overwrite existing launcher")

    # profile
    p.add_argument("--profile", help="Profile name from config profiles.*")

    # batch
    p.add_argument("--batch", help="Batch URL file (one URL per line)")
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--retries", type=int, default=1)

    # actions
    p.add_argument("--download", action="store_true", help="Download mode")
    p.add_argument("--list-keys", action="store_true", help="gallery-dl -K for URL")

    # output
    p.add_argument("--output-dir", help="Output directory override")
    p.add_argument("--export-links", help="Export fetched links to txt (gallery preview mode)")

    # filters
    p.add_argument("--allowed-ext", help="Gallery allowed ext CSV, e.g. jpg,png,mp4")

    # overrides
    p.add_argument("--cookie-file", help="Override cookies file for both engines")
    p.add_argument("--cookies-from-browser", help="Override cookies-from-browser for both engines")
    p.add_argument("--proxy", help="Override proxy for both engines")
    p.add_argument("--ua", help="Override user-agent for both engines")
    p.add_argument("--referer", help="Override referer for both engines")
    p.add_argument("--header", action="append", default=[], help="Override header, can repeat. Format: Key: Value")

    return p


def main():
    args = build_parser().parse_args()

    # install / uninstall first
    script_path = Path(__file__).resolve()
    if args.install:
        try:
            install_launcher(script_path, scope=args.install_scope, force=args.install_force)
        except PermissionError:
            console.print("[red]Permission denied.[/red] Try another scope or proper privileges.")
        except Exception as e:
            console.print(f"[red]Install failed:[/red] {e}")
        return

    if args.uninstall:
        try:
            uninstall_launcher(scope=args.install_scope)
        except Exception as e:
            console.print(f"[red]Uninstall failed:[/red] {e}")
        return

    if args.init_config:
        init_config(args.config)
        return

    cfg = load_config(args.config)
    cfg = apply_profile(cfg, args.profile)
    cfg = apply_cli_overrides(cfg, args)

    setup_readline_history(cfg)
    try:
        forced_engine = None if args.engine == "auto" else args.engine

        if args.doctor:
            doctor(cfg, args.cookie_file, args.output_dir)
            if not args.url and not args.batch:
                return

        if args.batch:
            urls = read_batch_file(args.batch)
            run_batch(
                urls=urls,
                cfg=cfg,
                forced_engine=forced_engine,
                workers=max(1, args.workers),
                retries=max(0, args.retries),
                mode_download=bool(args.download),
            )
            return

        if args.url and args.list_keys:
            gallery_list_keys(args.url, cfg)
            return

        if args.url and args.download:
            engine = detect_engine(args.url, forced_engine, cfg)
            if engine == "yt-dlp":
                info = yt_info(args.url, cfg)
                formats = yt_parse(info)
                chosen = yt_smart_pick(formats, cfg, audio_only=False)
                if not chosen:
                    console.print("[red]No suitable yt format[/red]")
                    return
                title = sanitize_filename(info.get("title", "video"))
                cmd = yt_download_cmd(args.url, cfg, chosen.format_id, f"{title}.%(ext)s")
                console.print(shell_join(cmd))
                run_live(cmd)
            else:
                cmd = gallery_download_cmd(args.url, cfg, None)
                console.print(shell_join(cmd))
                run_live(cmd)
            return

        if args.url:
            process_url_interactive(args.url, cfg, forced_engine)
            console.print("\n1) Input another URL\n2) Exit")
            if Prompt.ask("Choose", default="1").strip() == "1":
                interactive_main_loop(cfg, forced_engine)
            return

        interactive_main_loop(cfg, forced_engine)

    finally:
        save_readline_history(cfg)


if __name__ == "__main__":
    main()