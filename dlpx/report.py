#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from rich.console import Console

from dlpx.config import DEFAULT_REPORT_DIR
from dlpx.utils import JobResult, now_iso

console = Console()


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
        json.dump(data, f, indent=2)
    console.print(f"[green]Report saved:[/green] {p}")
