"""CLI command for microjail status."""

import typer

from microjail.commands.init import get_project
from microjail.microjail import ConfigNotFoundError, MicroJail


def status(ctx: typer.Context) -> None:
    """Show microjail and workshop status."""
    project = get_project(ctx)
    try:
        microjail = MicroJail.load(project)
    except ConfigNotFoundError:
        typer.echo("Not initialized. Run 'microjail init' first.")
        raise typer.Exit(code=0) from None

    result = microjail.status()

    typer.echo(f"Workshop: {result.workshop_name} ({result.workshop_status})")

    if result.capabilities:
        typer.echo("Capabilities:")
        for cap in result.capabilities:
            typer.echo(f"  - {cap}")

    if result.gates:
        typer.echo("Gates:")
        for gate in result.gates:
            typer.echo(f"  - {gate}")

    if result.connections:
        typer.echo("Tunnel connections:")
        for plug, slot in result.connections:
            typer.echo(f"  {plug} <-> {slot}")
