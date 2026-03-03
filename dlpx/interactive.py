#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel

from dlpx.utils import (
    sanitize_filename, copy_to_clipboard, shell_join, run_live,
)
from dlpx.doctor import detect_engine, open_in_1dm, open_stream, STREAM_PLAYERS
from dlpx.yt_dlp import (
    yt_info, yt_parse, yt_filter, yt_smart_pick, yt_table, yt_download_cmd,
)
from dlpx.gallery_dl import (
    gallery_fetch_items, gallery_table, gallery_list_keys,
    gallery_download_cmd,
)
from dlpx.history import ask_url_with_history
from dlpx.search import interactive_search, is_jable_url, resolve_jable_stream_url

console = Console()


def _ask_stream_player() -> str:
    """Prompt user to choose a streaming player."""
    players = list(STREAM_PLAYERS.keys())
    console.print("[bold]Stream player:[/bold]")
    for i, p in enumerate(players, 1):
        console.print(f"  {i}) {p}")
    pick = Prompt.ask("Choose player", default="1").strip()
    if pick.isdigit() and 1 <= int(pick) <= len(players):
        return players[int(pick) - 1]
    return "chooser"


def interactive_direct_stream(stream_url: str, cfg: Dict[str, Any]):
    """Menu for a direct stream URL (e.g. jable.tv m3u8) — no yt-dlp metadata needed."""
    console.print(Panel.fit(
        f"[bold]Direct stream URL[/bold]\n{stream_url}",
        title="Stream Info"
    ))

    while True:
        console.print(
            "\n1) Stream in player\n2) Open in 1DM+\n3) Copy URL\n4) Download via yt-dlp\n5) Back"
        )
        a = Prompt.ask("Action", default="1").strip()
        if a == "1":
            player = _ask_stream_player()
            ok, msg = open_stream(stream_url, player)
            console.print(f"[green]{msg}[/green]" if ok else f"[red]{msg}[/red]")
        elif a == "2":
            ok, msg = open_in_1dm(stream_url)
            console.print(f"[green]{msg}[/green]" if ok else f"[red]{msg}[/red]")
        elif a == "3":
            if copy_to_clipboard(stream_url):
                console.print("[green]Copied[/green]")
            else:
                console.print(stream_url)
        elif a == "4":
            from dlpx.yt_dlp import yt_base
            cmd = yt_base(cfg)
            if cfg.get("_runtime_output_dir"):
                cmd += ["-P", str(cfg["_runtime_output_dir"])]
            cmd += ["-o", "%(title)s.%(ext)s", stream_url]
            console.print(shell_join(cmd))
            run_live(cmd)
        elif a == "5":
            break
        else:
            console.print("[red]Invalid[/red]")


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
        console.print("\n1) Open in 1DM+\n2) Copy URL\n3) Show command\n4) Download\n5) Stream in player\n6) Back")
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
            player = _ask_stream_player()
            ok, msg = open_stream(chosen.direct_url, player)
            console.print(f"[green]{msg}[/green]" if ok else f"[red]{msg}[/red]")
        elif a == "6":
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
            from dlpx.utils import ensure_parent
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


def process_url_interactive(url: str, cfg: Dict[str, Any], forced_engine: Optional[str]):
    # jable.tv is not supported by yt-dlp; resolve to the HLS stream URL
    if is_jable_url(url):
        with console.status("[bold blue]Resolving jable.tv stream URL...[/bold blue]"):
            try:
                stream = resolve_jable_stream_url(url)
            except Exception as e:
                console.print(f"[red]Failed to resolve jable.tv stream:[/red] {e}")
                return
        if not stream:
            console.print("[red]Could not extract stream URL from jable.tv page[/red]")
            return
        console.print(f"[green]Stream URL:[/green] {stream}")
        interactive_direct_stream(stream, cfg)
        return

    engine = detect_engine(url, forced_engine, cfg)
    if engine == "gallery-dl":
        interactive_gallery(url, cfg)
    else:
        interactive_yt(url, cfg)


def interactive_main_loop(cfg: Dict[str, Any], forced_engine: Optional[str]):
    while True:
        url = ask_url_with_history("Enter URL (arrow ↑↓ history, q=quit, s=search)")
        if not url:
            console.print("[yellow]Empty input[/yellow]")
            continue
        if url.lower() in {"q", "quit", "exit", "/q"}:
            break

        if url.lower() in {"s", "/s", "/search", "search"}:
            result_url = interactive_search(cfg=cfg)
            if result_url:
                process_url_interactive(result_url, cfg, forced_engine)
        else:
            process_url_interactive(url, cfg, forced_engine)

        console.print("\n1) Input another URL\n2) Search\n3) Exit")
        nxt = Prompt.ask("Choose", default="1").strip()
        if nxt == "2":
            result_url = interactive_search(cfg=cfg)
            if result_url:
                process_url_interactive(result_url, cfg, forced_engine)
        elif nxt == "3":
            break
