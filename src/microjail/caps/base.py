from typing import Protocol


class Capability(Protocol):
    """Protocol for microjail capabilities.

    A capability represents functionality intentionally exposed to workloads —
    for example an endpoint proxy, a read-only project mount, or an MCP endpoint.

    Lifecycle::

        check()          # does the capability exist?
        if not present:
            provide()    # create the capability
        check()          # verify provisioning succeeded
    """

    name: str

    def check(self) -> bool: ...

    def provide(self) -> None: ...

    def revoke(self) -> None: ...
