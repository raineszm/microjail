from typing import TYPE_CHECKING

import msgspec

from microjail.adapters import lxc, workshop

if TYPE_CHECKING:
    from microjail.microjail import MicroJail

DEVICE_NAME = "microjail-config-ro"
CONTAINER_CONFIG_PATH = "/project/.microjail/config.yaml"


class ReadonlyConfig(msgspec.Struct):
    """Gate that bind-mounts the microjail config read-only inside the container."""

    name: str = "readonly-config"
    removed: bool = False

    def check(self, microjail: MicroJail) -> bool:
        """Return True when the config bind-mount device is present with readonly=true."""
        container = workshop.get_container(
            microjail.name, project=microjail.project_path
        )
        if container is None:
            return False
        instance = lxc.get_instance(container.name, project=workshop.lxd_project())
        device = instance.devices.get(DEVICE_NAME)
        if device is None:
            return False
        return device.get("readonly") == "true"

    def enforce(self, microjail: MicroJail) -> None:
        """Add a read-only disk device covering the microjail config file."""
        container_name, project = self.resolve_container(microjail)
        lxc.add_device(
            container_name,
            DEVICE_NAME,
            {
                "type": "disk",
                "source": str(microjail.config_path),
                "path": CONTAINER_CONFIG_PATH,
                "readonly": "true",
            },
            project=project,
        )
        self.removed = True

    def release(self, microjail: MicroJail) -> None:
        """Remove the read-only disk device added by enforce()."""
        if not self.removed:
            return
        container_name, project = self.resolve_container(microjail)
        lxc.remove_device(container_name, DEVICE_NAME, project=project)
        self.removed = False

    def resolve_container(self, microjail: MicroJail) -> tuple[str, str]:
        container = workshop.get_container(
            microjail.name, project=microjail.project_path
        )
        if container is None:
            raise workshop.WorkshopNotLaunchedError(
                name=microjail.name, project=microjail.project_path
            )
        return container.name, workshop.lxd_project()
