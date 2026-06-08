import subprocess
from typing import TYPE_CHECKING, Any

import msgspec

from microjail.adapters import lxc, workshop

if TYPE_CHECKING:
    from microjail.microjail import MicroJail

EGRESS_PROBE = ["bash", "-c", ": >/dev/tcp/1.1.1.1/443"]
EGRESS_PROBE_TIMEOUT = 10


class NetworkDrop(msgspec.Struct):
    """Gate that removes network interfaces from the workshop container."""

    name: str = "network-egress"
    removed_devices: dict[str, dict[str, Any]] = msgspec.field(default_factory=dict)

    def check(self, microjail: MicroJail) -> bool:
        """Return true when egress from inside the workshop is blocked."""
        try:
            result = workshop.exec_(
                microjail.name,
                microjail.project_path,
                EGRESS_PROBE,
                check=False,
                capture_output=True,
                text=True,
                timeout=EGRESS_PROBE_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return True
        return result.returncode != 0

    def enforce(self, microjail: MicroJail) -> None:
        """Remove every network device from the workshop container."""
        container_name, project = self.resolve_container(microjail)
        devices = self.network_devices(microjail)
        self.removed_devices = devices.copy()
        for device in devices:
            lxc.remove_device(container_name, device, project=project)

    def release(self, microjail: MicroJail) -> None:
        """Restore network devices removed by enforce()."""
        if not self.removed_devices:
            return

        container_name, project = self.resolve_container(microjail)
        for device, config in self.removed_devices.items():
            lxc.add_device(container_name, device, config, project=project)
        self.removed_devices = {}

    def resolve_container(self, microjail: MicroJail) -> tuple[str, str]:
        container = workshop.get_container(
            microjail.name, project=microjail.project_path
        )
        if container is None:
            raise workshop.WorkshopNotLaunchedError(
                name=microjail.name, project=microjail.project_path
            )
        return container.name, workshop.lxd_project()

    def network_devices(self, microjail: MicroJail) -> dict[str, dict[str, Any]]:
        container_name, project = self.resolve_container(microjail)
        instance = lxc.get_instance(container_name, project=project)
        return {
            name: config
            for name, config in instance.devices.items()
            if config.get("type") == "nic"
        }
