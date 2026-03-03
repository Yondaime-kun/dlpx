#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt

from dlpx.config import (
    DEFAULT_CONFIG_PATH,
    load_config, init_config, apply_profile, apply_cli_overrides,
)
from dlpx.install import install_launcher, uninstall_launcher
from dlpx.history import setup_readline_history, save_readline_history
from dlpx.doctor import doctor, detect_engine
from dlpx.yt_dlp import yt_info, yt_parse, yt_smart_pick, yt_download_cmd
from dlpx.gallery_dl import gallery_list_keys, gallery_download_cmd
from dlpx.interactive import (
    process_url_interactive, interactive_main_loop,
)
from dlpx.batch import read_batch_file, run_batch
from dlpx.search import search_jable, search_youtube, display_search_results, is_jable_url, resolve_jable_stream_url
from dlpx.utils import sanitize_filename, shell_join, run_live

console = Console()


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

    # search
    p.add_argument("--search", help="Search query (uses jable.tv by default)")
    p.add_argument("--search-provider", choices=["jable", "youtube"], default="jable", help="Search provider")
    p.add_argument("--search-page", type=int, default=1, help="Search results page number")

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

        # Search mode
        if args.search:
            if args.search_provider == "jable":
                results = search_jable(args.search, page=args.search_page)
            elif args.search_provider == "youtube":
                results = search_youtube(args.search, cfg=cfg)
            else:
                console.print(f"[red]Unknown provider: {args.search_provider}[/red]")
                return
            display_search_results(results, f"Results for '{args.search}'")
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

        # Resolve jable.tv URLs to HLS stream URLs (yt-dlp can't handle jable.tv directly)
        target_url = args.url
        if target_url and is_jable_url(target_url):
            console.print("[bold blue]Resolving jable.tv stream URL...[/bold blue]")
            try:
                stream = resolve_jable_stream_url(target_url)
            except Exception as e:
                console.print(f"[red]Failed to resolve jable.tv stream:[/red] {e}")
                return
            if not stream:
                console.print("[red]Could not extract stream URL from jable.tv page[/red]")
                return
            console.print(f"[green]Stream URL:[/green] {stream}")
            target_url = stream

        if target_url and args.download:
            engine = detect_engine(target_url, forced_engine, cfg)
            if engine == "yt-dlp":
                info = yt_info(target_url, cfg)
                formats = yt_parse(info)
                chosen = yt_smart_pick(formats, cfg, audio_only=False)
                if not chosen:
                    console.print("[red]No suitable yt format[/red]")
                    return
                title = sanitize_filename(info.get("title", "video"))
                cmd = yt_download_cmd(target_url, cfg, chosen.format_id, f"{title}.%(ext)s")
                console.print(shell_join(cmd))
                run_live(cmd)
            else:
                cmd = gallery_download_cmd(target_url, cfg, None)
                console.print(shell_join(cmd))
                run_live(cmd)
            return

        if target_url:
            process_url_interactive(target_url, cfg, forced_engine)
            console.print("\n1) Input another URL\n2) Exit")
            if Prompt.ask("Choose", default="1").strip() == "1":
                interactive_main_loop(cfg, forced_engine)
            return

        interactive_main_loop(cfg, forced_engine)

    finally:
        save_readline_history(cfg)


if __name__ == "__main__":
    main()
