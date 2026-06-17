import subprocess
from typing import TYPE_CHECKING, Any

import msgspec

from microjail.adapters.lxc import LxcCommandError
from microjail.policy import EGRESS_PROBE_TIMEOUT

if TYPE_CHECKING:
    from microjail.microjail import MicroJail

EGRESS_PROBE = ["bash", "-c", ": >/dev/tcp/1.1.1.1/443"]
DEFAULT_NETWORK = "workshopbr0"


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
        """Restore network devices removed by enforce().

        Tries, in order: recorded state, the LXD profile, and finally a
        fresh attach of :data:`DEFAULT_NETWORK`. The attach itself can
        fail (e.g. the bridge is gone); in that case we hand off to
        ``workshop restore`` as a last resort, which still works when
        LXD-level recovery is impossible.
        """
        if self.removed_devices:
            for device, config in self.removed_devices.items():
                microjail.add_device(device, config)
            self.removed_devices = {}
            return

        profile_devices = microjail.profile_devices()
        devices = {
            name: config
            for name, config in profile_devices.items()
            if config.get("type") == "nic"
        }
        if not devices:
            try:
                microjail.attach_network(DEFAULT_NETWORK)
            except LxcCommandError:
                microjail.restore_workshop()
            return

        current_devices = microjail.lxc_instance().devices
        for device, config in devices.items():
            if device not in current_devices:
                microjail.add_device(device, config)
        self.removed_devices = {}
