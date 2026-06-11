from typing import Annotated

import typer

from microjail.commands.init import get_project
from microjail.commands.lock import (
    ensure_lockdown,
    load_microjail_or_exit,
)


def run(ctx: typer.Context, command: Annotated[list[str], typer.Argument(...)]) -> None:
    project = get_project(ctx)
    microjail = load_microjail_or_exit(project)
    ensure_lockdown(microjail)

    result = microjail.exec_(command, check=False)
    raise typer.Exit(result.returncode)
