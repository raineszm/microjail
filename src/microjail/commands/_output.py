"""Console singletons and message helpers for CLI output.

Two module-level Rich consoles resolve ``sys.stdout`` / ``sys.stderr``
lazily. The helpers use Rich for color and icons when the destination
is a TTY and fall back to plain ``sys.stdout.write`` /
``sys.stderr.write`` in non-TTY streams (pipes, ``typer.testing.CliRunner``).

The non-TTY fallback matters: when Rich can't auto-detect a terminal
width it falls back to 80 columns, which word-wraps long single-line
messages and inserts newlines mid-string. That breaks substring
assertions in the existing functional tests (e.g. ``"workshop
unavailable" in result.stderr``). Plain ``sys.stderr.write`` doesn't
wrap.
"""

import sys

from rich.console import Console

stdout_console = Console()
stderr_console = Console(stderr=True)


def success(message: str) -> None:
    if stdout_console.is_terminal:
        stdout_console.print(f"[green]✓[/green] {message}")
    else:
        sys.stdout.write(f"✓ {message}\n")
        sys.stdout.flush()


def error(message: str) -> None:
    if stderr_console.is_terminal:
        stderr_console.print(f"[red]✗[/red] error: {message}")
    else:
        sys.stderr.write(f"✗ error: {message}\n")
        sys.stderr.flush()


def warning(message: str) -> None:
    if stderr_console.is_terminal:
        stderr_console.print(f"[yellow]⚠[/yellow] warning: {message}")
    else:
        sys.stderr.write(f"⚠ warning: {message}\n")
        sys.stderr.flush()


def info(message: str) -> None:
    if stdout_console.is_terminal:
        stdout_console.print(message)
    else:
        sys.stdout.write(f"{message}\n")
        sys.stdout.flush()
