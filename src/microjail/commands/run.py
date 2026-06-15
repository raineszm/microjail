from typing import Annotated

import anyio
import typer

from microjail import policy
from microjail.adapters import workshop
from microjail.commands.init import get_project
from microjail.commands.lock import (
    ensure_lockdown,
    load_microjail_or_exit,
)
from microjail.warden import CapabilityPolicyViolation, GatePolicyViolation, Warden


def run(ctx: typer.Context, command: Annotated[list[str], typer.Argument(...)]) -> None:
    project = get_project(ctx)
    microjail = load_microjail_or_exit(project)

    async def _run() -> None:
        if await microjail.workshop_info() is None:
            typer.echo(f"Launching workshop {microjail.name}...")
            await workshop.launch(microjail.name, project=microjail.project_path)

        await ensure_lockdown(microjail)

        process = await microjail.popen(command, interactive=False)
        warden = Warden(microjail, process)
        try:
            exit_code = await warden.supervise()
        except GatePolicyViolation as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(policy.RUNTIME_GATE_POLICY_VIOLATION) from exc
        except CapabilityPolicyViolation as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(policy.FATAL_RUNTIME_CAPABILITY_VIOLATION) from exc

        raise typer.Exit(exit_code if exit_code is not None else 1)

    anyio.run(_run)
