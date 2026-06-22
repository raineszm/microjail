import re
import subprocess
from typing import TYPE_CHECKING

import msgspec

if TYPE_CHECKING:
    from microjail.adapters.workshop import TunnelBatch
    from microjail.microjail import MicroJail


ENDPOINT_NAME_RE = re.compile(r"^[a-zA-Z][-a-zA-Z0-9]*$")
SIMPLE_HOST_RE = re.compile(r"^[a-zA-Z0-9.-]+$")


def validate_endpoint_name(name: str) -> str | None:
    """Return an error message if *name* is not a valid Endpoint name, or None."""
    if not ENDPOINT_NAME_RE.match(name):
        return (
            f"invalid endpoint name '{name}': must start with a letter, "
            "followed by letters, digits, or hyphens"
        )
    return None


def validate_endpoint_address(address: str) -> str | None:
    """Return an error message if *address* is not a valid HOST:PORT, or None."""
    if ":" not in address:
        return (
            f"invalid endpoint address '{address}': missing port (expected HOST:PORT)"
        )

    host, port_str = address.rsplit(":", 1)

    if not host:
        return f"invalid endpoint address '{address}': empty host"

    if "/" in host or " " in host or ":" in host:
        return f"invalid endpoint address '{address}': host contains invalid characters"

    if not SIMPLE_HOST_RE.match(host):
        return f"invalid endpoint address '{address}': host contains invalid characters"

    try:
        port = int(port_str)
    except ValueError:
        return f"invalid endpoint address '{address}': port is not an integer"

    if port < 1 or port > 65535:
        return f"invalid endpoint address '{address}': port out of range (1-65535)"

    return None


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
        """Return true when the tunnel connection is present in the Workshop SDK."""
        try:
            t = microjail.workshop.tunnel
            rows = t.connections()
        except subprocess.CalledProcessError, subprocess.TimeoutExpired:
            return False
        return (
            f"{microjail.name}/microjail:{self.name}",
            f"{microjail.name}/system:{self.name}",
        ) in rows

    def verify(self, microjail: MicroJail) -> bool:
        """Return true when the resolved endpoint is TCP-reachable."""
        try:
            t = microjail.workshop.tunnel
            host, port = self.resolved_endpoint.rsplit(":", 1)
            return t.endpoint_reachable(host, port)
        except subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError:
            return False

    def provide(self, microjail: MicroJail, batch: TunnelBatch | None = None) -> None:
        if self.check(microjail):
            return
        t = microjail.workshop.tunnel
        t.add_plug(self.name, self.resolved_endpoint)
        t.add_slot(self.name, self.host_endpoint)
        if batch is not None:
            batch.mark_dirty()
            batch.defer_connect(
                plug_sdk="microjail",
                plug=self.name,
                slot_sdk="system",
                slot=self.name,
            )
        else:
            microjail.workshop.refresh()
            t.connect(
                plug_sdk="microjail",
                plug=self.name,
                slot_sdk="system",
                slot=self.name,
            )

    def revoke(self, microjail: MicroJail, batch: TunnelBatch | None = None) -> None:
        t = microjail.workshop.tunnel
        t.disconnect(
            plug_sdk="microjail", plug=self.name, slot_sdk="system", slot=self.name
        )
        remaining = t.remove_plug(self.name)
        t.remove_slot(self.name, remove_sdk=not remaining)
        if batch is not None:
            batch.mark_dirty()
        else:
            microjail.workshop.refresh()
