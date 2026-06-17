"""CLI command for microjail validate."""

import msgspec
import typer

from microjail.commands.init import get_project
from microjail.microjail import ConfigNotFoundError, MicroJail


def validate(ctx: typer.Context) -> None:
    """Validate microjail configuration without applying policy."""
    project = get_project(ctx)
    try:
        microjail = MicroJail.load(project)
    except ConfigNotFoundError:
        typer.echo("Not initialized. Run 'microjail init' first.", err=True)
        raise typer.Exit(code=1) from None
    except msgspec.DecodeError as exc:
        typer.echo(f"Config error: {exc}", err=True)
        raise typer.Exit(code=1) from None

    errors = microjail.validate()

    if not errors:
        typer.echo("Configuration is valid.")
        return

    for err in errors:
        typer.echo(f"Error: {err.message}", err=True)
        if err.hint:
            typer.echo(f"  Hint: {err.hint}", err=True)

    raise typer.Exit(code=1)
