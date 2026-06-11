import shutil
import subprocess
import time
from typing import TYPE_CHECKING

import typer

from microjail.adapters import workshop
from microjail.microjail import ConfigNotFoundError, MicroJail

if TYPE_CHECKING:
    from pathlib import Path


def _resolve_state(name: str, project: Path) -> None:
    while True:
        info = workshop.info(name, project)
        if not info:
            break
        if info.status == "pending":
            typer.echo("Workshop is pending, waiting...")
            time.sleep(2)
            continue
        elif info.status == "off":
            typer.echo("Workshop is off, starting before removal...")
            workshop.start(name, project)
            break
        else:
            break


def destroy(
    ctx: typer.Context,
    all: bool = typer.Option(
        False,
        "--all",
        help="Destroy the entire project directory instead of just the purge path",
    ),
    force: bool = typer.Option(
        False,
        "--yes-i-really-mean-it",
        help="Bypass interactive confirmation for --all",
    ),
) -> None:
    project: Path = ctx.obj
    try:
        mj = MicroJail.load(project)
    except ConfigNotFoundError as exc:
        typer.echo(f"Cannot destroy: no microjail config found in {project}", err=True)
        raise typer.Exit(code=1) from exc

    # State resolution
    try:
        _resolve_state(mj.name, project)
        workshop.remove(mj.name, project)
    except subprocess.CalledProcessError as exc:
        typer.echo(f"Infrastructure teardown failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    # Filesystem cleanup
    if all:
        if not force:
            typer.confirm(
                f"Are you sure you want to delete the entire project at {project}?",
                abort=True,
            )
        shutil.rmtree(project)
    elif mj.purge_path:
        purge_dir = project / mj.purge_path
        if purge_dir.exists():
            shutil.rmtree(purge_dir)
