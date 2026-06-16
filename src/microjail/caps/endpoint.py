import subprocess
from typing import TYPE_CHECKING

import msgspec

if TYPE_CHECKING:
    from microjail.microjail import MicroJail


class WorkshopEndpointCapability(
    msgspec.Struct, tag="endpoint-tunnel", tag_field="type"
):
    name: str
    host_endpoint: str
    container_endpoint: str | None = None
    fatal: bool = False

    @property
    def type(self) -> str:
        return "endpoint-tunnel"

    @property
    def resolved_endpoint(self) -> str:
        return (
            self.container_endpoint
            if self.container_endpoint is not None
            else self.host_endpoint
        )

    def check(self, microjail: MicroJail) -> bool:
        try:
            t = microjail.workshop.tunnel
            rows = t.connections()
            if (
                f"{microjail.name}/microjail:{self.name}",
                f"{microjail.name}/system:{self.name}",
            ) not in rows:
                return False
            host, port = self.resolved_endpoint.rsplit(":", 1)
            return t.endpoint_reachable(host, port)
        except subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError:
            return False

    def provide(self, microjail: MicroJail) -> None:
        if self.check(microjail):
            return
        t = microjail.workshop.tunnel
        t.add_plug(self.name, self.resolved_endpoint)
        t.add_slot(self.name, self.host_endpoint)
        microjail.workshop.refresh()
        t.connect(
            plug_sdk="microjail", plug=self.name, slot_sdk="system", slot=self.name
        )

    def revoke(self, microjail: MicroJail) -> None:
        t = microjail.workshop.tunnel
        t.disconnect(
            plug_sdk="microjail", plug=self.name, slot_sdk="system", slot=self.name
        )
        remaining = t.remove_plug(self.name)
        t.remove_slot(self.name, remove_sdk=not remaining)
        microjail.workshop.refresh()
