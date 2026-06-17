"""Functional tests for the microjail validate CLI command."""

from typing import TYPE_CHECKING
from unittest.mock import Mock

from typer.testing import CliRunner

from microjail.adapters.workshop import Workshop
from microjail.cli import app
from microjail.lockdown import Lockdown
from microjail.microjail import MicroJail

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_validate_reports_not_initialized(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    from microjail.microjail import ConfigNotFoundError

    monkeypatch.setattr(
        MicroJail,
        "load",
        Mock(side_effect=ConfigNotFoundError(project_path=microjail_project)),
    )

    result = CliRunner().invoke(app, ["validate"])

    assert result.exit_code == 1
    assert "Not initialized" in result.stderr


def test_validate_reports_valid(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    from microjail.caps.endpoint import WorkshopEndpointCapability

    cap = WorkshopEndpointCapability(name="inference", host_endpoint="127.0.0.1:8080")
    microjail = MicroJail(
        workshop=Workshop(name="test-jail", project=microjail_project),
        lockdown=Lockdown(caps=[cap], gates=[]),
    )
    monkeypatch.setattr(MicroJail, "load", Mock(return_value=microjail))

    result = CliRunner().invoke(app, ["validate"])

    assert result.exit_code == 0
    assert "valid" in result.stdout.lower()


def test_validate_reports_config_errors(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    from microjail.caps.endpoint import WorkshopEndpointCapability

    cap_a = WorkshopEndpointCapability(name="inference", host_endpoint="127.0.0.1:8080")
    cap_b = WorkshopEndpointCapability(name="inference", host_endpoint="127.0.0.1:9090")
    microjail = MicroJail(
        workshop=Workshop(name="test-jail", project=microjail_project),
        lockdown=Lockdown(caps=[cap_a, cap_b], gates=[]),
    )
    monkeypatch.setattr(MicroJail, "load", Mock(return_value=microjail))

    result = CliRunner().invoke(app, ["validate"])

    assert result.exit_code == 1
    assert "duplicate" in result.stderr.lower()
