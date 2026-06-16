from typing import TYPE_CHECKING
from unittest.mock import Mock, PropertyMock, call

import pytest

from microjail.adapters.workshop import Workshop
from microjail.caps.endpoint import WorkshopEndpointCapability
from microjail.lockdown import Lockdown
from microjail.microjail import MicroJail

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def microjail(tmp_path: Path) -> MicroJail:
    return MicroJail(
        workshop=Workshop(name="mj-workshop", project=tmp_path),
        lockdown=Lockdown(caps=[], gates=[]),
    )


def cap(name: str, host_endpoint: str) -> WorkshopEndpointCapability:
    return WorkshopEndpointCapability(name=name, host_endpoint=host_endpoint)


def test_provide_calls_adapter_sequence_in_order(
    monkeypatch: pytest.MonkeyPatch, microjail: MicroJail
) -> None:
    capability = cap("inference", "127.0.0.1:8080")
    t = Mock()
    t.connections.return_value = []
    r = Mock()
    monkeypatch.setattr(Workshop, "tunnel", PropertyMock(return_value=t))
    monkeypatch.setattr(Workshop, "refresh", r)

    capability.provide(microjail)

    assert t.mock_calls == [
        call.connections(),
        call.add_plug("inference", "127.0.0.1:8080"),
        call.add_slot("inference", "127.0.0.1:8080"),
        call.connect(
            plug_sdk="microjail", plug="inference", slot_sdk="system", slot="inference"
        ),
    ]
    r.assert_called_once()


def test_provide_passes_container_endpoint_to_plug_and_host_endpoint_to_slot(
    monkeypatch: pytest.MonkeyPatch, microjail: MicroJail
) -> None:
    capability = WorkshopEndpointCapability(
        name="inference",
        host_endpoint="127.0.0.1:8080",
        container_endpoint="10.0.0.1:9090",
    )
    t = Mock()
    t.connections.return_value = []
    r = Mock()
    monkeypatch.setattr(Workshop, "tunnel", PropertyMock(return_value=t))
    monkeypatch.setattr(Workshop, "refresh", r)

    capability.provide(microjail)

    assert t.mock_calls == [
        call.connections(),
        call.add_plug("inference", "10.0.0.1:9090"),
        call.add_slot("inference", "127.0.0.1:8080"),
        call.connect(
            plug_sdk="microjail", plug="inference", slot_sdk="system", slot="inference"
        ),
    ]
    r.assert_called_once()


def test_revoke_calls_adapter_sequence_in_order(
    monkeypatch: pytest.MonkeyPatch, microjail: MicroJail
) -> None:
    capability = cap("inference", "127.0.0.1:8080")
    t = Mock()
    t.remove_plug.return_value = True
    r = Mock()
    monkeypatch.setattr(Workshop, "tunnel", PropertyMock(return_value=t))
    monkeypatch.setattr(Workshop, "refresh", r)

    capability.revoke(microjail)

    assert t.mock_calls == [
        call.disconnect(
            plug_sdk="microjail", plug="inference", slot_sdk="system", slot="inference"
        ),
        call.remove_plug("inference"),
        call.remove_slot("inference", remove_sdk=False),
    ]
    r.assert_called_once()


def test_check_parses_workshop_connections_column_positions(
    monkeypatch: pytest.MonkeyPatch, microjail: MicroJail
) -> None:
    capability = cap("inference", "127.0.0.1:8080")
    t = Mock()
    t.connections.return_value = [
        ("mj-workshop/microjail:inference", "mj-workshop/system:inference"),
        ("mj-workshop/microjail:other", "mj-workshop/system:other"),
    ]
    t.endpoint_reachable.return_value = True
    monkeypatch.setattr(Workshop, "tunnel", PropertyMock(return_value=t))

    assert capability.check(microjail)

    t.endpoint_reachable.assert_called_once_with("127.0.0.1", "8080")
