"""Shared CLI output helpers for microjail commands."""

from typing import NoReturn

import typer


def err(msg: str, code: int = 1) -> NoReturn:
    """Print ``Error: <msg>`` to stderr and exit with *code*."""
    typer.echo(f"Error: {msg}", err=True)
    raise typer.Exit(code)


def warn(msg: str) -> None:
    """Print ``Warning: <msg>`` to stderr without exiting."""
    typer.echo(f"Warning: {msg}", err=True)
