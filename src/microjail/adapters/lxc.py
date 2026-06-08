import subprocess
from dataclasses import dataclass
from typing import Any

import msgspec


@dataclass(frozen=True)
class InstanceInfo:
    name: str
    devices: dict[str, dict[str, Any]]


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
