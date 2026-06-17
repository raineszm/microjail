import subprocess
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


def test_check_returns_true_when_connection_and_reachability_hold(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    cap = capability()
    mock_tunnel = Mock()
    mock_tunnel.connections.return_value = [
        ("mj-workshop/microjail:inference", "mj-workshop/system:inference"),
    ]
    mock_tunnel.endpoint_reachable.return_value = True
    monkeypatch.setattr(Workshop, "tunnel", PropertyMock(return_value=mock_tunnel))

    assert cap.check(tmp_microjail)

    mock_tunnel.endpoint_reachable.assert_called_once_with("127.0.0.1", "8080")


def test_check_returns_false_when_endpoint_is_unreachable(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    cap = capability()
    mock_tunnel = Mock()
    mock_tunnel.connections.return_value = [
        ("mj-workshop/microjail:inference", "mj-workshop/system:inference"),
    ]
    mock_tunnel.endpoint_reachable.return_value = False
    monkeypatch.setattr(Workshop, "tunnel", PropertyMock(return_value=mock_tunnel))

    assert not cap.check(tmp_microjail)

    mock_tunnel.endpoint_reachable.assert_called_once_with("127.0.0.1", "8080")


def test_check_returns_false_when_connections_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    cap = capability()
    mock_tunnel = Mock()
    mock_tunnel.connections.side_effect = subprocess.CalledProcessError(
        returncode=1, cmd=["workshop", "connections"]
    )
    monkeypatch.setattr(Workshop, "tunnel", PropertyMock(return_value=mock_tunnel))

    assert not cap.check(tmp_microjail)


def test_check_returns_false_when_reachability_times_out(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    cap = capability()
    mock_tunnel = Mock()
    mock_tunnel.connections.return_value = [
        ("mj-workshop/microjail:inference", "mj-workshop/system:inference"),
    ]
    mock_tunnel.endpoint_reachable.side_effect = subprocess.TimeoutExpired(
        cmd=["bash"], timeout=5
    )
    monkeypatch.setattr(Workshop, "tunnel", PropertyMock(return_value=mock_tunnel))

    assert not cap.check(tmp_microjail)


def test_check_returns_false_on_invalid_endpoint(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    cap = WorkshopEndpointCapability(name="inference", host_endpoint="invalid-no-port")
    mock_tunnel = Mock()
    mock_tunnel.connections.return_value = [
        ("mj-workshop/microjail:inference", "mj-workshop/system:inference"),
    ]
    monkeypatch.setattr(Workshop, "tunnel", PropertyMock(return_value=mock_tunnel))

    assert not cap.check(tmp_microjail)


def test_check_probes_container_endpoint_when_set(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    cap = WorkshopEndpointCapability(
        name="inference",
        host_endpoint="127.0.0.1:8080",
        container_endpoint="10.0.0.1:9090",
    )
    mock_tunnel = Mock()
    mock_tunnel.connections.return_value = [
        ("mj-workshop/microjail:inference", "mj-workshop/system:inference"),
    ]
    mock_tunnel.endpoint_reachable.return_value = True
    monkeypatch.setattr(Workshop, "tunnel", PropertyMock(return_value=mock_tunnel))

    assert cap.check(tmp_microjail)

    mock_tunnel.endpoint_reachable.assert_called_once_with("10.0.0.1", "9090")


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
