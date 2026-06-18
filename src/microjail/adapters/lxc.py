import subprocess
from dataclasses import dataclass
from typing import Any

import msgspec

from microjail.exceptions import MicrojailError


class LxcCommandError(MicrojailError, subprocess.CalledProcessError):
    """Raised when an ``lxc`` subprocess returns non-zero.

    Carries the command, returncode, and stderr so callers can decide
    whether to fall back, surface the error, or re-raise.
    """

    def __init__(self, cmd: list[str], returncode: int, stderr: str) -> None:
        subprocess.CalledProcessError.__init__(self, returncode, cmd, stderr=stderr)

    def __str__(self) -> str:
        return f"lxc {' '.join(self.cmd)} failed (rc={self.returncode}): {self.stderr.strip()}"


def run_lxc_command(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run *cmd* and raise :class:`LxcCommandError` on non-zero exit."""
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise LxcCommandError(cmd, result.returncode, result.stderr)
    return result


@dataclass(frozen=True)
class InstanceInfo:
    name: str
    devices: dict[str, dict[str, Any]]
    profiles: list[str]


def get_instance(name: str, project: str) -> InstanceInfo:
    result = subprocess.run(
        ["lxc", "query", f"/1.0/instances/{name}?project={project}"],
        check=True,
        capture_output=True,
    )
    raw = msgspec.json.decode(result.stdout)
    return InstanceInfo(
        name=raw["name"],
        devices=raw.get("expanded_devices", raw.get("devices", {})),
        profiles=raw.get("profiles", []),
    )


def get_profile_devices(name: str, project: str) -> dict[str, dict[str, Any]]:
    result = subprocess.run(
        ["lxc", "query", f"/1.0/profiles/{name}?project={project}"],
        check=True,
        capture_output=True,
    )
    raw = msgspec.json.decode(result.stdout)
    return raw.get("devices", {})


def attach_network(network: str, container: str, project: str) -> None:
    """Attach a managed *network* to *container* in *project*.

    *network* is resolved in the default project; *project* scopes the
    container reference. This is the standard cross-project attach
    pattern: a managed network in ``default`` is visible to other
    projects whose ``features.networks`` is ``false`` (e.g. the workshop
    project).

    The device name is left for LXD to choose (typically ``eth0``).
    """
    run_lxc_command(
        ["lxc", "network", "attach", network, container, "--project", project]
    )


def remove_device(container: str, device: str, project: str) -> None:
    subprocess.run(
        ["lxc", "--project", project, "config", "device", "remove", container, device],
        check=True,
    )


def add_device(
    container: str, device: str, config: dict[str, Any], project: str
) -> None:
    subprocess.run(
        [
            "lxc",
            "--project",
            project,
            "config",
            "device",
            "add",
            container,
            device,
            config["type"],
            *[f"{key}={value}" for key, value in config.items() if key != "type"],
        ],
        check=True,
    )


def stop_instance(name: str, project: str, force: bool = False) -> None:
    cmd = ["lxc", "--project", project, "stop", name]
    if force:
        cmd.append("--force")
    subprocess.run(cmd, check=True)
