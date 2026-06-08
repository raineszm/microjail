from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
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

    def check(self, microjail: MicroJail) -> bool: ...

    def provide(self, microjail: MicroJail) -> None: ...

    def revoke(self, microjail: MicroJail) -> None: ...
