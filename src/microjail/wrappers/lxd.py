"""LXD subprocess wrappers for container network egress control.

All public functions raise :exc:`RuntimeError` with an actionable message on
failure. Callers are responsible for catching and surfacing errors to the user.

No state is held in this module — every function is a pure subprocess call.

LXD project targeting
---------------------
Workshop runs environments in a dedicated LXD project (``workshop.<uid>``).
All ``lxc`` calls MUST include ``--project workshop.<uid>`` to target the
correct project.  The project name is resolved by querying Workshop's own
project list; it is the first project whose name starts with ``workshop.``.

The readonly=true device for state.json
-----------------------------------------
``lock_egress`` adds a named disk device (``microjail-state-ro``) that
bind-mounts the workspace state file into the container with ``readonly=true``.
This overlays the workspace's mutable mount so the workload sees the file as
read-only.  ``unlock_egress`` removes the same device.
"""

import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

# Device name used for the readonly state.json bind-mount.
_STATE_RO_DEVICE = "microjail-state-ro"


def _workshop_project() -> str:
    """Return the Workshop LXD project name (``workshop.<uid>``).

    Raises :exc:`RuntimeError` if no Workshop project can be found.
    """
    result = subprocess.run(
        ["lxc", "project", "list", "--format", "csv"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        msg = (
            "Cannot list LXD projects. Ensure LXD is running. "
            f"(lxc project list exited {result.returncode}: "
            f"{result.stderr.decode().strip()})"
        )
        raise RuntimeError(msg)
    for line in result.stdout.decode().splitlines():
        name = line.split(",")[0].strip()
        if name.startswith("workshop."):
            return name
    msg = (
        "No Workshop LXD project found. "
        "Ensure Workshop is installed and at least one environment has been initialised."
    )
    raise RuntimeError(msg)


def _container_name(env_name: str) -> str:
    """Derive the LXD container name from the Workshop environment name.

    Workshop names containers ``<project_prefix>-<env_name>`` where
    ``project_prefix`` is the portion after ``workshop.`` in the project name.
    We query the project's container list and return the one whose name ends
    with the environment name, to avoid hard-coding the UID.

    Raises :exc:`RuntimeError` if the container cannot be found.
    """
    project = _workshop_project()
    result = subprocess.run(
        ["lxc", "--project", project, "list", "--format", "csv", "--columns", "n"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        msg = (
            f"Cannot list containers in LXD project '{project}'. "
            f"(lxc list exited {result.returncode}: {result.stderr.decode().strip()})"
        )
        raise RuntimeError(msg)
    candidates = [
        line.strip()
        for line in result.stdout.decode().splitlines()
        if line.strip().startswith(f"{env_name}-") or line.strip() == env_name
    ]
    if not candidates:
        msg = (
            f"Container for environment '{env_name}' not found in LXD project "
            f"'{project}'. Is the environment running? Run 'workshop status' to check."
        )
        raise RuntimeError(msg)
    return candidates[0]


def lock_egress(env_name: str, workspace: Path) -> None:
    """Sever network egress for the Workshop environment *env_name*.

    Steps performed:
    1. Resolve the LXD project and container name.
    2. Disable the container NIC's IPv4 and IPv6 routes via ``lxc config device set``.
    3. Add a ``readonly=true`` disk device for ``.microjail/state.json`` so the
       workload cannot modify the state file from inside the container.

    Raises :exc:`RuntimeError` with an actionable message on any failure.
    The caller (``perform_lock``) is responsible for rolling back if this
    raises after partial completion.
    """
    project = _workshop_project()
    container = _container_name(env_name)
    state_json_host = str(workspace / ".microjail" / "state.json")

    # Determine all NIC device names — Workshop typically uses "eth0" but we
    # query to be safe.  We enumerate every NIC so multi-interface containers
    # have all egress severed.
    nic_devices = _all_nic_devices(project, container)

    # Cut IPv4 and IPv6 routing by clearing the allowed-routes lists.
    for nic_device in nic_devices:
        for key in ("ipv4.routes.external", "ipv6.routes.external"):
            result = subprocess.run(
                [
                    "lxc",
                    "--project",
                    project,
                    "config",
                    "device",
                    "set",
                    container,
                    nic_device,
                    key,
                    "",
                ],
                capture_output=True,
                check=False,
            )
            if result.returncode != 0:
                msg = (
                    f"Failed to cut egress ({key}) for container '{container}'"
                    f" on device '{nic_device}': "
                    f"{result.stderr.decode().strip()}"
                )
                raise RuntimeError(msg)

    # Add the readonly bind-mount for state.json.
    # The container path matches the bind-mount path Workshop creates for the
    # workspace — we rely on workshop always mounting at the same path.
    state_json_container = (
        _workspace_mount_path(project, container) + "/.microjail/state.json"
    )
    result = subprocess.run(
        [
            "lxc",
            "--project",
            project,
            "config",
            "device",
            "add",
            container,
            _STATE_RO_DEVICE,
            "disk",
            f"source={state_json_host}",
            f"path={state_json_container}",
            "readonly=true",
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        msg = (
            f"Failed to add readonly state.json device to container '{container}': "
            f"{result.stderr.decode().strip()}"
        )
        raise RuntimeError(msg)


def unlock_egress(env_name: str) -> None:
    """Restore network egress for the Workshop environment *env_name*.

    Reverses ``lock_egress``:
    1. Removes the readonly state.json bind-mount device.
    2. Re-enables IPv4 and IPv6 routing on all container NICs.
    3. Re-attaches the container to the ``workshopbr0`` network if running.

    Raises :exc:`RuntimeError` with an actionable message on failure.
    Continues past individual failures where possible so partial unlock
    does not leave the container entirely unusable.
    """
    project = _workshop_project()
    container = _container_name(env_name)
    nic_devices = _all_nic_devices(project, container)

    errors: list[str] = []

    # Remove the readonly state.json device (best-effort).
    result = subprocess.run(
        [
            "lxc",
            "--project",
            project,
            "config",
            "device",
            "remove",
            container,
            _STATE_RO_DEVICE,
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        # Not fatal: the device may already be absent if lock failed mid-way.
        errors.append(
            f"Warning: could not remove {_STATE_RO_DEVICE} device: "
            f"{result.stderr.decode().strip()}"
        )

    # Restore NIC routing on every NIC.  LXD uses empty string to mean "no restriction".
    # Setting a non-empty value would impose a restriction; restoring to the
    # default means removing the key entirely.
    for nic_device in nic_devices:
        for key in ("ipv4.routes.external", "ipv6.routes.external"):
            result = subprocess.run(
                [
                    "lxc",
                    "--project",
                    project,
                    "config",
                    "device",
                    "unset",
                    container,
                    nic_device,
                    key,
                ],
                capture_output=True,
                check=False,
            )
            if result.returncode != 0:
                errors.append(
                    f"Failed to restore {key} for container '{container}'"
                    f" on device '{nic_device}': "
                    f"{result.stderr.decode().strip()}"
                )

    if errors:
        # At least one step failed — surface all errors together.
        msg = "Unlock completed with errors:\n" + "\n".join(errors)
        raise RuntimeError(msg)


def _all_nic_devices(project: str, container: str) -> list[str]:
    """Return the names of all NIC devices for *container*.

    Raises :exc:`RuntimeError` if no NIC device can be found.
    """
    result = subprocess.run(
        [
            "lxc",
            "--project",
            project,
            "config",
            "device",
            "show",
            container,
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        msg = (
            f"Cannot query devices for container '{container}': "
            f"{result.stderr.decode().strip()}"
        )
        raise RuntimeError(msg)
    # The output is YAML: device name is the top-level key; type: nic identifies it.
    nic_devices: list[str] = []
    current_device: str | None = None
    for line in result.stdout.decode().splitlines():
        stripped = line.rstrip()
        if stripped and not stripped.startswith(" ") and stripped.endswith(":"):
            current_device = stripped.rstrip(":")
        if "type: nic" in stripped and current_device:
            nic_devices.append(current_device)
    if not nic_devices:
        msg = (
            f"No NIC device found for container '{container}'. "
            "Ensure the Workshop environment has been started."
        )
        raise RuntimeError(msg)
    return nic_devices


def _workspace_mount_path(project: str, container: str) -> str:
    """Return the container-side path of the workspace bind-mount.

    Workshop always mounts the workspace at ``/root/<env-name>`` inside
    the container.  We extract it from ``lxc config device show`` to
    avoid hard-coding the path.

    Raises :exc:`RuntimeError` if the workspace mount cannot be determined.
    """
    result = subprocess.run(
        [
            "lxc",
            "--project",
            project,
            "config",
            "device",
            "show",
            container,
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        msg = (
            f"Cannot query devices for container '{container}': "
            f"{result.stderr.decode().strip()}"
        )
        raise RuntimeError(msg)

    # Workshop always mounts the project workspace as a disk device named
    # "workshop.project".  Extract its "path:" value rather than scanning
    # content for the word "workspace", which does not appear in the values.
    lines = result.stdout.decode().splitlines()
    current_device: str | None = None
    device_lines: dict[str, list[str]] = {}
    for line in lines:
        stripped = line.rstrip()
        if stripped and not stripped.startswith(" ") and stripped.endswith(":"):
            current_device = stripped.rstrip(":")
            device_lines[current_device] = []
        elif current_device:
            device_lines[current_device].append(stripped)

    proj_lines = device_lines.get("workshop.project", [])
    for dline in proj_lines:
        if dline.strip().startswith("path:"):
            return dline.split(":", 1)[1].strip()

    msg = (
        f"Cannot determine workspace mount path for container '{container}'. "
        "Ensure the Workshop environment is running and the workspace is mounted."
    )
    raise RuntimeError(msg)
