"""Functional tests for the microjail status CLI command."""

from typing import TYPE_CHECKING
from unittest.mock import Mock

from typer.testing import CliRunner

from microjail.adapters.workshop import Workshop
from microjail.cli import app
from microjail.lockdown import Lockdown
from microjail.microjail import EndpointCapabilityInfo, MicroJail, MicroJailStatus

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
                capabilities=("inference", "critical"),
                gates=("network-egress",),
                connections=(
                    ("test-jail/microjail:inference", "test-jail/system:inference"),
                ),
                endpoint_capabilities=(
                    EndpointCapabilityInfo(
                        name="inference",
                        host_endpoint="127.0.0.1:8080",
                        container_endpoint="127.0.0.1:8080",
                        fatal=False,
                    ),
                    EndpointCapabilityInfo(
                        name="critical",
                        host_endpoint="10.0.0.1:443",
                        container_endpoint="api:443",
                        fatal=True,
                    ),
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
    # Endpoint binding info from the new field
    assert "127.0.0.1:8080" in result.stdout
    assert "10.0.0.1:443" in result.stdout
    assert "api:443" in result.stdout
    # Fatal cap marker
    # Fatal cap marker — the ✗ must be associated with the fatal cap's
    # name, not appear anywhere. (A broad substring match would pass even
    # if the marker showed up next to the non-fatal cap.)
    assert "✗ critical" in result.stdout
    assert "✗ inference" not in result.stdout


def test_status_renders_none_when_no_endpoint_capabilities(
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
                capabilities=(),
                gates=(),
                connections=(),
                endpoint_capabilities=(),
            )
        ),
    )

    result = CliRunner().invoke(app, ["status"])

    assert result.exit_code == 0
    assert "test-jail" in result.stdout
    assert "(none declared)" in result.stdout
