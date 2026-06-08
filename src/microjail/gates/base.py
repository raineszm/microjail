from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from microjail.microjail import MicroJail


@runtime_checkable
class Gate(Protocol):
    """Protocol for microjail gates.

    A gate represents a restriction that must hold while a workload executes.
    Concrete gate implementations cover things like denying network access,
    hiding host secrets, or dropping dangerous Linux capabilities.

    Lifecycle::

        check(microjail)          # is the restriction currently satisfied?
        if not satisfied:
            enforce(microjail)    # establish the restriction
        check(microjail)          # verify enforcement succeeded
    """

    name: str

    def check(self, microjail: MicroJail) -> bool: ...

    def enforce(self, microjail: MicroJail) -> None: ...

    def release(self, microjail: MicroJail) -> None: ...
