"""End-to-end tests for WorkshopEndpointCapability against a real Workshop.

Verifies the core spec requirement: after ``provide()``, the declared
``host:port`` is TCP-reachable from inside the container.
"""

import socket
from typing import TYPE_CHECKING

import pytest

from microjail.adapters import workshop
from microjail.caps.endpoint import WorkshopEndpointCapability
from microjail.lockdown import Lockdown
from microjail.microjail import MicroJail
from tests.marks import requires_lxd, requires_workshop

if TYPE_CHECKING:
    from collections.abc import Generator

    from tests._helpers import SharedWorkshop

pytestmark = [
    requires_lxd(),
    requires_workshop(),
]


@pytest.fixture(scope="function")
def host_tcp_listener() -> Generator[tuple[str, int]]:
    """A localhost TCP listener on a random port. Yields ``(host, port)``.

    ``WorkshopEndpointCapability.check()`` only verifies TCP connectability with
    ``: >/dev/tcp/host/port``. A passive listener is enough for that handshake;
    no accept loop or background thread is needed.
    """
    host = "127.0.0.1"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((host, 0))
        listener.listen(16)
        yield (host, listener.getsockname()[1])


@pytest.fixture(scope="function")
def endpoint_microjail(
    e2e_workshop: SharedWorkshop,
    host_tcp_listener: tuple[str, int],
) -> MicroJail:
    """A saved MicroJail config with one endpoint capability."""
    host, port = host_tcp_listener
    mj = MicroJail(
        name=e2e_workshop.name,
        project_path=e2e_workshop.path,
        lockdown=Lockdown(
            caps=[
                WorkshopEndpointCapability(
                    name="tcp-svc",
                    endpoint=f"{host}:{port}",
                )
            ],
            gates=Lockdown.default().gates,
        ),
    )
    mj.save()
    return mj


def test_provide_makes_endpoint_reachable(
    endpoint_microjail: MicroJail,
    host_tcp_listener: tuple[str, int],
) -> None:
    """After ``provide()`` the endpoint is TCP-reachable from inside the container."""
    host, port = host_tcp_listener
    cap = endpoint_microjail.lockdown.caps[0]

    assert not cap.check(endpoint_microjail)

    cap.provide(endpoint_microjail)

    assert cap.check(endpoint_microjail)
    assert workshop.endpoint_reachable(endpoint_microjail, host, str(port))


def test_ensure_applies_endpoint_capability(
    endpoint_microjail: MicroJail,
    host_tcp_listener: tuple[str, int],
) -> None:
    """``ensure()`` provides the endpoint capability and the tunnel survives the
    network-egress gate applied by the same ``ensure()`` call."""
    host, port = host_tcp_listener

    endpoint_microjail.ensure()

    assert workshop.endpoint_reachable(endpoint_microjail, host, str(port))
