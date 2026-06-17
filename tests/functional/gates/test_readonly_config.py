from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from microjail.adapters.workshop import Workshop
from microjail.gates.readonly_config import ReadonlyConfig
from microjail.lockdown import Lockdown
from microjail.microjail import (
    ApplicationIntent,
    ApplicationStatus,
    MicroJail,
)
from tests.marks import requires_lxd, requires_workshop

pytestmark = [
    requires_lxd(),
    requires_workshop(),
    pytest.mark.slow,
]


def can_write_config(ws: Workshop) -> bool:
    result = ws.exec_(
        ["bash", "-c", "echo x >> /project/.microjail/config.yaml"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def test_readonly_config_blocks_write_on_application_and_restores_on_release(
    launched_workshop: Workshop,
) -> None:
    if not can_write_config(launched_workshop):
        pytest.skip("workshop does not have baseline write access to config")

    lockdown = Lockdown(caps=[], gates=[ReadonlyConfig()])
    microjail = MicroJail(
        workshop=launched_workshop,
        lockdown=lockdown,
    )

    try:
        result = microjail.ensure(ApplicationIntent.RUN)
        assert result.status is ApplicationStatus.SUCCESS
        assert not can_write_config(launched_workshop)
    finally:
        microjail.release()

    assert can_write_config(launched_workshop)
