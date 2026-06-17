from typing import Annotated

import typer

from microjail.commands.init import get_project
from microjail.commands.lock import (
    ensure_lockdown,
    load_microjail_or_exit,
)
from microjail.commands.supervision import supervise_workload


def exec_command(
    ctx: typer.Context,
    command: Annotated[list[str], typer.Argument(...)],
    interactive: bool = typer.Option(
        False,
        "--interactive/--non-interactive",
        help="Use interactive mode (PTY allocation) or non-interactive mode",
    ),
) -> None:
    project = get_project(ctx)
    microjail = load_microjail_or_exit(project)
    if microjail.workshop_info() is None:
        typer.echo(f"Launching workshop {microjail.name}...")
        microjail.workshop.launch()

    ensure_lockdown(microjail)

    process = microjail.popen(command, interactive=interactive)
    supervise_workload(microjail, process)
