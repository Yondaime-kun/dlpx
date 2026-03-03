#!/usr/bin/env python3
"""DLPX – Universal media downloader (Flet mobile app)."""

import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional
from urllib.parse import quote_plus

import flet as ft
import requests

try:
    import yt_dlp as yt_dlp_lib

    HAS_YT_DLP = True
except ImportError:
    HAS_YT_DLP = False


# ── Data models ───────────────────────────────────────


@dataclass
class SearchResult:
    """A single search result from YouTube or jable.tv."""

    title: str
    url: str
    duration: str
    source: str


@dataclass
class FormatInfo:
    """Parsed media format from yt-dlp info dict."""

    format_id: str
    ext: str
    resolution: str
    height: int
    filesize: Optional[int]
    note: str
    is_progressive: bool
    is_audio_only: bool


@dataclass
class DownloadTask:
    """Tracks a single download job."""

    url: str
    title: str
    status: str = "pending"
    progress: float = 0.0
    speed: str = ""
    eta: str = ""
    error: str = ""
    format_id: Optional[str] = None


# ── Backend helpers ───────────────────────────────────

_SESSION_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


def human_size(num: Optional[int]) -> str:
    """Format byte count as human-readable string."""
    if not num:
        return "-"
    size = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def fetch_info(url: str) -> dict:
    """Fetch media info using the yt-dlp Python API."""
    if not HAS_YT_DLP:
        raise RuntimeError("yt-dlp is not installed")
    opts = {"quiet": True, "no_warnings": True}
    with yt_dlp_lib.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def parse_formats(info: dict) -> List[FormatInfo]:
    """Convert raw yt-dlp format dicts into :class:`FormatInfo` objects."""
    out: List[FormatInfo] = []
    for f in info.get("formats", []):
        if not f.get("url"):
            continue
        vcodec = str(f.get("vcodec", "none"))
        acodec = str(f.get("acodec", "none"))
        is_audio = vcodec == "none" and acodec != "none"
        is_prog = vcodec != "none" and acodec != "none"
        h = int(f.get("height") or 0)
        res = f.get("resolution") or (f"{h}p" if h else ("audio" if is_audio else "-"))
        out.append(
            FormatInfo(
                format_id=str(f.get("format_id", "-")),
                ext=str(f.get("ext", "-")),
                resolution=res,
                height=h,
                filesize=f.get("filesize") or f.get("filesize_approx"),
                note=str(f.get("format_note", "-")),
                is_progressive=is_prog,
                is_audio_only=is_audio,
            )
        )
    out.sort(key=lambda x: (0 if x.is_progressive else 1, -(x.height or 0)))
    return out


def smart_pick(formats: List[FormatInfo]) -> Optional[FormatInfo]:
    """Pick the best format – prefers progressive mp4, highest resolution."""
    if not formats:
        return None
    prog = [f for f in formats if f.is_progressive]
    candidates = prog if prog else formats
    mp4 = [f for f in candidates if f.ext.lower() == "mp4"]
    if mp4:
        candidates = mp4
    candidates.sort(key=lambda x: -(x.height or 0))
    return candidates[0] if candidates else None


def download_media(
    url: str,
    output_dir: str,
    format_id: Optional[str] = None,
    progress_hook: Optional[Callable] = None,
) -> str:
    """Download media using the yt-dlp Python API."""
    if not HAS_YT_DLP:
        raise RuntimeError("yt-dlp is not installed")
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
    }
    if format_id:
        opts["format"] = format_id
    if progress_hook:
        opts["progress_hooks"] = [progress_hook]
    with yt_dlp_lib.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)


def search_youtube_api(query: str, max_results: int = 10) -> List[SearchResult]:
    """Search YouTube via the yt-dlp Python API (flat extraction)."""
    if not HAS_YT_DLP:
        raise RuntimeError("yt-dlp is not installed")
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True}
    with yt_dlp_lib.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
    results: List[SearchResult] = []
    for entry in (info or {}).get("entries", []):
        vid_url = entry.get("url") or entry.get("webpage_url", "")
        if vid_url and not vid_url.startswith("http"):
            vid_url = f"https://www.youtube.com/watch?v={vid_url}"
        title = entry.get("title", "")
        dur = entry.get("duration")
        duration = ""
        if dur:
            m, s = divmod(int(dur), 60)
            duration = f"{m}:{s:02d}"
        if vid_url and title:
            results.append(SearchResult(title=title, url=vid_url, duration=duration, source="youtube"))
    return results


def search_jable_api(query: str, page: int = 1) -> List[SearchResult]:
    """Search jable.tv using HTTP requests and HTML parsing."""
    encoded = quote_plus(query)
    base = "https://en.jable.tv"
    url = f"{base}/search/{encoded}/"
    if page > 1:
        url = (
            f"{base}/search/{encoded}/?mode=async&function=get_block"
            f"&block_id=list_videos_videos_list_search_result"
            f"&q={encoded}&sort_by=&from={page}"
        )

    resp = requests.get(url, headers=_SESSION_HEADERS, timeout=15)
    resp.raise_for_status()
    html = resp.text

    results: List[SearchResult] = []
    seen: set = set()

    # Extract video links and titles from HTML
    for href in re.findall(r'href="(https?://en\.jable\.tv/videos/[^"]+)"', html):
        if href in seen:
            continue
        seen.add(href)
        slug = href.rstrip("/").rsplit("/", 1)[-1]
        title = slug.replace("-", " ").title()
        results.append(SearchResult(title=title, url=href, duration="", source="jable.tv"))

    # Try to get better titles from title elements
    title_matches = re.findall(
        r'<a[^>]+href="(https?://en\.jable\.tv/videos/[^"]+)"[^>]*'
        r'title="([^"]+)"',
        html,
    )
    title_map = {url_: t for url_, t in title_matches}
    for r in results:
        if r.url in title_map:
            r.title = title_map[r.url]

    return results


# ── Flet UI ───────────────────────────────────────────


def main(page: ft.Page):
    page.title = "DLPX"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)

    # ── State ──
    downloads: List[DownloadTask] = []

    # ── Helpers ──
    def show_snack(msg: str, bgcolor: str = ft.Colors.GREEN):
        page.snack_bar = ft.SnackBar(ft.Text(msg), bgcolor=bgcolor)
        page.snack_bar.open = True
        page.update()

    # ── Downloads list ──
    download_list = ft.ListView(spacing=8, padding=10, expand=True)

    def refresh_downloads():
        download_list.controls.clear()
        if not downloads:
            download_list.controls.append(
                ft.Container(
                    ft.Text("No downloads yet", size=16, color=ft.Colors.GREY),
                    alignment=ft.alignment.center,
                    padding=40,
                )
            )
        for dl in reversed(downloads):
            icon = {
                "pending": ft.Icons.HOURGLASS_EMPTY,
                "downloading": ft.Icons.DOWNLOADING,
                "done": ft.Icons.CHECK_CIRCLE,
                "error": ft.Icons.ERROR,
            }.get(dl.status, ft.Icons.HELP)
            color = {
                "pending": ft.Colors.GREY,
                "downloading": ft.Colors.BLUE,
                "done": ft.Colors.GREEN,
                "error": ft.Colors.RED,
            }.get(dl.status, ft.Colors.GREY)

            parts = [dl.status.upper()]
            if dl.speed:
                parts.append(dl.speed)
            if dl.eta:
                parts.append(f"ETA {dl.eta}")
            if dl.error:
                parts.append(dl.error)

            bar_value = dl.progress if dl.status == "downloading" else (1.0 if dl.status == "done" else 0)
            download_list.controls.append(
                ft.Card(
                    ft.Container(
                        ft.Column(
                            [
                                ft.ListTile(
                                    leading=ft.Icon(icon, color=color),
                                    title=ft.Text(
                                        dl.title or dl.url,
                                        max_lines=2,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                    subtitle=ft.Text(" · ".join(parts), size=12),
                                ),
                                ft.ProgressBar(value=bar_value, color=color),
                            ]
                        ),
                        padding=ft.padding.only(bottom=8),
                    )
                )
            )
        page.update()

    # ── Download logic ──
    def start_download(url: str, title: str, format_id: Optional[str] = None):
        task = DownloadTask(url=url, title=title, format_id=format_id)
        downloads.append(task)
        nav_bar.selected_index = 2
        body.content = views[2]
        refresh_downloads()

        def _run():
            try:
                task.status = "downloading"
                refresh_downloads()
                out_dir = settings_output.value or str(Path.home() / "Downloads")
                os.makedirs(out_dir, exist_ok=True)

                def _hook(d):
                    if d["status"] == "downloading":
                        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                        done = d.get("downloaded_bytes", 0)
                        task.progress = done / total if total else 0
                        task.speed = d.get("_speed_str", "")
                        task.eta = d.get("_eta_str", "")
                        refresh_downloads()
                    elif d["status"] == "finished":
                        task.progress = 1.0
                        task.status = "done"
                        refresh_downloads()

                download_media(url, out_dir, format_id, _hook)
                task.status = "done"
                task.progress = 1.0
                show_snack(f"Downloaded: {title}")
            except Exception as exc:
                task.status = "error"
                task.error = str(exc)[:100]
                show_snack(f"Error: {str(exc)[:60]}", ft.Colors.RED)
            refresh_downloads()

        threading.Thread(target=_run, daemon=True).start()

    # ── Format selection dialog ──
    def _close_dialog(dlg):
        dlg.open = False
        page.update()

    def show_formats(info: dict, formats: List[FormatInfo], url: str):
        title = info.get("title", "Unknown")
        items = []
        for f in formats[:20]:
            typ = "AV" if f.is_progressive else ("Audio" if f.is_audio_only else "Video")
            label = f"{f.resolution} · {f.ext} · {typ} · {human_size(f.filesize)}"

            def _on_pick(e, fid=f.format_id, dlg_ref=[]):
                _close_dialog(dlg_ref[0])
                start_download(url, title, fid)

            tile = ft.ListTile(
                title=ft.Text(label, size=14),
                subtitle=ft.Text(f"ID: {f.format_id} | {f.note}", size=11),
                trailing=ft.Icon(ft.Icons.DOWNLOAD),
            )
            items.append((tile, _on_pick))

        best = smart_pick(formats)
        dlg = ft.AlertDialog(
            title=ft.Text(title, size=16, max_lines=3, overflow=ft.TextOverflow.ELLIPSIS),
            content=ft.Container(ft.ListView(spacing=2, expand=True), width=350, height=400),
            actions=[
                ft.TextButton(
                    "Smart Pick",
                    on_click=lambda e: (
                        _close_dialog(dlg),
                        start_download(url, title, best.format_id if best else None),
                    ),
                ),
                ft.TextButton("Cancel", on_click=lambda e: _close_dialog(dlg)),
            ],
        )
        # Wire up the tile click handlers now that dlg exists
        lv = dlg.content.content
        for tile, handler in items:
            handler.__defaults__ = (handler.__defaults__[0], [dlg])  # type: ignore[union-attr]
            tile.on_click = handler
            lv.controls.append(tile)

        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    # ── Fetch formats ──
    home_status = ft.Text("", size=13, visible=False)
    home_bar = ft.ProgressBar(visible=False)

    def fetch_formats(url_str: str):
        if not url_str or not url_str.strip():
            show_snack("Please enter a URL", ft.Colors.ORANGE)
            return

        def _run():
            try:
                home_status.value = "Fetching media info…"
                home_status.color = ft.Colors.BLUE
                home_status.visible = True
                home_bar.visible = True
                page.update()
                info = fetch_info(url_str.strip())
                title = info.get("title", "Unknown")
                formats = parse_formats(info)
                home_status.visible = False
                home_bar.visible = False
                page.update()
                if formats:
                    show_formats(info, formats, url_str.strip())
                else:
                    start_download(url_str.strip(), title)
            except Exception as exc:
                home_status.value = f"Error: {exc}"
                home_status.color = ft.Colors.RED
                home_bar.visible = False
                page.update()

        threading.Thread(target=_run, daemon=True).start()

    def quick_dl(url_str: str):
        if not url_str or not url_str.strip():
            show_snack("Please enter a URL", ft.Colors.ORANGE)
            return

        def _run():
            try:
                home_status.value = "Fetching…"
                home_status.visible = True
                home_bar.visible = True
                page.update()
                info = fetch_info(url_str.strip())
                title = info.get("title", "Unknown")
                formats = parse_formats(info)
                best = smart_pick(formats)
                home_status.visible = False
                home_bar.visible = False
                page.update()
                start_download(url_str.strip(), title, best.format_id if best else None)
            except Exception as exc:
                home_status.value = f"Error: {exc}"
                home_status.color = ft.Colors.RED
                home_bar.visible = False
                page.update()

        threading.Thread(target=_run, daemon=True).start()

    # ══════════════════════════════════════════════════
    # HOME
    # ══════════════════════════════════════════════════
    url_field = ft.TextField(
        label="Enter URL",
        hint_text="https://youtube.com/watch?v=…",
        border_radius=12,
        prefix_icon=ft.Icons.LINK,
        expand=True,
        on_submit=lambda e: fetch_formats(url_field.value),
    )

    home_view = ft.Container(
        ft.Column(
            [
                ft.Container(
                    ft.Column(
                        [
                            ft.Text("DLPX", size=28, weight=ft.FontWeight.BOLD),
                            ft.Text("Universal Media Downloader", size=14, color=ft.Colors.GREY),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.padding.only(top=40, bottom=20),
                    alignment=ft.alignment.center,
                ),
                ft.Container(
                    ft.Column(
                        [
                            ft.Row([url_field]),
                            ft.Row(
                                [
                                    ft.ElevatedButton(
                                        "Fetch Formats",
                                        icon=ft.Icons.LIST,
                                        on_click=lambda e: fetch_formats(url_field.value),
                                        expand=True,
                                    ),
                                    ft.ElevatedButton(
                                        "Quick Download",
                                        icon=ft.Icons.DOWNLOAD,
                                        on_click=lambda e: quick_dl(url_field.value),
                                        expand=True,
                                        color=ft.Colors.WHITE,
                                        bgcolor=ft.Colors.BLUE,
                                    ),
                                ]
                            ),
                            ft.Row(
                                [
                                    ft.OutlinedButton(
                                        "Clear",
                                        icon=ft.Icons.CLEAR,
                                        on_click=lambda e: _clear_url(),
                                    ),
                                ]
                            ),
                        ],
                        spacing=12,
                    ),
                    padding=ft.padding.symmetric(horizontal=16),
                ),
                ft.Container(
                    ft.Column([home_status, home_bar], spacing=4),
                    padding=ft.padding.symmetric(horizontal=16, vertical=8),
                ),
                ft.Container(
                    ft.Column(
                        [
                            ft.Card(
                                ft.Container(
                                    ft.ListTile(
                                        leading=ft.Icon(ft.Icons.VIDEO_LIBRARY),
                                        title=ft.Text("Supported Sites"),
                                        subtitle=ft.Text(
                                            "YouTube, Twitter/X, Reddit, Instagram, TikTok, and 1800+ more"
                                        ),
                                    ),
                                    padding=4,
                                )
                            ),
                            ft.Card(
                                ft.Container(
                                    ft.ListTile(
                                        leading=ft.Icon(ft.Icons.SEARCH),
                                        title=ft.Text("Search"),
                                        subtitle=ft.Text(
                                            "Search YouTube or jable.tv from the Search tab"
                                        ),
                                    ),
                                    padding=4,
                                )
                            ),
                        ],
                        spacing=8,
                    ),
                    padding=ft.padding.symmetric(horizontal=16, vertical=8),
                ),
            ],
            scroll=ft.ScrollMode.AUTO,
        ),
        expand=True,
    )

    def _clear_url():
        url_field.value = ""
        home_status.visible = False
        home_bar.visible = False
        page.update()

    # ══════════════════════════════════════════════════
    # SEARCH
    # ══════════════════════════════════════════════════
    search_field = ft.TextField(
        label="Search query",
        hint_text="Search for videos…",
        border_radius=12,
        prefix_icon=ft.Icons.SEARCH,
        expand=True,
        on_submit=lambda e: _do_search(),
    )
    search_provider = ft.Dropdown(
        label="Provider",
        value="youtube",
        options=[
            ft.dropdown.Option("youtube", "YouTube"),
            ft.dropdown.Option("jable", "Jable.tv"),
        ],
        width=140,
        border_radius=12,
    )
    search_status = ft.Text("", size=13, visible=False)
    search_bar = ft.ProgressBar(visible=False)
    search_list = ft.ListView(spacing=4, padding=10, expand=True)

    def _use_result(url: str):
        url_field.value = url
        nav_bar.selected_index = 0
        body.content = views[0]
        page.update()
        fetch_formats(url)

    def _do_search():
        query = (search_field.value or "").strip()
        if not query:
            show_snack("Enter a search query", ft.Colors.ORANGE)
            return

        def _run():
            try:
                search_status.value = "Searching…"
                search_status.color = ft.Colors.BLUE
                search_status.visible = True
                search_bar.visible = True
                search_list.controls.clear()
                page.update()

                prov = search_provider.value or "youtube"
                results = search_youtube_api(query) if prov == "youtube" else search_jable_api(query)

                search_status.visible = False
                search_bar.visible = False

                if not results:
                    search_list.controls.append(
                        ft.Container(
                            ft.Text("No results found", size=16, color=ft.Colors.GREY),
                            alignment=ft.alignment.center,
                            padding=40,
                        )
                    )
                else:
                    for i, r in enumerate(results, 1):
                        search_list.controls.append(
                            ft.Card(
                                ft.Container(
                                    ft.ListTile(
                                        leading=ft.CircleAvatar(
                                            content=ft.Text(str(i)),
                                            bgcolor=ft.Colors.BLUE,
                                        ),
                                        title=ft.Text(
                                            r.title,
                                            max_lines=2,
                                            overflow=ft.TextOverflow.ELLIPSIS,
                                        ),
                                        subtitle=ft.Text(
                                            f"{r.source} · {r.duration}" if r.duration else r.source,
                                            size=12,
                                        ),
                                        trailing=ft.IconButton(
                                            ft.Icons.DOWNLOAD,
                                            tooltip="Quick download",
                                            on_click=lambda e, u=r.url, t=r.title: start_download(u, t),
                                        ),
                                        on_click=lambda e, u=r.url: _use_result(u),
                                    ),
                                    padding=4,
                                )
                            )
                        )
                page.update()
            except Exception as exc:
                search_status.value = f"Error: {exc}"
                search_status.color = ft.Colors.RED
                search_bar.visible = False
                page.update()

        threading.Thread(target=_run, daemon=True).start()

    search_view = ft.Container(
        ft.Column(
            [
                ft.Container(
                    ft.Column(
                        [
                            ft.Text("Search", size=24, weight=ft.FontWeight.BOLD),
                            ft.Row([search_field, search_provider]),
                            ft.ElevatedButton(
                                "Search",
                                icon=ft.Icons.SEARCH,
                                on_click=lambda e: _do_search(),
                            ),
                            search_status,
                            search_bar,
                        ],
                        spacing=12,
                    ),
                    padding=ft.padding.only(top=20, left=16, right=16, bottom=8),
                ),
                search_list,
            ]
        ),
        expand=True,
    )

    # ══════════════════════════════════════════════════
    # DOWNLOADS
    # ══════════════════════════════════════════════════
    def _clear_done():
        downloads[:] = [d for d in downloads if d.status not in ("done", "error")]
        refresh_downloads()

    downloads_view = ft.Container(
        ft.Column(
            [
                ft.Container(
                    ft.Row(
                        [
                            ft.Text("Downloads", size=24, weight=ft.FontWeight.BOLD),
                            ft.IconButton(ft.Icons.DELETE_SWEEP, tooltip="Clear completed", on_click=lambda e: _clear_done()),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    padding=ft.padding.only(top=20, left=16, right=16, bottom=8),
                ),
                download_list,
            ]
        ),
        expand=True,
    )

    # ══════════════════════════════════════════════════
    # SETTINGS
    # ══════════════════════════════════════════════════
    settings_output = ft.TextField(
        label="Output Directory",
        value=str(Path.home() / "Downloads"),
        border_radius=12,
        prefix_icon=ft.Icons.FOLDER,
    )

    settings_view = ft.Container(
        ft.Column(
            [
                ft.Container(
                    ft.Column(
                        [
                            ft.Text("Settings", size=24, weight=ft.FontWeight.BOLD),
                            ft.Divider(),
                            settings_output,
                            ft.Divider(),
                            ft.Card(
                                ft.Container(
                                    ft.ListTile(
                                        leading=ft.Icon(ft.Icons.INFO),
                                        title=ft.Text("DLPX"),
                                        subtitle=ft.Text(
                                            "Universal Media Downloader\nPowered by yt-dlp + Flet"
                                        ),
                                    ),
                                    padding=4,
                                )
                            ),
                            ft.Text(
                                f"yt-dlp: {'Available' if HAS_YT_DLP else 'Not installed'}",
                                size=13,
                                color=ft.Colors.GREEN if HAS_YT_DLP else ft.Colors.RED,
                            ),
                        ],
                        spacing=16,
                    ),
                    padding=ft.padding.only(top=20, left=16, right=16),
                )
            ],
            scroll=ft.ScrollMode.AUTO,
        ),
        expand=True,
    )

    # ══════════════════════════════════════════════════
    # NAVIGATION
    # ══════════════════════════════════════════════════
    views = [home_view, search_view, downloads_view, settings_view]
    body = ft.Container(content=views[0], expand=True)

    def _on_nav(e):
        idx = e.control.selected_index
        body.content = views[idx]
        if idx == 2:
            refresh_downloads()
        page.update()

    nav_bar = ft.NavigationBar(
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.HOME, label="Home"),
            ft.NavigationBarDestination(icon=ft.Icons.SEARCH, label="Search"),
            ft.NavigationBarDestination(icon=ft.Icons.DOWNLOAD, label="Downloads"),
            ft.NavigationBarDestination(icon=ft.Icons.SETTINGS, label="Settings"),
        ],
        selected_index=0,
        on_change=_on_nav,
    )

    page.add(body, nav_bar)
    refresh_downloads()


if __name__ == "__main__":
    ft.app(main)
