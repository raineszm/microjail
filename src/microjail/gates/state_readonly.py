"""Gate: verify that the readonly=true LXD device for state.json is active.

The protection mechanism is a named disk device (``microjail-state-ro``) added
by ``lock_egress`` that bind-mounts ``.microjail/state.json`` into the
container with ``readonly=true``.  This gate verifies the device is present
and active by inspecting ``lxc config device show`` output.

We do NOT use ``lxc exec -- test -w <path>`` because that probes filesystem
permissions, not the LXD device configuration — an administrator could have
set permissions independently and the mount could still be writable at the
LXD layer.
"""

import subprocess
from typing import TYPE_CHECKING

from microjail.gates import GateResult, resolve_project

if TYPE_CHECKING:
    from pathlib import Path

_STATE_RO_DEVICE = "microjail-state-ro"


def check_state_readonly(container_name: str, workspace: Path) -> GateResult:
    """Return a :class:`~microjail.gates.GateResult` confirming state.json is readonly.

    Queries ``lxc config device show <container>`` and confirms that a device
    named ``microjail-state-ro`` with ``readonly: "true"`` (or ``true``) is
    present.  ``workspace`` identifies the state file path for use in error
    messages and future ``source`` path verification.
    """
    state_path = workspace / ".microjail" / "state.json"
    project, err_result = resolve_project("state-readonly")
    if err_result is not None:
        return err_result
    assert project is not None

    result = subprocess.run(
        [
            "lxc",
            "--project",
            project,
            "config",
            "device",
            "show",
            container_name,
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return GateResult(
            name="state-readonly",
            passed=False,
            message=(
                f"Cannot query devices for container '{container_name}': "
                f"{result.stderr.decode().strip()}."
            ),
        )

    output = result.stdout.decode()
    if _STATE_RO_DEVICE not in output:
        return GateResult(
            name="state-readonly",
            passed=False,
            message=(
                f"Readonly state.json device ('{_STATE_RO_DEVICE}') is not present "
                f"on container '{container_name}'. "
                "The state file is writable from inside the container. "
                "This indicates lock_egress did not complete successfully."
            ),
        )

    # Check that the device block contains readonly: true
    # Parse the relevant section.
    in_device = False
    for line in output.splitlines():
        if line.startswith(_STATE_RO_DEVICE):
            in_device = True
            continue
        if in_device:
            # A new top-level key means we've left the device block.
            if line and not line.startswith(" "):
                break
            if "readonly" in line and ("true" in line.lower()):
                return GateResult(
                    name="state-readonly",
                    passed=True,
                    message=(
                        f"State file is protected: '{_STATE_RO_DEVICE}' device "
                        f"with readonly=true is active on container '{container_name}'."
                    ),
                )

    return GateResult(
        name="state-readonly",
        passed=False,
        message=(
            f"Device '{_STATE_RO_DEVICE}' is present but readonly=true is not set "
            f"on container '{container_name}'. "
            f"The state file '{state_path}' may be writable from inside the container."
        ),
    )
