"""Tests for ``WorkshopEndpointCapability`` against an in-memory workshop stub.

The capability interacts with a real ``Workshop`` (subprocess) in
production. For these unit tests we substitute a hand-rolled
``FakeTunnel`` that exposes the same ``tunnel`` surface and records
state in plain Python data structures. ``FakeWorkshop`` is a subclass
of ``Workshop`` whose ``tunnel`` and ``refresh`` methods are overridden
to use the fake.

Assertions are on the recorded state (plugs, slots, connections,
reachability) — not on call counts to mocked methods.
"""

from pathlib import Path  # noqa: TC003
from typing import cast

from microjail.adapters.workshop import TunnelInterface, Workshop
from microjail.caps.endpoint import WorkshopEndpointCapability
from microjail.lockdown import Lockdown
from microjail.microjail import MicroJail


class FakeTunnel:
    """In-memory stand-in for ``TunnelInterface``."""

    def __init__(self, workshop_name: str) -> None:
        self.workshop_name = workshop_name
        self.plugs: dict[str, str] = {}
        self.slots: dict[str, str] = {}
        self.connections_list: list[tuple[str, str, str, str]] = []
        self.reachable: bool = False

    def add_plug(self, plug_name: str, endpoint: str) -> None:
        self.plugs[plug_name] = endpoint

    def add_slot(self, slot_name: str, endpoint: str) -> None:
        self.slots[slot_name] = endpoint

    def connect(self, *, plug_sdk: str, plug: str, slot_sdk: str, slot: str) -> None:
        self.connections_list.append((plug_sdk, plug, slot_sdk, slot))

    def disconnect(self, *, plug_sdk: str, plug: str, slot_sdk: str, slot: str) -> None:
        key = (plug_sdk, plug, slot_sdk, slot)
        if key in self.connections_list:
            self.connections_list.remove(key)

    def remove_plug(self, plug_name: str) -> bool:
        self.plugs.pop(plug_name, None)
        return bool(self.plugs)

    def remove_slot(
        self,
        slot_name: str,
        *,
        remove_sdk: bool = False,  # noqa: ARG002
    ) -> None:
        self.slots.pop(slot_name, None)

    def connections(self) -> list[tuple[str, str]]:
        return [
            (
                f"{self.workshop_name}/{plug_sdk}:{plug}",
                f"{self.workshop_name}/{slot_sdk}:{slot}",
            )
            for plug_sdk, plug, slot_sdk, slot in self.connections_list
        ]

    def endpoint_reachable(
        self,
        host: str,  # noqa: ARG002
        port: int | str,  # noqa: ARG002
    ) -> bool:
        return self.reachable


class FakeWorkshop(Workshop):
    """``Workshop`` whose ``tunnel`` and ``refresh`` are stubbed."""

    def __init__(self, name: str, project: Path) -> None:
        super().__init__(name=name, project=project)
        self._tunnel = FakeTunnel(name)
        self.refresh_count = 0

    @property
    def tunnel(self) -> TunnelInterface:
        return self._tunnel  # type: ignore

    def refresh(self) -> None:
        self.refresh_count += 1


def make_microjail(tmp_path: Path) -> MicroJail:
    return MicroJail(
        workshop=FakeWorkshop(name="mj-workshop", project=tmp_path),
        lockdown=Lockdown(caps=[], gates=[]),
    )


def tunnel_of(microjail: MicroJail) -> FakeTunnel:
    """Return the fake tunnel bound to *microjail*'s workshop."""
    return cast("FakeTunnel", microjail.workshop.tunnel)


def test_provide_registers_plug_slot_and_connection(
    tmp_path: Path,
) -> None:
    microjail = make_microjail(tmp_path)
    tunnel = tunnel_of(microjail)
    tunnel.reachable = True
    cap = WorkshopEndpointCapability(name="inference", host_endpoint="127.0.0.1:8080")

    cap.provide(microjail)

    assert tunnel.plugs == {"inference": "127.0.0.1:8080"}
    assert tunnel.slots == {"inference": "127.0.0.1:8080"}
    assert tunnel.connections_list == [
        ("microjail", "inference", "system", "inference")
    ]
    assert cap.check(microjail)


def test_provide_routes_container_endpoint_to_plug(
    tmp_path: Path,
) -> None:
    microjail = make_microjail(tmp_path)
    tunnel = tunnel_of(microjail)
    tunnel.reachable = True
    cap = WorkshopEndpointCapability(
        name="inference",
        host_endpoint="127.0.0.1:8080",
        container_endpoint="10.0.0.1:9090",
    )

    cap.provide(microjail)

    assert tunnel.plugs["inference"] == "10.0.0.1:9090"
    assert tunnel.slots["inference"] == "127.0.0.1:8080"


def test_provide_is_idempotent(tmp_path: Path) -> None:
    microjail = make_microjail(tmp_path)
    tunnel = tunnel_of(microjail)
    tunnel.reachable = True
    cap = WorkshopEndpointCapability(name="inference", host_endpoint="127.0.0.1:8080")

    cap.provide(microjail)
    cap.provide(microjail)

    assert len(tunnel.plugs) == 1
    assert len(tunnel.slots) == 1
    assert len(tunnel.connections_list) == 1


def test_revoke_removes_plug_slot_and_connection(tmp_path: Path) -> None:
    microjail = make_microjail(tmp_path)
    tunnel = tunnel_of(microjail)
    tunnel.reachable = True
    cap = WorkshopEndpointCapability(name="inference", host_endpoint="127.0.0.1:8080")
    cap.provide(microjail)

    cap.revoke(microjail)

    assert tunnel.plugs == {}
    assert tunnel.slots == {}
    assert tunnel.connections_list == []


def test_check_returns_false_when_no_connection(tmp_path: Path) -> None:
    microjail = make_microjail(tmp_path)
    cap = WorkshopEndpointCapability(name="inference", host_endpoint="127.0.0.1:8080")

    assert cap.check(microjail) is False


def test_check_and_verify_behavior_on_reachability(
    tmp_path: Path,
) -> None:
    microjail = make_microjail(tmp_path)
    tunnel = tunnel_of(microjail)
    tunnel.reachable = True
    cap = WorkshopEndpointCapability(name="inference", host_endpoint="127.0.0.1:8080")
    cap.provide(microjail)
    tunnel.reachable = False

    assert cap.check(microjail) is True
    assert cap.verify(microjail) is False
