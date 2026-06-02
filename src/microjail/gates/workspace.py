"""Gate: verify that the workspace directory is bind-mounted inside the container.

Workshop bind-mounts the user's workspace into the container automatically.
This gate confirms the mount is present and at the expected path so the
workload is guaranteed to see the same files that were provisioned.
"""

import subprocess
from typing import TYPE_CHECKING

from microjail.gates import GateResult
from microjail.lxd.network import _workshop_project

if TYPE_CHECKING:
    from pathlib import Path


def check_workspace_mounted(container_name: str, workspace: Path) -> GateResult:
    """Return a :class:`~microjail.gates.GateResult` confirming the workspace is mounted.

    Queries ``lxc config device show <container>`` and inspects the disk
    devices for one whose ``source`` matches the workspace path.  A purely
    filesystem check (``lxc exec -- ls``) would pass even if the mount was
    stale; inspecting device config is the more reliable observable.
    """
    try:
        project = _workshop_project()
    except RuntimeError as exc:
        return GateResult(
            name="workspace-mounted",
            passed=False,
            message=(
                f"Cannot determine LXD project to check workspace mount: {exc}. "
                "Ensure Workshop and LXD are running."
            ),
        )

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
            name="workspace-mounted",
            passed=False,
            message=(
                f"Cannot query devices for container '{container_name}': "
                f"{result.stderr.decode().strip()}. "
                f"Is the container running? Run 'workshop status' to check."
            ),
        )

    workspace_str = str(workspace)
    output = result.stdout.decode()
    if workspace_str in output:
        return GateResult(
            name="workspace-mounted",
            passed=True,
            message=f"Workspace '{workspace_str}' is mounted inside the container.",
        )

    return GateResult(
        name="workspace-mounted",
        passed=False,
        message=(
            f"Workspace '{workspace_str}' is not mounted inside container "
            f"'{container_name}'. "
            "The environment may have been recreated without the workspace mount. "
            "Run 'microjail init --force' to reinitialise."
        ),
    )
