"""Functional tests for the microjail status CLI command."""

from typing import TYPE_CHECKING
from unittest.mock import Mock

from typer.testing import CliRunner

from microjail.adapters.workshop import Workshop
from microjail.cli import app
from microjail.lockdown import Lockdown
from microjail.microjail import MicroJail, MicroJailStatus

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_status_reports_not_initialized(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    from microjail.microjail import ConfigNotFoundError

    monkeypatch.setattr(
        MicroJail,
        "load",
        Mock(side_effect=ConfigNotFoundError(project_path=microjail_project)),
    )

    result = CliRunner().invoke(app, ["status"])

    assert result.exit_code == 0
    assert "Not initialized" in result.stdout


def test_status_displays_workshop_state(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    microjail = MicroJail(
        workshop=Workshop(name="test-jail", project=microjail_project),
        lockdown=Lockdown(caps=[], gates=[]),
    )
    monkeypatch.setattr(MicroJail, "load", Mock(return_value=microjail))
    monkeypatch.setattr(
        microjail,
        "status",
        Mock(
            return_value=MicroJailStatus(
                workshop_name="test-jail",
                workshop_status="ready",
                capabilities=("inference",),
                gates=("network-egress",),
                connections=(
                    ("test-jail/microjail:inference", "test-jail/system:inference"),
                ),
            )
        ),
    )

    result = CliRunner().invoke(app, ["status"])

    assert result.exit_code == 0
    assert "test-jail" in result.stdout
    assert "ready" in result.stdout
    assert "inference" in result.stdout
    assert "network-egress" in result.stdout
