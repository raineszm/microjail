from typing import TYPE_CHECKING

import pytest

from microjail.gates.network_drop import NetworkDrop
from microjail.lockdown import Lockdown
from microjail.microjail import (
    ApplicationIntent,
    ApplicationStatus,
    MicroJail,
)
from tests.marks import requires_lxd, requires_workshop

if TYPE_CHECKING:
    from microjail.adapters.workshop import Workshop

pytestmark = [
    requires_lxd(),
    requires_workshop(),
    pytest.mark.slow,
]

NETWORK_PROBE_TIMEOUT = 10


def has_network_egress(workshop_state: Workshop) -> bool:
    result = workshop_state.exec_(
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


def test_network_drop_blocks_egress_on_application_and_restores_it_on_release(
    launched_workshop: Workshop,
) -> None:
    if not has_network_egress(launched_workshop):
        pytest.skip("workshop does not have baseline network egress")

    lockdown = Lockdown(caps=[], gates=[NetworkDrop()])
    microjail = MicroJail(
        workshop=launched_workshop,
        lockdown=lockdown,
    )

    try:
        result = microjail.ensure(ApplicationIntent.RUN)
        assert result.status is ApplicationStatus.SUCCESS
        assert not has_network_egress(launched_workshop)
    finally:
        microjail.release()

    assert has_network_egress(launched_workshop)
