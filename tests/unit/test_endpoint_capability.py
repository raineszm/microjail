from typing import TYPE_CHECKING
from unittest.mock import Mock

import msgspec
import pytest

from microjail.adapters import workshop
from microjail.caps.endpoint import WorkshopEndpointCapability
from microjail.lockdown import Lockdown
from microjail.microjail import MicroJail, dec_hook

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def tmp_microjail(tmp_path: Path) -> MicroJail:
    return MicroJail(
        name="mj-workshop",
        project_path=tmp_path,
        lockdown=Lockdown(caps=[], gates=[]),
    )


def capability() -> WorkshopEndpointCapability:
    return WorkshopEndpointCapability(name="inference", host_endpoint="127.0.0.1:8080")


def test_check_returns_false_when_connection_row_is_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    cap = capability()
    monkeypatch.setattr(
        workshop,
        "connections",
        Mock(return_value=[]),
    )
    monkeypatch.setattr(
        workshop,
        "endpoint_reachable",
        Mock(return_value=True),
    )

    assert not cap.check(tmp_microjail)

    workshop.connections.assert_called_once_with(
        tmp_microjail.name, project=tmp_microjail.project_path
    )
    workshop.endpoint_reachable.assert_not_called()


def test_check_returns_true_when_connection_and_reachability_hold(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    cap = capability()
    monkeypatch.setattr(
        workshop,
        "connections",
        Mock(
            return_value=[
                ("mj-workshop/microjail:inference", "mj-workshop/system:inference")
            ]
        ),
    )
    monkeypatch.setattr(
        workshop,
        "endpoint_reachable",
        Mock(return_value=True),
    )

    assert cap.check(tmp_microjail)

    workshop.connections.assert_called_once_with(
        tmp_microjail.name, project=tmp_microjail.project_path
    )
    workshop.endpoint_reachable.assert_called_once_with(
        tmp_microjail, "127.0.0.1", "8080"
    )


def test_check_returns_false_when_endpoint_is_unreachable(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    cap = capability()
    monkeypatch.setattr(
        workshop,
        "connections",
        Mock(
            return_value=[
                ("mj-workshop/microjail:inference", "mj-workshop/system:inference")
            ]
        ),
    )
    monkeypatch.setattr(
        workshop,
        "endpoint_reachable",
        Mock(return_value=False),
    )

    assert not cap.check(tmp_microjail)

    workshop.endpoint_reachable.assert_called_once_with(
        tmp_microjail, "127.0.0.1", "8080"
    )


def test_check_probes_container_endpoint_when_set(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    cap = WorkshopEndpointCapability(
        name="inference",
        host_endpoint="127.0.0.1:8080",
        container_endpoint="10.0.0.1:9090",
    )
    monkeypatch.setattr(
        workshop,
        "connections",
        Mock(
            return_value=[
                ("mj-workshop/microjail:inference", "mj-workshop/system:inference")
            ]
        ),
    )
    monkeypatch.setattr(
        workshop,
        "endpoint_reachable",
        Mock(return_value=True),
    )

    assert cap.check(tmp_microjail)

    workshop.endpoint_reachable.assert_called_once_with(
        tmp_microjail, "10.0.0.1", "9090"
    )


def test_provide_is_idempotent_when_check_already_returns_true(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    cap = capability()
    monkeypatch.setattr(
        workshop,
        "connections",
        Mock(
            return_value=[
                ("mj-workshop/microjail:inference", "mj-workshop/system:inference")
            ]
        ),
    )
    monkeypatch.setattr(workshop, "endpoint_reachable", Mock(return_value=True))
    add_tunnel_plug = Mock()
    add_tunnel_slot = Mock()
    refresh = Mock()
    connect = Mock()
    monkeypatch.setattr(workshop, "add_tunnel_plug", add_tunnel_plug)
    monkeypatch.setattr(workshop, "add_tunnel_slot", add_tunnel_slot)
    monkeypatch.setattr(workshop, "refresh", refresh)
    monkeypatch.setattr(workshop, "connect", connect)

    cap.provide(tmp_microjail)

    add_tunnel_plug.assert_not_called()
    add_tunnel_slot.assert_not_called()
    refresh.assert_not_called()
    connect.assert_not_called()


def test_revoke_is_idempotent_when_capability_was_never_provided(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    cap = capability()
    disconnect = Mock()
    remove_tunnel_plug = Mock(return_value=True)
    remove_tunnel_slot = Mock()
    refresh = Mock()
    monkeypatch.setattr(workshop, "disconnect", disconnect)
    monkeypatch.setattr(workshop, "remove_tunnel_plug", remove_tunnel_plug)
    monkeypatch.setattr(workshop, "remove_tunnel_slot", remove_tunnel_slot)
    monkeypatch.setattr(workshop, "refresh", refresh)

    cap.revoke(tmp_microjail)

    disconnect.assert_called_once_with(
        tmp_microjail.name,
        project=tmp_microjail.project_path,
        plug_sdk="microjail",
        plug="inference",
        slot_sdk="system",
        slot="inference",
    )
    remove_tunnel_plug.assert_called_once_with(tmp_microjail.project_path, "inference")
    remove_tunnel_slot.assert_called_once_with(
        tmp_microjail.name,
        tmp_microjail.project_path,
        "inference",
        remove_sdk=False,
    )
    refresh.assert_called_once_with(
        tmp_microjail.name, project=tmp_microjail.project_path
    )


def test_config_round_trip_deserializes_endpoint_proxy_capability() -> None:
    raw = b"""name: mj-workshop
project_path: /project
lockdown:
  caps:
    - type: endpoint-proxy
      name: inference
      host_endpoint: localhost:8080
  gates: []
"""

    loaded = msgspec.yaml.decode(raw, type=MicroJail, dec_hook=dec_hook)

    assert isinstance(loaded.lockdown.caps[0], WorkshopEndpointCapability)
    assert loaded.lockdown.caps[0].name == "inference"
    assert loaded.lockdown.caps[0].host_endpoint == "localhost:8080"
    assert loaded.lockdown.caps[0].container_endpoint is None


def test_config_round_trip_deserializes_with_container_endpoint() -> None:
    raw = b"""name: mj-workshop
project_path: /project
lockdown:
  caps:
    - type: endpoint-proxy
      name: inference
      host_endpoint: 127.0.0.1:8080
      container_endpoint: 127.0.0.1:9090
  gates: []
"""

    loaded = msgspec.yaml.decode(raw, type=MicroJail, dec_hook=dec_hook)

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
