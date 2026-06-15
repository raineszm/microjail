import os
import subprocess
import uuid
from pathlib import Path

import anyio
import pytest

from microjail.adapters import workshop
from microjail.gates.readonly_config import ReadonlyConfig
from microjail.lockdown import Lockdown
from microjail.microjail import (
    ApplicationIntent,
    ApplicationStatus,
    MicroJail,
)
from tests._helpers import SharedWorkshop
from tests.marks import requires_lxd, requires_workshop

pytestmark = [
    requires_lxd(),
    requires_workshop(),
    pytest.mark.slow,
]


@pytest.fixture(scope="module")
def launched_workshop(tmp_path_factory):
    project = tmp_path_factory.mktemp("readonly-config-workshop")
    name = f"mj-workshop-{uuid.uuid4().hex[:8]}"
    cwd = Path.cwd()

    async def _setup():
        await workshop.init(name, project=project)
        mj = MicroJail(name=name, project_path=project, lockdown=Lockdown.default())
        mj.save()
        await workshop.launch(name, project=project)

    try:
        os.chdir(project)
        anyio.run(_setup)
        yield SharedWorkshop(name=name, path=project)
    finally:
        os.chdir(cwd)
        subprocess.run(["workshop", "remove", "--project", str(project)], check=False)


async def can_write_config(ws: SharedWorkshop) -> bool:
    result = await workshop.exec_(
        ws.name,
        ws.path,
        ["bash", "-c", "echo x >> /project/.microjail/config.yaml"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


async def test_readonly_config_blocks_write_on_application_and_restores_on_release(
    launched_workshop: SharedWorkshop,
) -> None:
    if not await can_write_config(launched_workshop):
        pytest.skip("workshop does not have baseline write access to config")

    lockdown = Lockdown(caps=[], gates=[ReadonlyConfig()])
    microjail = MicroJail(
        name=launched_workshop.name,
        project_path=launched_workshop.path,
        lockdown=lockdown,
    )

    try:
        result = await microjail.ensure(ApplicationIntent.RUN)
        assert result.status is ApplicationStatus.SUCCESS
        assert not await can_write_config(launched_workshop)
    finally:
        await microjail.release()

    assert await can_write_config(launched_workshop)
