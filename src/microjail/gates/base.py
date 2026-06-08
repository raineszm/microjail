from typing import Protocol


class Gate(Protocol):
    """Protocol for microjail gates.

    A gate represents a restriction that must hold while a workload executes.
    Concrete gate implementations cover things like denying network access,
    hiding host secrets, or dropping dangerous Linux capabilities.

    Lifecycle::

        check()          # is the restriction currently satisfied?
        if not satisfied:
            enforce()    # establish the restriction
        check()          # verify enforcement succeeded
    """

    name: str

    def check(self) -> bool: ...

    def enforce(self) -> None: ...

    def release(self) -> None: ...
