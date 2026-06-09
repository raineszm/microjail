from typing import TYPE_CHECKING

import msgspec

from microjail.adapters.workshop import WorkshopNotLaunchedError

if TYPE_CHECKING:
    from microjail.microjail import MicroJail

DEVICE_NAME = "microjail-config-ro"
CONTAINER_CONFIG_PATH = "/project/.microjail/config.yaml"


class ReadonlyConfig(msgspec.Struct, tag="readonly-config", tag_field="name"):
    """Gate that bind-mounts the microjail config read-only inside the container."""

    removed: bool = False

    @property
    def name(self) -> str:
        return "readonly-config"

    def check(self, microjail: MicroJail) -> bool:
        """Return True when the config bind-mount device is present with readonly=true."""
        try:
            instance = microjail.lxc_instance()
        except WorkshopNotLaunchedError:
            return False
        device = instance.devices.get(DEVICE_NAME)
        if device is None:
            return False
        return device.get("readonly") == "true"

    def enforce(self, microjail: MicroJail) -> None:
        """Add a read-only disk device covering the microjail config file."""
        microjail.add_device(
            DEVICE_NAME,
            {
                "type": "disk",
                "source": str(microjail.config_path),
                "path": CONTAINER_CONFIG_PATH,
                "readonly": "true",
            },
        )
        self.removed = True

    def release(self, microjail: MicroJail) -> None:
        """Remove the read-only disk device added by enforce()."""
        if not self.removed:
            return
        microjail.remove_device(DEVICE_NAME)
        self.removed = False
