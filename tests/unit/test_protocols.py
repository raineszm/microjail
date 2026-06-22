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


def test_gate_protocol_declares_verify() -> None:
    assert "verify" in Gate.__dict__


def test_capability_protocol_declares_verify() -> None:
    assert "verify" in Capability.__dict__


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
