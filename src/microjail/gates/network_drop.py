import subprocess
from typing import TYPE_CHECKING, Any

import msgspec

from microjail.adapters.lxc import LxcCommandError
from microjail.exceptions import MicrojailError
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
        """Return true when egress from inside the workshop is blocked.

        Returns ``False`` when the restriction cannot be evaluated against
        the current state (for example, the workshop has not been launched,
        or no workshop exists in the project). This matches the contract
        used by :class:`ReadonlyConfig` and lets callers iterate over all
        gates to answer "is the lockdown currently applied?" without
        special-casing each failure mode.
        """
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
        except MicrojailError:
            return False
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

        The recovery branch is chosen by the state of the container:

        * If :attr:`removed_devices` is non-empty (the normal case
          after :meth:`enforce` ran), replay those devices directly.
        * Otherwise, re-add any nic devices from the LXD profile that
          are missing from the container.
        * If the profile has no nics, attach :data:`DEFAULT_NETWORK` to
          give the container *some* interface. If that fails (e.g. the
          bridge is gone), fall back to ``workshop restore``, which
          works at a higher level when LXD-level recovery is
          impossible.
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
