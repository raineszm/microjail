from typing import TYPE_CHECKING

import pytest

from microjail.adapters import workshop
from microjail.gates.network_drop import NetworkDrop
from microjail.lockdown import Lockdown
from microjail.microjail import (
    ApplicationIntent,
    ApplicationStatus,
    MicroJail,
)
from tests.marks import requires_lxd, requires_workshop

if TYPE_CHECKING:
    from tests._helpers import SharedWorkshop

pytestmark = [
    requires_lxd(),
    requires_workshop(),
    pytest.mark.slow,
]

NETWORK_PROBE_TIMEOUT = 10


async def has_network_egress(workshop_state: SharedWorkshop) -> bool:
    result = await workshop.exec_(
        workshop_state.name,
        workshop_state.path,
        [
            "python3",
            "-c",
            "import socket; socket.create_connection(('1.1.1.1', 443), timeout=5).close()",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=NETWORK_PROBE_TIMEOUT,
    )
    return result.returncode == 0


async def test_network_drop_blocks_egress_on_application_and_restores_it_on_release(
    launched_workshop: SharedWorkshop,
) -> None:
    if not await has_network_egress(launched_workshop):
        pytest.skip("workshop does not have baseline network egress")

    lockdown = Lockdown(caps=[], gates=[NetworkDrop()])
    microjail = MicroJail(
        name=launched_workshop.name,
        project_path=launched_workshop.path,
        lockdown=lockdown,
    )

    try:
        result = await microjail.ensure(ApplicationIntent.RUN)
        assert result.status is ApplicationStatus.SUCCESS
        assert not await has_network_egress(launched_workshop)
    finally:
        await microjail.release()

    assert await has_network_egress(launched_workshop)
