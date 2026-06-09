import subprocess
from typing import TYPE_CHECKING, Any

import msgspec

if TYPE_CHECKING:
    from microjail.microjail import MicroJail

EGRESS_PROBE = ["bash", "-c", ": >/dev/tcp/1.1.1.1/443"]
EGRESS_PROBE_TIMEOUT = 10


class NetworkDrop(msgspec.Struct, tag="network-egress", tag_field="name"):
    """Gate that removes network interfaces from the workshop container."""

    removed_devices: dict[str, dict[str, Any]] = msgspec.field(default_factory=dict)

    @property
    def name(self) -> str:
        return "network-egress"

    def check(self, microjail: MicroJail) -> bool:
        """Return true when egress from inside the workshop is blocked."""
        try:
            result = microjail.exec_(
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
        instance = microjail.lxc_instance()
        devices = {
            name: config
            for name, config in instance.devices.items()
            if config.get("type") == "nic"
        }
        self.removed_devices = devices.copy()
        for device in devices:
            microjail.remove_device(device)

    def release(self, microjail: MicroJail) -> None:
        """Restore network devices removed by enforce()."""
        if not self.removed_devices:
            return

        for device, config in self.removed_devices.items():
            microjail.add_device(device, config)
        self.removed_devices = {}
