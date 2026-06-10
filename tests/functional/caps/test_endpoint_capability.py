from typing import TYPE_CHECKING
from unittest.mock import Mock, call

import pytest

from microjail.adapters import workshop
from microjail.caps.endpoint import WorkshopEndpointCapability
from microjail.lockdown import Lockdown
from microjail.microjail import MicroJail

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def microjail(tmp_path: Path) -> MicroJail:
    return MicroJail(
        name="mj-workshop",
        project_path=tmp_path,
        lockdown=Lockdown(caps=[], gates=[]),
    )


def cap(name: str, host_endpoint: str) -> WorkshopEndpointCapability:
    return WorkshopEndpointCapability(name=name, host_endpoint=host_endpoint)


def test_provide_calls_adapter_sequence_in_order(
    monkeypatch: pytest.MonkeyPatch, microjail: MicroJail
) -> None:
    capability = cap("inference", "127.0.0.1:8080")
    parent = Mock()
    monkeypatch.setattr(workshop, "connections", Mock(return_value=[]))
    monkeypatch.setattr(workshop, "add_tunnel_plug", parent.add_tunnel_plug)
    monkeypatch.setattr(workshop, "add_tunnel_slot", parent.add_tunnel_slot)
    monkeypatch.setattr(workshop, "refresh", parent.refresh)
    monkeypatch.setattr(workshop, "connect", parent.connect)

    capability.provide(microjail)

    assert parent.mock_calls == [
        call.add_tunnel_plug(microjail.project_path, "inference", "127.0.0.1:8080"),
        call.add_tunnel_slot(
            microjail.name, microjail.project_path, "inference", "127.0.0.1:8080"
        ),
        call.refresh(microjail.name, project=microjail.project_path),
        call.connect(
            microjail.name,
            project=microjail.project_path,
            plug_sdk="microjail",
            plug="inference",
            slot_sdk="system",
            slot="inference",
        ),
    ]


def test_provide_passes_container_endpoint_to_plug_and_host_endpoint_to_slot(
    monkeypatch: pytest.MonkeyPatch, microjail: MicroJail
) -> None:
    capability = WorkshopEndpointCapability(
        name="inference",
        host_endpoint="127.0.0.1:8080",
        container_endpoint="10.0.0.1:9090",
    )
    parent = Mock()
    monkeypatch.setattr(workshop, "connections", Mock(return_value=[]))
    monkeypatch.setattr(workshop, "add_tunnel_plug", parent.add_tunnel_plug)
    monkeypatch.setattr(workshop, "add_tunnel_slot", parent.add_tunnel_slot)
    monkeypatch.setattr(workshop, "refresh", parent.refresh)
    monkeypatch.setattr(workshop, "connect", parent.connect)

    capability.provide(microjail)

    assert parent.mock_calls == [
        call.add_tunnel_plug(microjail.project_path, "inference", "10.0.0.1:9090"),
        call.add_tunnel_slot(
            microjail.name, microjail.project_path, "inference", "127.0.0.1:8080"
        ),
        call.refresh(microjail.name, project=microjail.project_path),
        call.connect(
            microjail.name,
            project=microjail.project_path,
            plug_sdk="microjail",
            plug="inference",
            slot_sdk="system",
            slot="inference",
        ),
    ]


def test_revoke_calls_adapter_sequence_in_order(
    monkeypatch: pytest.MonkeyPatch, microjail: MicroJail
) -> None:
    capability = cap("inference", "127.0.0.1:8080")
    parent = Mock()
    monkeypatch.setattr(workshop, "disconnect", parent.disconnect)
    monkeypatch.setattr(workshop, "remove_tunnel_plug", parent.remove_tunnel_plug)
    monkeypatch.setattr(workshop, "remove_tunnel_slot", parent.remove_tunnel_slot)
    monkeypatch.setattr(workshop, "refresh", parent.refresh)
    parent.remove_tunnel_plug.return_value = True

    capability.revoke(microjail)

    assert parent.mock_calls == [
        call.disconnect(
            microjail.name,
            project=microjail.project_path,
            plug_sdk="microjail",
            plug="inference",
            slot_sdk="system",
            slot="inference",
        ),
        call.remove_tunnel_plug(microjail.project_path, "inference"),
        call.remove_tunnel_slot(
            microjail.name, microjail.project_path, "inference", remove_sdk=False
        ),
        call.refresh(microjail.name, project=microjail.project_path),
    ]


@pytest.mark.parametrize(
    ("remove_plug_result", "expected_sdks"),
    [
        (False, ["direnv"]),
        (True, ["direnv", "project-microjail"]),
    ],
)
def test_revoke_preserves_or_removes_project_microjail_entry(
    monkeypatch: pytest.MonkeyPatch,
    microjail: MicroJail,
    remove_plug_result: bool,
    expected_sdks: list[str],
) -> None:
    capability = cap("inference", "127.0.0.1:8080")
    workshop_yaml = {"sdks": ["direnv", "project-microjail"]}

    monkeypatch.setattr(workshop, "disconnect", Mock())
    monkeypatch.setattr(
        workshop, "remove_tunnel_plug", Mock(return_value=remove_plug_result)
    )
    monkeypatch.setattr(
        workshop, "read_workshop_yaml", Mock(return_value=workshop_yaml)
    )

    def remove_tunnel_slot(_: str, __: Path, ___: str, remove_sdk: bool) -> None:
        if remove_sdk and "project-microjail" in workshop_yaml["sdks"]:
            workshop_yaml["sdks"].remove("project-microjail")
        if not remove_sdk and "project-microjail" not in workshop_yaml["sdks"]:
            workshop_yaml["sdks"].append("project-microjail")

    monkeypatch.setattr(workshop, "remove_tunnel_slot", remove_tunnel_slot)
    monkeypatch.setattr(workshop, "refresh", Mock())

    capability.revoke(microjail)

    assert workshop_yaml["sdks"] == expected_sdks


def test_check_parses_workshop_connections_column_positions(
    monkeypatch: pytest.MonkeyPatch, microjail: MicroJail
) -> None:
    capability = cap("inference", "127.0.0.1:8080")
    output = "\n".join(
        [
            "INTERFACE  PLUG                             SLOT                           NOTES",
            f"{'tunnel':<11}{'mj-workshop/microjail:inference':<33}{'mj-workshop/system:inference':<31}manual with spaces",
            f"{'tunnel':<11}{'mj-workshop/microjail:other':<33}{'mj-workshop/system:other':<31}ignored",
        ]
    )
    monkeypatch.setattr(
        workshop.subprocess,
        "run",
        Mock(return_value=Mock(stdout=output)),
    )
    monkeypatch.setattr(workshop, "endpoint_reachable", Mock(return_value=True))

    assert capability.check(microjail)

    workshop.endpoint_reachable.assert_called_once_with(microjail, "127.0.0.1", "8080")


def test_provide_does_not_duplicate_project_microjail_entry(
    monkeypatch: pytest.MonkeyPatch, microjail: MicroJail
) -> None:
    first = cap("inference-a", "127.0.0.1:8080")
    second = cap("inference-b", "127.0.0.1:8081")
    workshop_yaml = {"sdks": ["direnv"]}
    sdk_yaml = {"name": "microjail", "plugs": {}}

    monkeypatch.setattr(workshop, "connections", Mock(return_value=[]))
    monkeypatch.setattr(workshop, "read_microjail_sdk", Mock(return_value=sdk_yaml))
    monkeypatch.setattr(
        workshop, "read_workshop_yaml", Mock(return_value=workshop_yaml)
    )

    def write_microjail_sdk(_: Path, __: dict[str, object]) -> None:
        return None

    def write_workshop_yaml(_: str, __: Path, data: dict[str, object]) -> None:
        workshop_yaml.clear()
        workshop_yaml.update(data)

    def add_tunnel_plug(_: Path, __: str, ___: str) -> None:
        sdk_yaml["plugs"]["inference-a"] = {
            "interface": "tunnel",
            "endpoint": "127.0.0.1:8080",
        }
        sdk_yaml["plugs"]["inference-b"] = {
            "interface": "tunnel",
            "endpoint": "127.0.0.1:8081",
        }

    def add_tunnel_slot(_: str, __: Path, ___: str, ____: str) -> None:
        if "project-microjail" not in workshop_yaml["sdks"]:
            workshop_yaml["sdks"].append("project-microjail")

    monkeypatch.setattr(workshop, "write_microjail_sdk", write_microjail_sdk)
    monkeypatch.setattr(workshop, "write_workshop_yaml", write_workshop_yaml)
    monkeypatch.setattr(workshop, "refresh", Mock())
    monkeypatch.setattr(workshop, "connect", Mock())
    monkeypatch.setattr(workshop, "add_tunnel_plug", add_tunnel_plug)
    monkeypatch.setattr(workshop, "add_tunnel_slot", add_tunnel_slot)

    first.provide(microjail)
    second.provide(microjail)

    assert workshop_yaml["sdks"].count("project-microjail") == 1
