"""CLI command for microjail validate."""

import msgspec
import typer
from rich.panel import Panel

from microjail.commands._output import error, stderr_console, success
from microjail.commands.init import get_project
from microjail.microjail import ConfigNotFoundError, MicroJail


def validate(ctx: typer.Context) -> None:
    """Validate microjail configuration without applying policy."""
    project = get_project(ctx)
    try:
        microjail = MicroJail.load(project)
    except ConfigNotFoundError:
        error("Not initialized. Run 'microjail init' first.")
        raise typer.Exit(code=1) from None
    except msgspec.DecodeError as exc:
        error(f"Config error: {exc}")
        raise typer.Exit(code=1) from None

    errors = microjail.validate()

    if not errors:
        success("Configuration is valid.")
        return

    stderr_console.print("[bold]Configuration errors:[/bold]")
    for err in errors:
        body = err.message
        if err.hint:
            body = f"{err.message}\n\n[dim]Hint:[/dim] {err.hint}"
        stderr_console.print(Panel(body, title=err.kind, border_style="red"))

    raise typer.Exit(code=1)
