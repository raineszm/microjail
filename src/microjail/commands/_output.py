"""Console singletons and message helpers for CLI output.

Two module-level Rich consoles resolve ``sys.stdout`` / ``sys.stderr``
lazily, so they pick up the streams set by ``typer.testing.CliRunner`` or
by a redirected process. ANSI is stripped automatically when the stream
is not a TTY, so substring assertions in tests and piped output stay
plain text.
"""

from rich.console import Console

# Wide default so test substrings that span the full message stay intact
# even when Rich can't auto-detect a terminal width (e.g. under
# typer.testing.CliRunner, which substitutes sys.stdout with a non-TTY
# wrapper and causes Rich to fall back to 80 columns).
stdout_console = Console(width=200)
stderr_console = Console(stderr=True, width=200)


def success(message: str) -> None:
    stdout_console.print(f"[green]✓[/green] {message}")


def error(message: str) -> None:
    stderr_console.print(f"[red]✗[/red] error: {message}")


def warning(message: str) -> None:
    stderr_console.print(f"[yellow]⚠[/yellow] warning: {message}")


def info(message: str) -> None:
    stdout_console.print(message)
