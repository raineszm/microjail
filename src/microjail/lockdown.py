from dataclasses import dataclass
from typing import TYPE_CHECKING

import msgspec

if TYPE_CHECKING:
    from microjail.caps.base import Capability
    from microjail.gates.base import Gate


@dataclass(frozen=True)
class CapabilityError(Exception):
    """Raised when a capability could not be verified after provisioning."""

    name: str


@dataclass(frozen=True)
class GateError(Exception):
    """Raised when a gate could not be verified after enforcement."""

    name: str


class Lockdown(msgspec.Struct):
    """Orchestrates capability provisioning and gate enforcement.

    Parameters
    ----------
    caps:
        Ordered sequence of capabilities to provision.  Capabilities are
        established before gates so that explicitly allowed functionality is
        in place before broad denial policies are applied.
    gates:
        Ordered sequence of gates to enforce.
    """

    caps: list[Capability]
    gates: list[Gate]

    def ensure(self) -> None:
        """Bring the environment into the desired state.

        To play it safe we add capabilities first, then apply restrictions.
        Failures of capabilities can be configured to be a warning or an error.
        Failure of any gate leads to immediate teardown of state applied here.
        """
        provided_caps: list[Capability] = []
        enforced_gates: list[Gate] = []

        try:
            for cap in self.caps:
                self.ensure_capability(cap, provided_caps)

            for gate in self.gates:
                self.ensure_gate(gate, enforced_gates)
        except Exception:
            self.release_applied(provided_caps, enforced_gates)
            raise

    def release(self) -> None:
        """Explicitly tear down the lockdown in reverse dependency order.

        Errors from individual release/revoke calls are collected and re-raised
        as a group so that every gate and capability gets a chance to clean up.
        """
        errors: list[Exception] = []

        for gate in reversed(self.gates):
            try:
                gate.release()
            except Exception as exc:
                errors.append(exc)

        for cap in reversed(self.caps):
            try:
                cap.revoke()
            except Exception as exc:
                errors.append(exc)

        if errors:
            raise ExceptionGroup("lockdown release failures", errors)

    def release_applied(
        self, provided_caps: list[Capability], enforced_gates: list[Gate]
    ) -> None:
        """Tear down only state that this ensure() call attempted to apply."""
        errors: list[Exception] = []

        for gate in reversed(enforced_gates):
            try:
                gate.release()
            except Exception as exc:
                errors.append(exc)

        for cap in reversed(provided_caps):
            try:
                cap.revoke()
            except Exception as exc:
                errors.append(exc)

        if errors:
            raise ExceptionGroup("lockdown release failures", errors)

    def ensure_capability(
        self, cap: Capability, provided_caps: list[Capability]
    ) -> None:
        """check → provide if missing → verify for a single capability."""
        if not cap.check():
            provided_caps.append(cap)
            cap.provide()
            if not cap.check():
                raise CapabilityError(name=cap.name)

    def ensure_gate(self, gate: Gate, enforced_gates: list[Gate]) -> None:
        """check → enforce if unsatisfied → verify for a single gate."""
        if not gate.check():
            enforced_gates.append(gate)
            gate.enforce()
            if not gate.check():
                raise GateError(name=gate.name)
