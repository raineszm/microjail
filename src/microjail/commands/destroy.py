import subprocess
from typing import TYPE_CHECKING

import typer

from microjail.microjail import ConfigNotFoundError, MicroJail

if TYPE_CHECKING:
    from pathlib import Path


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

    if all and not force:
        typer.confirm(
            f"Are you sure you want to delete the entire project at {project}?",
            abort=True,
        )

    try:
        mj.destroy(delete_project=all, echo=typer.echo)
    except subprocess.CalledProcessError as exc:
        typer.echo(f"Infrastructure teardown failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
