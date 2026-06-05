"""Gate: verify that network egress is actually down inside the container.

Probes from inside the container to a well-known external IP address (8.8.8.8)
and expects the probe to fail.  Confirming the actual network state — not just
trusting the return code of the ``lock_egress`` call — satisfies constitution
Principles I and II (safety first; correctness over confidence).
"""

import subprocess

from microjail.gates import GateResult, resolve_project

_PROBE_HOST = "8.8.8.8"
_PROBE_TIMEOUT = "3"  # seconds, as string for ping -W


def check_egress_down(container_name: str) -> GateResult:
    """Return a :class:`~microjail.gates.GateResult` confirming egress is severed.

    Runs ``ping -c 1 -W 3 8.8.8.8`` inside the container via ``lxc exec``
    through the Workshop LXD project.  A non-zero exit code (ping failed to
    reach the host) means egress is down — which is what we want.

    A *zero* exit code means egress is still reachable and the gate fails.
    """
    project, err_result = resolve_project("egress-down")
    if err_result is not None:
        return err_result
    assert project is not None

    result = subprocess.run(
        [
            "lxc",
            "--project",
            project,
            "exec",
            container_name,
            "--",
            "ping",
            "-c",
            "1",
            "-W",
            _PROBE_TIMEOUT,
            _PROBE_HOST,
        ],
        capture_output=True,
        check=False,
    )

    if result.returncode == 0:
        # Ping succeeded — egress is still reachable.  Gate FAILS.
        return GateResult(
            name="egress-down",
            passed=False,
            message=(
                f"Egress is still reachable from container '{container_name}' "
                f"(probe to {_PROBE_HOST} succeeded). "
                "Network isolation was not applied correctly. "
                "Check LXD device configuration for the container."
            ),
        )

    # Ping failed — egress is down.  Gate PASSES.
    return GateResult(
        name="egress-down",
        passed=True,
        message=f"Egress confirmed down: probe to {_PROBE_HOST} failed as expected.",
    )
