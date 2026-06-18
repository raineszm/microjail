from dataclasses import dataclass

import msgspec

# These types are needed at runtime by msgspec
from microjail.caps.base import Capability  # noqa: TC001
from microjail.exceptions import MicrojailError
from microjail.gates.base import Gate  # noqa: TC001
from microjail.gates.network_drop import NetworkDrop
from microjail.gates.readonly_config import ReadonlyConfig


@dataclass(frozen=True)
class CapabilityError(MicrojailError):
    """Raised when a capability could not be verified after provisioning."""

    name: str


@dataclass(frozen=True)
class GateError(MicrojailError):
    """Raised when a gate could not be verified after enforcement."""

    name: str


@dataclass(frozen=True)
class CapabilityReleaseError(MicrojailError):
    """Raised when a capability could not be revoked."""

    name: str


@dataclass(frozen=True)
class GateReleaseError(MicrojailError):
    """Raised when a gate could not be released."""

    name: str


class Lockdown(msgspec.Struct):
    """Policy describing capabilities to provide and gates to enforce."""

    caps: list[Capability]
    gates: list[Gate]

    @classmethod
    def default(cls) -> Lockdown:
        return cls(caps=[], gates=[NetworkDrop(), ReadonlyConfig()])
