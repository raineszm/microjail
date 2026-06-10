from typing import Annotated

import typer

from microjail.commands.lock import (
    ensure_lockdown_for_run_or_exit,
    load_microjail_or_exit,
)


def run(command: Annotated[list[str], typer.Argument(...)]) -> None:
    microjail = load_microjail_or_exit()
    ensure_lockdown_for_run_or_exit(microjail)

    result = microjail.exec_(command, check=False)
    raise typer.Exit(result.returncode)
