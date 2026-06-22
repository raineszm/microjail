"""Tests for protocol conformance of Gate and Capability.

The :class:`Gate` and :class:`Capability` protocols gain a :meth:`verify`
method. This module verifies that all concrete implementations satisfy
the protocol surface.
"""

from unittest.mock import Mock

from microjail.caps.base import Capability
from microjail.caps.endpoint import WorkshopEndpointCapability
from microjail.gates.base import Gate
from microjail.gates.network_drop import NetworkDrop
from microjail.gates.readonly_config import ReadonlyConfig


def test_concrete_gates_satisfy_gate_protocol() -> None:
    """Every concrete gate ``isinstance`` is ``Gate`` — runtime protocol check."""
    assert isinstance(NetworkDrop(), Gate)
    assert isinstance(ReadonlyConfig(), Gate)


def test_concrete_capabilities_satisfy_capability_protocol() -> None:
    """Every concrete cap ``isinstance`` is ``Capability`` — runtime protocol check."""
    cap = WorkshopEndpointCapability(
        name="inference",
        host_endpoint="localhost:8080",
    )
    assert isinstance(cap, Capability)


def test_network_drop_verify_returns_true() -> None:
    gate = NetworkDrop()
    assert gate.verify(Mock()) is True


def test_readonly_config_verify_returns_true() -> None:
    gate = ReadonlyConfig()
    assert gate.verify(Mock()) is True


def test_workshop_endpoint_capability_verify_returns_true() -> None:
    cap = WorkshopEndpointCapability(
        name="inference",
        host_endpoint="localhost:8080",
    )
    mock_mj = Mock()
    mock_mj.workshop.tunnel.endpoint_reachable.return_value = True
    assert cap.verify(mock_mj) is True
