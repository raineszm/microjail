"""End-to-end tests for WorkshopEndpointCapability against a real Workshop.

Verifies the core spec requirement: after ``provide()``, the declared
``host:port`` is TCP-reachable from inside the container.
"""

import socket
import threading
import time
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


ENDPOINT_PROBE_RETRIES = 3
ENDPOINT_PROBE_DELAY = 1.0


def _find_free_port() -> int:
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(host: str, port: int, timeout: float = 5.0) -> bool:
    """Block until *host:port* accepts connections, or *timeout* elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except TimeoutError, ConnectionRefusedError:
            time.sleep(0.1)
    return False


@pytest.fixture(scope="function")
def host_echo_server() -> Generator[tuple[str, int]]:
    """A TCP echo server on a random localhost port.  Yields ``(host, port)``.

    The server accepts one connection at a time and echoes back whatever it
    receives.  This is lightweight and proves the tunnel is forwarding real
    TCP traffic, not just completing a handshake.
    """
    port = _find_free_port()

    def handle(client: socket.socket) -> None:
        try:
            with client:
                data = client.recv(1024)
                if data:
                    client.sendall(data)
        except OSError:
            pass

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", port))
    server.listen(1)
    server.settimeout(1.0)

    def serve() -> None:
        while True:
            try:
                client, _ = server.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            t = threading.Thread(target=handle, args=(client,), daemon=True)
            t.start()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()

    if not _wait_for_server("127.0.0.1", port):
        server.close()
        thread.join(timeout=2)
        pytest.fail(f"echo server did not start on 127.0.0.1:{port}")

    try:
        yield ("127.0.0.1", port)
    finally:
        server.close()
        thread.join(timeout=5)


def _endpoint_reachable_with_retry(mj: MicroJail, host: str, port: str) -> bool:
    """Call ``endpoint_reachable`` with retries — tunnels may take a moment."""
    for _ in range(ENDPOINT_PROBE_RETRIES):
        if workshop.endpoint_reachable(mj, host, port):
            return True
        time.sleep(ENDPOINT_PROBE_DELAY)
    return False


# ------------------------------------------------------------------


def test_provide_makes_endpoint_reachable(
    e2e_workshop: SharedWorkshop,
    host_echo_server: tuple[str, int],
) -> None:
    """After ``provide()`` the endpoint is TCP-reachable from inside the container."""
    host, port = host_echo_server
    endpoint = f"{host}:{port}"

    mj = MicroJail(
        name=e2e_workshop.name,
        project_path=e2e_workshop.path,
        lockdown=Lockdown(
            caps=[WorkshopEndpointCapability(name="echo-svc", endpoint=endpoint)],
            gates=Lockdown.default().gates,
        ),
    )
    mj.save()
    cap = mj.lockdown.caps[0]

    # Before provide, the endpoint should not be reachable.
    assert not cap.check(mj)

    cap.provide(mj)

    # After provide, check() must return True …
    assert cap.check(mj)
    # … and the endpoint must actually accept a TCP connection.
    assert _endpoint_reachable_with_retry(mj, host, str(port))


def test_ensure_applies_endpoint_capability(
    e2e_workshop: SharedWorkshop,
    host_echo_server: tuple[str, int],
) -> None:
    """``ensure()`` provides the endpoint capability and the tunnel survives the
    network-egress gate applied by the same ``ensure()`` call."""
    host, port = host_echo_server
    endpoint = f"{host}:{port}"

    mj = MicroJail(
        name=e2e_workshop.name,
        project_path=e2e_workshop.path,
        lockdown=Lockdown(
            caps=[WorkshopEndpointCapability(name="echo-svc", endpoint=endpoint)],
            gates=Lockdown.default().gates,
        ),
    )
    mj.save()

    mj.ensure()

    # Tunnel must be reachable even after the network-egress gate has
    # dropped all NICs (capabilities are applied before gates).
    assert _endpoint_reachable_with_retry(mj, host, str(port))
