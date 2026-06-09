from typing import TYPE_CHECKING

import msgspec

from microjail.adapters import workshop

if TYPE_CHECKING:
    from microjail.microjail import MicroJail


class WorkshopEndpointCapability(
    msgspec.Struct, tag="endpoint-proxy", tag_field="type"
):
    name: str
    endpoint: str

    @property
    def type(self) -> str:
        return "endpoint-proxy"

    def check(self, microjail: MicroJail) -> bool:
        try:
            rows = workshop.connections(microjail.name, project=microjail.project_path)
            if (
                f"{microjail.name}/microjail:{self.name}",
                f"{microjail.name}/system:{self.name}",
            ) not in rows:
                return False
            host, port = self.endpoint.rsplit(":", 1)
            return workshop.endpoint_reachable(microjail, host, port)
        except Exception:
            return False

    def provide(self, microjail: MicroJail) -> None:
        if self.check(microjail):
            return
        workshop.add_tunnel_plug(microjail.project_path, self.name, self.endpoint)
        workshop.add_tunnel_slot(
            microjail.name, microjail.project_path, self.name, self.endpoint
        )
        workshop.refresh(microjail.name, project=microjail.project_path)
        workshop.connect(
            microjail.name,
            project=microjail.project_path,
            plug_sdk="microjail",
            plug=self.name,
            slot_sdk="system",
            slot=self.name,
        )

    def revoke(self, microjail: MicroJail) -> None:
        workshop.disconnect(
            microjail.name,
            project=microjail.project_path,
            plug_sdk="microjail",
            plug=self.name,
            slot_sdk="system",
            slot=self.name,
        )
        remaining = workshop.remove_tunnel_plug(microjail.project_path, self.name)
        workshop.remove_tunnel_slot(
            microjail.name,
            microjail.project_path,
            self.name,
            remove_sdk=not remaining,
        )
        workshop.refresh(microjail.name, project=microjail.project_path)
