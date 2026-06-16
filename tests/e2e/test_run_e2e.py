from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from microjail.cli import app
from tests._helpers import (
    can_append_microjail_config,
    can_write_microjail_config,
    has_network_egress,
)

if TYPE_CHECKING:
    from microjail.adapters.workshop import Workshop


def require_baseline_lockable(ws: Workshop) -> None:
    if not has_network_egress(ws):
        pytest.skip("workshop lacks baseline network egress")
    if not can_write_microjail_config(ws):
        pytest.skip("workshop config not writable at baseline")


def test_run_applies_readonly_config_gate_before_workload(
    e2e_workshop: Workshop,
) -> None:
    require_baseline_lockable(e2e_workshop)

    result = CliRunner().invoke(
        app,
        ["run", "--", "sh", "-c", "echo x >> /project/.microjail/config.yaml"],
    )

    assert result.exit_code != 0
    assert not can_append_microjail_config(e2e_workshop)


def test_run_does_not_unlock_after_workload_exits(e2e_workshop: Workshop) -> None:
    require_baseline_lockable(e2e_workshop)

    result = CliRunner().invoke(app, ["run", "--", "true"])

    assert result.exit_code == 0, result.stderr
    assert not has_network_egress(e2e_workshop)
    assert not can_write_microjail_config(e2e_workshop)


def test_run_preserves_workshop_project_mount_behavior(
    e2e_workshop: Workshop,
) -> None:
    require_baseline_lockable(e2e_workshop)
    (e2e_workshop.project / "input.txt").write_text("ok", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["run", "--", "sh", "-c", "cat /project/input.txt > /project/out.txt"],
    )

    assert result.exit_code == 0, result.stderr
    assert (e2e_workshop.project / "out.txt").read_text(encoding="utf-8") == "ok"
    assert not has_network_egress(e2e_workshop)
    assert not can_write_microjail_config(e2e_workshop)


def test_lock_then_run_succeeds_without_clean_baseline(
    e2e_workshop: Workshop,
) -> None:
    require_baseline_lockable(e2e_workshop)

    result = CliRunner().invoke(app, ["lock"])
    assert result.exit_code == 0, result.stderr

    result = CliRunner().invoke(app, ["run", "--", "true"])
    assert result.exit_code == 0, result.stderr


def test_run_auto_launches_workshop_e2e(
    e2e_unlaunched_workshop: Workshop,
) -> None:
    # Assert that workshop is NOT launched before running
    assert e2e_unlaunched_workshop.info() is None

    # Act: Run microjail run
    result = CliRunner().invoke(app, ["run", "--", "true"])

    # Assert
    assert result.exit_code == 0, result.stderr
    info = e2e_unlaunched_workshop.info()
    assert info is not None
    assert info.status == "ready"
