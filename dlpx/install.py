#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import shlex
import sys
from pathlib import Path

from rich.console import Console

from dlpx.utils import ensure_parent

console = Console()


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


def install_launcher(project_root: Path, scope: str = "user", force: bool = False):
    target = _resolve_install_target(scope)
    ensure_parent(target)

    if target.exists() and not force:
        console.print(f"[yellow]{target} already exists.[/yellow] Use --install-force to overwrite.")
        return

    py = sys.executable or "python3"
    launcher = f"""#!/usr/bin/env sh
# Auto-generated launcher for dlp wrapper
export PYTHONPATH={shlex.quote(str(project_root))}${{PYTHONPATH:+:$PYTHONPATH}}
exec {shlex.quote(py)} -m dlpx "$@"
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
