"""End-to-end tests for WorkshopEndpointCapability against a real Workshop.

Verifies the core spec requirement: after ``provide()``, the declared
``host:port`` is TCP-reachable from inside the container.
"""

from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from microjail import policy
from microjail.adapters import workshop
from microjail.caps.endpoint import WorkshopEndpointCapability
from microjail.cli import app
from microjail.lockdown import Lockdown
from microjail.microjail import (
    ApplicationIntent,
    ApplicationStatus,
    MicroJail,
)
from tests._helpers import (
    SharedWorkshop,
    has_network_egress,
)
from tests._helpers import (
    host_tcp_listener as shared_host_tcp_listener,
)
from tests.marks import requires_lxd, requires_workshop

if TYPE_CHECKING:
    from collections.abc import Generator

pytestmark = [
    requires_lxd(),
    requires_workshop(),
]


@pytest.fixture(scope="function")
def host_tcp_listener() -> Generator[tuple[str, int]]:
    yield from shared_host_tcp_listener()


@pytest.fixture(scope="function")
def endpoint_microjail(
    endpoint_e2e_workshop: SharedWorkshop,
    host_tcp_listener: tuple[str, int],
) -> MicroJail:
    """A saved MicroJail config with one endpoint capability."""
    host, port = host_tcp_listener
    mj = MicroJail(
        name=endpoint_e2e_workshop.name,
        project_path=endpoint_e2e_workshop.path,
        lockdown=Lockdown(
            caps=[
                WorkshopEndpointCapability(
                    name="tcp-svc",
                    host_endpoint=f"{host}:{port}",
                )
            ],
            gates=Lockdown.default().gates,
        ),
    )
    mj.save()
    return mj


async def test_provide_makes_endpoint_reachable(
    endpoint_microjail: MicroJail,
    host_tcp_listener: tuple[str, int],
) -> None:
    """After ``provide()`` the endpoint is TCP-reachable from inside the container."""
    host, port = host_tcp_listener
    cap = endpoint_microjail.lockdown.caps[0]

    assert not await cap.check(endpoint_microjail)

    await cap.provide(endpoint_microjail)

    assert await cap.check(endpoint_microjail)
    assert await workshop.endpoint_reachable(endpoint_microjail, host, str(port))


async def test_lockdown_application_applies_endpoint_capability(
    endpoint_microjail: MicroJail,
    host_tcp_listener: tuple[str, int],
) -> None:
    """Lockdown application provides the endpoint capability and the tunnel survives
    the network-egress Gate applied by the same run intent."""
    host, port = host_tcp_listener

    result = await endpoint_microjail.ensure(ApplicationIntent.RUN)

    assert result.status is ApplicationStatus.SUCCESS

    assert await workshop.endpoint_reachable(endpoint_microjail, host, str(port))


async def test_run_with_endpoint_capability_reaches_declared_endpoint_and_blocks_other_egress(
    endpoint_microjail: MicroJail,
    host_tcp_listener: tuple[str, int],
) -> None:
    ws = SharedWorkshop(
        name=endpoint_microjail.name, path=endpoint_microjail.project_path
    )
    host, port = host_tcp_listener
    if not has_network_egress(ws):
        pytest.skip("workshop lacks baseline network egress")

    result = CliRunner().invoke(
        app,
        [
            "run",
            "--",
            "bash",
            "-c",
            f": >/dev/tcp/{host}/{port} && touch /project/endpoint-ok",
        ],
    )

    assert result.exit_code == 0, result.stderr
    assert (endpoint_microjail.project_path / "endpoint-ok").exists()
    assert await workshop.endpoint_reachable(endpoint_microjail, host, str(port))
    assert not has_network_egress(ws)


def test_run_does_not_start_workload_when_endpoint_capability_cannot_be_applied(
    e2e_workshop: SharedWorkshop,
) -> None:
    mj = MicroJail(
        name=e2e_workshop.name,
        project_path=e2e_workshop.path,
        lockdown=Lockdown(
            caps=[
                WorkshopEndpointCapability(
                    name="bad-endpoint", host_endpoint="not-an-endpoint"
                )
            ],
            gates=Lockdown.default().gates,
        ),
    )
    mj.save()

    result = CliRunner().invoke(
        app,
        ["run", "--", "sh", "-c", "touch /project/started"],
    )

    assert result.exit_code == policy.CAPABILITY_APPLICATION_FAILURE
    assert not (e2e_workshop.path / "started").exists()


def test_unlock_revokes_declared_endpoint_capability(
    endpoint_microjail: MicroJail,
    host_tcp_listener: tuple[str, int],
) -> None:
    host, port = host_tcp_listener

    result = CliRunner().invoke(app, ["run", "--", "true"])
    assert result.exit_code == 0, result.stderr
    assert workshop.endpoint_reachable(endpoint_microjail, host, str(port))

    result = CliRunner().invoke(app, ["unlock"])
    assert result.exit_code == 0, result.stderr
    assert not workshop.endpoint_reachable(endpoint_microjail, host, str(port))
