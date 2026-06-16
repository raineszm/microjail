import os
import subprocess
import uuid
from pathlib import Path

import pytest

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


@pytest.fixture(scope="module")
def launched_workshop(tmp_path_factory):
    project = tmp_path_factory.mktemp("readonly-config-workshop")
    name = f"mj-workshop-{uuid.uuid4().hex[:8]}"
    cwd = Path.cwd()

    try:
        os.chdir(project)
        Workshop.init(name, project=project)
        mj = MicroJail(
            workshop=Workshop(name=name, project=project), lockdown=Lockdown.default()
        )
        mj.save()
        Workshop(name=name, project=project).launch()
        yield Workshop(name=name, project=project)
    finally:
        os.chdir(cwd)
        subprocess.run(["workshop", "remove", "--project", str(project)], check=False)


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
