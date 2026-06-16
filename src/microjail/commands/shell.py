import sys
from typing import Annotated

import typer

from microjail.commands.init import get_project
from microjail.commands.lock import ensure_lockdown, load_microjail_or_exit
from microjail.commands.supervision import supervise_workload


def stdin_is_tty() -> bool:
    return sys.stdin.isatty()


def stdout_is_tty() -> bool:
    return sys.stdout.isatty()


def shell(
    ctx: typer.Context,
    command: Annotated[list[str] | None, typer.Argument()] = None,
) -> None:
    if not stdin_is_tty() or not stdout_is_tty():
        typer.echo("microjail shell requires an interactive terminal", err=True)
        raise typer.Exit(1)

    project = get_project(ctx)
    microjail = load_microjail_or_exit(project)
    if microjail.workshop_info() is None:
        typer.echo(f"Launching workshop {microjail.name}...")
        microjail.workshop.launch()

    ensure_lockdown(microjail)

    if command:
        process = microjail.popen(command, interactive=True)
    else:
        process = microjail.shell()
    supervise_workload(microjail, process)
