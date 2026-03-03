#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

console = Console()

_SESSION_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

JABLE_BASE = "https://jable.tv"


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
    """Scrape jable.tv search results for the given query."""
    encoded = quote_plus(query)
    url = f"{JABLE_BASE}/search/{encoded}/"
    if page > 1:
        url = f"{JABLE_BASE}/search/{encoded}/?mode=async&function=get_block&block_id=list_videos_videos_list_search_result&q={encoded}&sort_by=&from={page}"

    session = _get_session()
    resp = session.get(url, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    results: List[SearchResult] = []

    video_items = soup.select("div.video-img-box")
    if not video_items:
        video_items = soup.select("div.col-6.col-sm-4.col-lg-3")
    if not video_items:
        video_items = soup.select("div.item")

    for item in video_items:
        a_tag = item.select_one("a[href]")
        if not a_tag:
            continue
        href = a_tag.get("href", "")
        if not href:
            continue
        link = urljoin(JABLE_BASE, href)

        img_tag = item.select_one("img")
        thumb = ""
        if img_tag:
            thumb = img_tag.get("data-src", "") or img_tag.get("src", "")

        title_el = item.select_one("h6.title a") or item.select_one(".title a") or a_tag
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            title = a_tag.get("title", "") or href.rstrip("/").rsplit("/", 1)[-1]

        dur_el = item.select_one(".duration") or item.select_one(".label")
        duration = dur_el.get_text(strip=True) if dur_el else ""

        if link and title:
            results.append(SearchResult(
                title=title,
                url=link,
                thumbnail=thumb,
                duration=duration,
                source="jable.tv",
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


def interactive_search():
    """Run an interactive search session."""
    while True:
        query = Prompt.ask("\n[bold]Search query[/bold] (q=quit)").strip()
        if not query or query.lower() in {"q", "quit", "exit"}:
            break

        console.print(f"\n[bold]Search provider:[/bold]")
        console.print("1) jable.tv")
        provider = Prompt.ask("Choose provider", default="1").strip()

        with console.status("[bold blue]Searching...[/bold blue]"):
            if provider == "1":
                results = search_jable(query)
            else:
                console.print("[red]Invalid provider[/red]")
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
