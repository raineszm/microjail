from dataclasses import dataclass
from typing import Any

import anyio
import msgspec


@dataclass(frozen=True)
class InstanceInfo:
    name: str
    devices: dict[str, dict[str, Any]]
    profiles: list[str]


async def get_instance(name: str, project: str) -> InstanceInfo:
    result = await anyio.run_process(
        ["lxc", "query", f"/1.0/instances/{name}?project={project}"],
    )
    raw = msgspec.json.decode(result.stdout)
    return InstanceInfo(
        name=raw["name"],
        devices=raw.get("expanded_devices", raw.get("devices", {})),
        profiles=raw.get("profiles", []),
    )


async def get_profile_devices(name: str, project: str) -> dict[str, dict[str, Any]]:
    result = await anyio.run_process(
        ["lxc", "query", f"/1.0/profiles/{name}?project={project}"],
    )
    raw = msgspec.json.decode(result.stdout)
    return raw.get("devices", {})


async def remove_device(container: str, device: str, project: str) -> None:
    await anyio.run_process(
        ["lxc", "--project", project, "config", "device", "remove", container, device],
    )


async def add_device(
    container: str, device: str, config: dict[str, Any], project: str
) -> None:
    await anyio.run_process(
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
    )


async def stop_instance(name: str, project: str, force: bool = False) -> None:
    cmd = ["lxc", "--project", project, "stop", name]
    if force:
        cmd.append("--force")
    await anyio.run_process(cmd)


class NetworkConfig(msgspec.Struct):
    ipv4_address: str = msgspec.field(name="ipv4.address", default="")
    ipv6_address: str = msgspec.field(name="ipv6.address", default="")


class NetworkInfo(msgspec.Struct):
    name: str
    type: str
    config: NetworkConfig


async def get_network(name: str) -> NetworkInfo:
    """Return LXD network information for the given network name."""
    result = await anyio.run_process(
        ["lxc", "query", f"/1.0/networks/{name}"],
    )
    return msgspec.json.decode(result.stdout, type=NetworkInfo)
