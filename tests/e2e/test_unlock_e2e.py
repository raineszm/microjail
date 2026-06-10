import pytest
from typer.testing import CliRunner

from microjail.cli import app
from tests._helpers import (
    SharedWorkshop,
    can_write_microjail_config,
    has_network_egress,
)


def require_baseline_lockable(ws: SharedWorkshop) -> None:
    if not has_network_egress(ws):
        pytest.skip("workshop lacks baseline network egress")
    if not can_write_microjail_config(ws):
        pytest.skip("workshop config not writable at baseline")


def test_unlock_releases_network_egress_and_readonly_config_gate(
    e2e_workshop: SharedWorkshop,
) -> None:
    require_baseline_lockable(e2e_workshop)

    result = CliRunner().invoke(app, ["lock"])
    assert result.exit_code == 0, result.stderr
    assert not has_network_egress(e2e_workshop)
    assert not can_write_microjail_config(e2e_workshop)

    result = CliRunner().invoke(app, ["unlock"])
    assert result.exit_code == 0, result.stderr
    assert has_network_egress(e2e_workshop)
    assert can_write_microjail_config(e2e_workshop)


def test_lock_twice_succeeds_and_policy_remains_enforced(
    e2e_workshop: SharedWorkshop,
) -> None:
    require_baseline_lockable(e2e_workshop)

    first = CliRunner().invoke(app, ["lock"])
    second = CliRunner().invoke(app, ["lock"])

    assert first.exit_code == 0, first.stderr
    assert second.exit_code == 0, second.stderr
    assert not has_network_egress(e2e_workshop)
    assert not can_write_microjail_config(e2e_workshop)


def test_unlock_twice_succeeds_and_policy_remains_released(
    e2e_workshop: SharedWorkshop,
) -> None:
    require_baseline_lockable(e2e_workshop)

    lock_result = CliRunner().invoke(app, ["lock"])
    first = CliRunner().invoke(app, ["unlock"])
    second = CliRunner().invoke(app, ["unlock"])

    assert lock_result.exit_code == 0, lock_result.stderr
    assert first.exit_code == 0, first.stderr
    assert second.exit_code == 0, second.stderr
    assert has_network_egress(e2e_workshop)
    assert can_write_microjail_config(e2e_workshop)


def test_full_lifecycle_smoke(e2e_workshop: SharedWorkshop) -> None:
    require_baseline_lockable(e2e_workshop)
    (e2e_workshop.path / "input.txt").write_text("ok", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["run", "--", "sh", "-c", "cat /project/input.txt > /project/out.txt"],
    )
    assert result.exit_code == 0, result.stderr
    assert (e2e_workshop.path / "out.txt").read_text(encoding="utf-8") == "ok"
    assert not has_network_egress(e2e_workshop)
    assert not can_write_microjail_config(e2e_workshop)

    result = CliRunner().invoke(app, ["unlock"])
    assert result.exit_code == 0, result.stderr
    assert has_network_egress(e2e_workshop)
    assert can_write_microjail_config(e2e_workshop)
