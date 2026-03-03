#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import shutil
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from urllib.parse import quote_plus, urljoin

import requests
from scrapling.parser import Adaptor
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from dlpx.utils import run_cmd

console = Console()

_SESSION_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

JABLE_BASE = "https://en.jable.tv"


@dataclass
class SearchResult:
    title: str
    url: str
    thumbnail: str
    duration: str
    source: str


def _get_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_SESSION_HEADERS)
    return s


def search_jable(query: str, page: int = 1) -> List[SearchResult]:
    """Scrape en.jable.tv search results for the given query using scrapling."""
    encoded = quote_plus(query)
    url = f"{JABLE_BASE}/search/{encoded}/"
    if page > 1:
        url = f"{JABLE_BASE}/search/{encoded}/?mode=async&function=get_block&block_id=list_videos_videos_list_search_result&q={encoded}&sort_by=&from={page}"

    session = _get_session()
    resp = session.get(url, timeout=15)
    resp.raise_for_status()

    page_doc = Adaptor(resp.text, url=JABLE_BASE)
    results: List[SearchResult] = []

    video_items = page_doc.css("div.video-img-box")
    if not video_items:
        video_items = page_doc.css("div.col-6.col-sm-4.col-lg-3")
    if not video_items:
        video_items = page_doc.css("div.item")

    for item in video_items:
        a_tags = item.css("a[href]")
        if not a_tags:
            continue
        a_tag = a_tags[0]
        href = a_tag.attrib.get("href", "")
        if not href:
            continue
        link = urljoin(JABLE_BASE, href)

        imgs = item.css("img")
        thumb = ""
        if imgs:
            thumb = imgs[0].attrib.get("data-src", "") or imgs[0].attrib.get("src", "")

        title_els = item.css("h6.title a")
        if not title_els:
            title_els = item.css(".title a")
        title_el = title_els[0] if title_els else a_tag
        title = title_el.text.strip() if title_el.text else ""
        if not title:
            title = a_tag.attrib.get("title", "") or href.rstrip("/").rsplit("/", 1)[-1]

        dur_els = item.css(".duration")
        if not dur_els:
            dur_els = item.css(".label")
        duration = dur_els[0].text.strip() if dur_els and dur_els[0].text else ""

        if link and title:
            results.append(SearchResult(
                title=title,
                url=link,
                thumbnail=thumb,
                duration=duration,
                source="jable.tv",
            ))

    return results


def search_youtube(query: str, max_results: int = 10, cfg: Optional[Dict[str, Any]] = None) -> List[SearchResult]:
    """Search YouTube using yt-dlp's built-in ytsearch extractor."""
    if not shutil.which("yt-dlp"):
        raise RuntimeError("yt-dlp not found")

    from dlpx.yt_dlp import yt_base
    base = yt_base(cfg or {})
    cmd = base + [
        "-J", "--no-warnings", "--flat-playlist",
        f"ytsearch{max_results}:{query}",
    ]
    r = run_cmd(cmd, check=True)
    data = json.loads(r.stdout)

    results: List[SearchResult] = []
    for entry in data.get("entries", []):
        vid_url = entry.get("url") or entry.get("webpage_url", "")
        if vid_url and not vid_url.startswith("http"):
            vid_url = f"https://www.youtube.com/watch?v={vid_url}"
        title = entry.get("title", "")
        thumb = entry.get("thumbnail", "")
        if not thumb:
            thumbnails = entry.get("thumbnails")
            if thumbnails:
                thumb = thumbnails[0].get("url", "")
        dur_secs = entry.get("duration")
        duration = ""
        if dur_secs:
            m, s = divmod(int(dur_secs), 60)
            duration = f"{m}:{s:02d}"
        if vid_url and title:
            results.append(SearchResult(
                title=title,
                url=vid_url,
                thumbnail=thumb,
                duration=duration,
                source="youtube",
            ))

    return results


def display_search_results(results: List[SearchResult], title: str = "Search Results"):
    """Display search results in a rich table."""
    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    t = Table(title=title)
    t.add_column("#", style="cyan", width=4)
    t.add_column("Title", style="bold")
    t.add_column("Duration", width=10)
    t.add_column("Source", width=12)
    t.add_column("URL", overflow="fold")

    for i, r in enumerate(results, 1):
        t.add_row(str(i), r.title, r.duration or "-", r.source, r.url)

    console.print(t)


def interactive_search(cfg: Optional[Dict[str, Any]] = None):
    """Run an interactive search session."""
    while True:
        query = Prompt.ask("\n[bold]Search query[/bold] (q=quit)").strip()
        if not query or query.lower() in {"q", "quit", "exit"}:
            break

        console.print(f"\n[bold]Search provider:[/bold]")
        console.print("1) jable.tv\n2) YouTube (via yt-dlp)")
        provider = Prompt.ask("Choose provider", default="1").strip()

        with console.status("[bold blue]Searching...[/bold blue]"):
            try:
                if provider == "1":
                    results = search_jable(query)
                elif provider == "2":
                    results = search_youtube(query, cfg=cfg)
                else:
                    console.print("[red]Invalid provider[/red]")
                    continue
            except Exception as e:
                console.print(f"[red]Search failed:[/red] {e}")
                continue

        display_search_results(results, f"Results for '{query}'")

        if not results:
            continue

        while True:
            console.print("\n1) Open result URL\n2) Copy URL\n3) New search\n4) Back")
            action = Prompt.ask("Action", default="3").strip()

            if action == "1":
                idx = Prompt.ask("Result #", default="1").strip()
                if idx.isdigit() and 1 <= int(idx) <= len(results):
                    url = results[int(idx) - 1].url
                    console.print(f"[green]URL:[/green] {url}")
                    return url
                else:
                    console.print("[red]Invalid number[/red]")
            elif action == "2":
                idx = Prompt.ask("Result #", default="1").strip()
                if idx.isdigit() and 1 <= int(idx) <= len(results):
                    url = results[int(idx) - 1].url
                    from dlpx.utils import copy_to_clipboard
                    if copy_to_clipboard(url):
                        console.print("[green]Copied[/green]")
                    else:
                        console.print(f"[green]URL:[/green] {url}")
                else:
                    console.print("[red]Invalid number[/red]")
            elif action == "3":
                break
            elif action == "4":
                return None

    return None
