from typing import Annotated

import typer

from microjail.commands.lock import (
    ensure_lockdown,
    load_microjail_or_exit,
)


def run(command: Annotated[list[str], typer.Argument(...)]) -> None:
    microjail = load_microjail_or_exit()
    ensure_lockdown(microjail)

    result = microjail.exec_(command, check=False)
    raise typer.Exit(result.returncode)
