import subprocess
from typing import TYPE_CHECKING

import typer

from microjail import policy
from microjail.warden import CapabilityPolicyViolation, GatePolicyViolation, Warden

if TYPE_CHECKING:
    from microjail.microjail import MicroJail


def supervise_workload(microjail: MicroJail, process: subprocess.Popen) -> None:
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
