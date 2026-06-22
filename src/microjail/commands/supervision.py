import subprocess

import typer

from microjail import policy
from microjail.adapters.lxc import lxd_local_connect
from microjail.adapters.lxd_events import LxdEventWatcher
from microjail.commands._output import error
from microjail.warden import GatePolicyViolation, Warden


def supervise_workload(microjail, process: subprocess.Popen) -> None:
    """Start the LXD event watcher and run the Warden until the workload exits."""
    watcher = LxdEventWatcher(
        container_name=microjail.container_name(),
        lxd_project=microjail.lxd_project(),
        connect=lxd_local_connect,
    )
    watcher.start()
    warden = Warden(microjail, process, events=watcher.events, watcher=watcher)
    try:
        exit_code = warden.supervise()
    except GatePolicyViolation as exc:
        error(str(exc))
        raise typer.Exit(policy.RUNTIME_GATE_POLICY_VIOLATION) from exc
    finally:
        watcher.stop()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    raise typer.Exit(exit_code)
