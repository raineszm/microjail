from typing import TYPE_CHECKING
from unittest.mock import Mock, PropertyMock

import msgspec
import pytest

from microjail.adapters.workshop import Workshop
from microjail.caps.endpoint import WorkshopEndpointCapability
from microjail.lockdown import Lockdown
from microjail.microjail import MicroJail, MicroJailConfig, dec_hook

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def tmp_microjail(tmp_path: Path) -> MicroJail:
    return MicroJail(
        workshop=Workshop(name="mj-workshop", project=tmp_path),
        lockdown=Lockdown(caps=[], gates=[]),
    )


def capability() -> WorkshopEndpointCapability:
    return WorkshopEndpointCapability(name="inference", host_endpoint="127.0.0.1:8080")


def test_check_returns_false_when_connection_row_is_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    cap = capability()
    mock_tunnel = Mock()
    mock_tunnel.connections.return_value = []
    monkeypatch.setattr(Workshop, "tunnel", PropertyMock(return_value=mock_tunnel))

    assert not cap.check(tmp_microjail)

    mock_tunnel.connections.assert_called_once()
    mock_tunnel.endpoint_reachable.assert_not_called()


def test_provide_is_idempotent_when_check_already_returns_true(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    cap = capability()
    mock_tunnel = Mock()
    mock_tunnel.connections.return_value = [
        ("mj-workshop/microjail:inference", "mj-workshop/system:inference"),
    ]
    mock_tunnel.endpoint_reachable.return_value = True
    mock_refresh = Mock()
    monkeypatch.setattr(Workshop, "tunnel", PropertyMock(return_value=mock_tunnel))
    monkeypatch.setattr(Workshop, "refresh", mock_refresh)

    cap.provide(tmp_microjail)

    mock_tunnel.add_plug.assert_not_called()
    mock_tunnel.add_slot.assert_not_called()
    mock_refresh.assert_not_called()
    mock_tunnel.connect.assert_not_called()


def test_revoke_is_idempotent_when_capability_was_never_provided(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    cap = capability()
    mock_tunnel = Mock()
    mock_tunnel.remove_plug.return_value = True
    mock_refresh = Mock()
    monkeypatch.setattr(Workshop, "tunnel", PropertyMock(return_value=mock_tunnel))
    monkeypatch.setattr(Workshop, "refresh", mock_refresh)

    cap.revoke(tmp_microjail)

    mock_tunnel.disconnect.assert_called_once_with(
        plug_sdk="microjail",
        plug="inference",
        slot_sdk="system",
        slot="inference",
    )
    mock_tunnel.remove_plug.assert_called_once_with("inference")
    mock_tunnel.remove_slot.assert_called_once_with("inference", remove_sdk=False)
    mock_refresh.assert_called_once()


def test_config_round_trip_deserializes_endpoint_proxy_capability() -> None:
    raw = b"""workshop:
  name: mj-workshop
  project: /project
lockdown:
  caps:
    - type: endpoint-tunnel
      name: inference
      host_endpoint: localhost:8080
  gates: []
"""
    config = msgspec.yaml.decode(raw, type=MicroJailConfig, dec_hook=dec_hook)
    loaded = MicroJail.from_config(config)
    assert isinstance(loaded.lockdown.caps[0], WorkshopEndpointCapability)
    assert loaded.lockdown.caps[0].name == "inference"
    assert loaded.lockdown.caps[0].host_endpoint == "localhost:8080"
    assert loaded.lockdown.caps[0].container_endpoint is None


def test_config_round_trip_deserializes_with_container_endpoint() -> None:
    raw = b"""workshop:
  name: mj-workshop
  project: /project
lockdown:
  caps:
    - type: endpoint-tunnel
      name: inference
      host_endpoint: 127.0.0.1:8080
      container_endpoint: 127.0.0.1:9090
  gates: []
"""
    config = msgspec.yaml.decode(raw, type=MicroJailConfig, dec_hook=dec_hook)
    loaded = MicroJail.from_config(config)
    assert isinstance(loaded.lockdown.caps[0], WorkshopEndpointCapability)
    assert loaded.lockdown.caps[0].name == "inference"
    assert loaded.lockdown.caps[0].host_endpoint == "127.0.0.1:8080"
    assert loaded.lockdown.caps[0].container_endpoint == "127.0.0.1:9090"


def test_resolved_endpoint_returns_container_endpoint_when_set() -> None:
    cap = WorkshopEndpointCapability(
        name="svc", host_endpoint="127.0.0.1:8080", container_endpoint="10.0.0.1:9090"
    )
    assert cap.resolved_endpoint == "10.0.0.1:9090"


def test_resolved_endpoint_returns_host_endpoint_when_container_is_none() -> None:
    cap = WorkshopEndpointCapability(name="svc", host_endpoint="localhost:8080")
    assert cap.resolved_endpoint == "localhost:8080"


def test_endpoint_capability_check_and_verify(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    from microjail.adapters.workshop import Workshop

    # Case 1: check returns True when connection holds, and endpoint_reachable is not called
    cap = capability()
    mock_tunnel = Mock()
    mock_tunnel.connections.return_value = [
        ("mj-workshop/microjail:inference", "mj-workshop/system:inference"),
    ]
    monkeypatch.setattr(Workshop, "tunnel", PropertyMock(return_value=mock_tunnel))
    assert cap.check(tmp_microjail) is True
    mock_tunnel.endpoint_reachable.assert_not_called()

    # Case 2: check returns False when connection is absent
    mock_tunnel.connections.return_value = []
    assert cap.check(tmp_microjail) is False

    # Case 3: verify returns VERIFIED when endpoint is reachable and tunnel is connected
    from microjail.gates.base import VerificationResult

    mock_tunnel.connections.return_value = [
        ("mj-workshop/microjail:inference", "mj-workshop/system:inference"),
    ]
    mock_tunnel.endpoint_reachable.return_value = True
    assert cap.verify(tmp_microjail) == VerificationResult.VERIFIED
    mock_tunnel.endpoint_reachable.assert_called_once_with("127.0.0.1", "8080")

    # Case 4: verify returns FAILED when endpoint is unreachable
    mock_tunnel.endpoint_reachable.reset_mock()
    mock_tunnel.endpoint_reachable.return_value = False
    assert cap.verify(tmp_microjail) == VerificationResult.FAILED

    # Case 5: verify returns FAILED when tunnel is not connected
    mock_tunnel.connections.return_value = []
    assert cap.verify(tmp_microjail) == VerificationResult.FAILED

    # Case 6: verify returns FAILED when reachability probe fails or times out
    mock_tunnel.connections.return_value = [
        ("mj-workshop/microjail:inference", "mj-workshop/system:inference"),
    ]
    mock_tunnel.endpoint_reachable.side_effect = Exception("probe failed")
    assert cap.verify(tmp_microjail) == VerificationResult.FAILED

    # Case 7: verify probes container_endpoint when set
    cap_remapped = WorkshopEndpointCapability(
        name="inference",
        host_endpoint="127.0.0.1:8080",
        container_endpoint="10.0.0.1:9090",
    )
    mock_tunnel.connections.return_value = [
        ("mj-workshop/microjail:inference", "mj-workshop/system:inference"),
    ]
    mock_tunnel.endpoint_reachable.reset_mock()
    mock_tunnel.endpoint_reachable.side_effect = None
    mock_tunnel.endpoint_reachable.return_value = True
    assert cap_remapped.verify(tmp_microjail) == VerificationResult.VERIFIED
    mock_tunnel.endpoint_reachable.assert_called_once_with("10.0.0.1", "9090")
