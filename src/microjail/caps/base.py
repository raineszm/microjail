from typing import TYPE_CHECKING, Protocol, runtime_checkable

from microjail.gates.base import VerificationResult  # noqa: TC001

if TYPE_CHECKING:
    from microjail.adapters.workshop import TunnelBatch
    from microjail.microjail import MicroJail


@runtime_checkable
class Capability(Protocol):
    """Protocol for microjail capabilities.

    A capability represents functionality intentionally exposed to workloads —
    for example an endpoint proxy, a read-only project mount, or an MCP endpoint.

    Lifecycle::

        check(microjail)          # does the capability exist?
        if not present:
            provide(microjail)    # create the capability
        check(microjail)          # verify provisioning succeeded
    """

    name: str
    fatal: bool = False

    def check(self, microjail: MicroJail) -> bool: ...

    def provide(
        self, microjail: MicroJail, batch: TunnelBatch | None = None
    ) -> None: ...
    def revoke(
        self, microjail: MicroJail, batch: TunnelBatch | None = None
    ) -> None: ...

    def verify(self, microjail: MicroJail) -> VerificationResult: ...
