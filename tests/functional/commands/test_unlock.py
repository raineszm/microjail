from typing import TYPE_CHECKING
from unittest.mock import Mock

from typer.testing import CliRunner

from microjail import policy
from microjail.cli import app
from microjail.lockdown import Lockdown
from microjail.microjail import MicroJail
from tests.functional.commands.helpers import RecordingCapability, RecordingGate

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def load_as(microjail: MicroJail, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MicroJail, "load", Mock(return_value=microjail))


class FailingReleaseGate(RecordingGate):
    def release(self, microjail: MicroJail) -> None:
        del microjail
        self.calls.append("release")
        raise RuntimeError(self.name)


class FailingRevokeCapability(RecordingCapability):
    def revoke(self, microjail: MicroJail) -> None:
        del microjail
        self.calls.append("revoke")
        raise RuntimeError(self.name)


def test_unlock_reports_success_with_counts(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    microjail = MicroJail(
        name="test-jail",
        project_path=microjail_project,
        lockdown=Lockdown(
            caps=[RecordingCapability("endpoint")],
            gates=[RecordingGate("network-egress"), RecordingGate("readonly-config")],
        ),
    )
    load_as(microjail, monkeypatch)

    result = CliRunner().invoke(app, ["unlock"])

    assert result.exit_code == 0
    assert "unlock released" in result.stdout
    assert "2 gates" in result.stdout
    assert "1 capabilities" in result.stdout


def test_unlock_rejects_unexpected_arguments() -> None:
    result = CliRunner().invoke(app, ["unlock", "workload"])

    assert result.exit_code != 0
    assert "unexpected" in result.stderr.lower()


def test_unlock_gate_release_failure_returns_policy_code_and_name(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    gate = FailingReleaseGate("network-egress")
    microjail = MicroJail(
        name="test-jail",
        project_path=microjail_project,
        lockdown=Lockdown(caps=[], gates=[gate]),
    )
    load_as(microjail, monkeypatch)

    result = CliRunner().invoke(app, ["unlock"])

    assert result.exit_code == policy.GATE_RELEASE_FAILURE
    assert "unlock failed" in result.stderr
    assert "network-egress" in result.stderr
    assert "ExceptionGroup" not in result.stderr


def test_unlock_capability_release_failure_returns_policy_code_and_name(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    cap = FailingRevokeCapability("endpoint")
    microjail = MicroJail(
        name="test-jail",
        project_path=microjail_project,
        lockdown=Lockdown(caps=[cap], gates=[]),
    )
    load_as(microjail, monkeypatch)

    result = CliRunner().invoke(app, ["unlock"])

    assert result.exit_code == policy.CAPABILITY_RELEASE_FAILURE
    assert "endpoint" in result.stderr


def test_unlock_combined_release_failures_return_combined_policy_code(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    cap = FailingRevokeCapability("endpoint")
    gate = FailingReleaseGate("network-egress")
    microjail = MicroJail(
        name="test-jail",
        project_path=microjail_project,
        lockdown=Lockdown(caps=[cap], gates=[gate]),
    )
    load_as(microjail, monkeypatch)

    result = CliRunner().invoke(app, ["unlock"])

    assert result.exit_code == policy.CAPABILITY_AND_GATE_RELEASE_FAILURE
    assert "network-egress" in result.stderr
    assert "endpoint" in result.stderr


def test_unlock_attempts_all_release_and_revoke_operations_after_failures(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    first_gate = FailingReleaseGate("network-egress")
    second_gate = RecordingGate("readonly-config")
    first_cap = FailingRevokeCapability("endpoint")
    second_cap = RecordingCapability("other-endpoint")
    microjail = MicroJail(
        name="test-jail",
        project_path=microjail_project,
        lockdown=Lockdown(
            caps=[second_cap, first_cap],
            gates=[second_gate, first_gate],
        ),
    )
    load_as(microjail, monkeypatch)

    result = CliRunner().invoke(app, ["unlock"])

    assert result.exit_code == policy.CAPABILITY_AND_GATE_RELEASE_FAILURE
    assert first_gate.calls == ["release"]
    assert second_gate.calls == ["release"]
    assert first_cap.calls == ["revoke"]
    assert second_cap.calls == ["revoke"]
