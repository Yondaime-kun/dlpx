#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import concurrent.futures
import time
from typing import Dict, Any, List, Optional, Set
from pathlib import Path

from rich.console import Console
from rich.table import Table

from dlpx.utils import JobResult, now_iso, sanitize_filename, run_live
from dlpx.doctor import detect_engine
from dlpx.archive import load_archive, add_archive
from dlpx.report import write_report
from dlpx.yt_dlp import yt_info, yt_parse, yt_smart_pick, yt_download_cmd
from dlpx.gallery_dl import gallery_fetch_items, gallery_download_cmd

console = Console()


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
