from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from microjail.cli import app
from microjail.microjail import MicroJail
from tests._helpers import (
    can_write_microjail_config,
    has_network_egress,
)

if TYPE_CHECKING:
    from microjail.adapters.workshop import Workshop


def test_init_writes_default_config_that_lock_can_apply(
    e2e_project: Workshop,
) -> None:
    result = CliRunner().invoke(app, ["init", e2e_project.name])
    assert result.exit_code == 0, result.stderr
    assert (e2e_project.project / ".microjail" / "config.yaml").exists()
    e2e_project.launch()

    if not has_network_egress(e2e_project):
        pytest.skip("workshop lacks baseline network egress")
    if not can_write_microjail_config(e2e_project):
        pytest.skip("workshop config not writable at baseline")

    result = CliRunner().invoke(app, ["lock"])
    assert result.exit_code == 0, result.stderr
    assert not has_network_egress(e2e_project)
    assert not can_write_microjail_config(e2e_project)


def test_init_adopt_existing_workshop_writes_config_and_lock_applies_defaults(
    e2e_raw_workshop: Workshop,
) -> None:
    result = CliRunner().invoke(app, ["init", e2e_raw_workshop.name, "--adopt"])
    assert result.exit_code == 0, result.stderr

    loaded = MicroJail.load(e2e_raw_workshop.project)
    assert loaded.name == e2e_raw_workshop.name
    assert loaded.project_path == e2e_raw_workshop.project

    if not has_network_egress(e2e_raw_workshop):
        pytest.skip("workshop lacks baseline network egress")
    if not can_write_microjail_config(e2e_raw_workshop):
        pytest.skip("workshop config not writable at baseline")
    result = CliRunner().invoke(app, ["lock"])
    assert result.exit_code == 0, result.stderr
    assert not has_network_egress(e2e_raw_workshop)
    assert not can_write_microjail_config(e2e_raw_workshop)
