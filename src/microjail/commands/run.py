import subprocess
from typing import Annotated

import typer

from microjail import policy
from microjail.commands.init import get_project
from microjail.commands.lock import (
    ensure_lockdown,
    load_microjail_or_exit,
)
from microjail.warden import CapabilityPolicyViolation, GatePolicyViolation, Warden


def run(ctx: typer.Context, command: Annotated[list[str], typer.Argument(...)]) -> None:
    project = get_project(ctx)
    microjail = load_microjail_or_exit(project)
    if microjail.workshop_info() is None:
        typer.echo(f"Launching workshop {microjail.name}...")
        microjail.workshop.launch()

    ensure_lockdown(microjail)

    process = microjail.popen(command, interactive=False)
    warden = Warden(microjail, process)
    try:
        exit_code = warden.supervise()
    except GatePolicyViolation as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(policy.RUNTIME_GATE_POLICY_VIOLATION) from exc
    except CapabilityPolicyViolation as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(policy.FATAL_RUNTIME_CAPABILITY_VIOLATION) from exc
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    raise typer.Exit(exit_code)
