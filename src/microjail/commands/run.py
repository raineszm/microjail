from typing import Annotated

import typer

from microjail.commands.init import get_project
from microjail.commands.lock import (
    ensure_lockdown,
    load_microjail_or_exit,
)
from microjail.commands.supervision import supervise_workload


def run(ctx: typer.Context, command: Annotated[list[str], typer.Argument(...)]) -> None:
    project = get_project(ctx)
    microjail = load_microjail_or_exit(project)
    if microjail.workshop_info() is None:
        typer.echo(f"Launching workshop {microjail.name}...")
        microjail.workshop.launch()

    ensure_lockdown(microjail)

    process = microjail.popen(command, interactive=False)
    supervise_workload(microjail, process)
