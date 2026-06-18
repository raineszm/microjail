import subprocess
from typing import TYPE_CHECKING

import pytest

from microjail.adapters.workshop import Workshop
from microjail.gates.network_drop import NetworkDrop
from microjail.gates.readonly_config import ReadonlyConfig
from microjail.lockdown import Lockdown
from microjail.microjail import ConfigNotFoundError, MicroJail

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def tmp_microjail(tmp_path: Path, project_name: str) -> MicroJail:
    return MicroJail(
        workshop=Workshop(name=project_name, project=tmp_path),
        lockdown=Lockdown(caps=[], gates=[]),
    )


def test_save_writes_config_under_microjail_dir(tmp_microjail: MicroJail) -> None:
    tmp_microjail.save()
    assert tmp_microjail.config_path.exists()


def test_save_creates_missing_microjail_dir(tmp_microjail: MicroJail) -> None:
    tmp_microjail.save()

    assert tmp_microjail.config_dir.is_dir()


def test_load_round_trips_saved_config(tmp_microjail: MicroJail) -> None:
    tmp_microjail.save()

    loaded = MicroJail.load(tmp_microjail.project_path)
    assert loaded == tmp_microjail


def test_load_round_trips_default_gates(tmp_path: Path, project_name: str) -> None:
    microjail = MicroJail(
        workshop=Workshop(name=project_name, project=tmp_path),
        lockdown=Lockdown.default(),
    )
    microjail.save()

    loaded = MicroJail.load(tmp_path)
    assert loaded.name == microjail.name
    assert loaded.project_path == microjail.project_path
    assert isinstance(loaded.lockdown.gates[0], NetworkDrop)
    assert isinstance(loaded.lockdown.gates[1], ReadonlyConfig)


def test_load_raises_when_config_missing(tmp_path: Path) -> None:
    with pytest.raises(ConfigNotFoundError) as exc_info:
        MicroJail.load(tmp_path)

    assert exc_info.value.project_path == tmp_path


def test_status_returns_workshop_info_and_lockdown_state(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    from unittest.mock import Mock, PropertyMock

    from microjail.adapters.workshop import WorkshopInfo
    from microjail.caps.endpoint import WorkshopEndpointCapability

    cap = WorkshopEndpointCapability(name="inference", host_endpoint="127.0.0.1:8080")
    microjail = MicroJail(
        workshop=Workshop(name=tmp_microjail.name, project=tmp_microjail.project_path),
        lockdown=Lockdown(caps=[cap], gates=[]),
    )
    monkeypatch.setattr(
        microjail.workshop,
        "info",
        Mock(return_value=WorkshopInfo(name=microjail.name, status="ready")),
    )
    mock_tunnel = Mock()
    mock_tunnel.connections.return_value = [
        (f"{microjail.name}/microjail:inference", f"{microjail.name}/system:inference"),
    ]
    monkeypatch.setattr(Workshop, "tunnel", PropertyMock(return_value=mock_tunnel))

    result = microjail.status()

    assert result.workshop_name == microjail.name
    assert result.workshop_status == "ready"
    assert result.capabilities == ("inference",)
    assert result.gates == ()
    assert result.connections == (
        (f"{microjail.name}/microjail:inference", f"{microjail.name}/system:inference"),
    )


def test_status_exposes_endpoint_capability_binding_info(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    from unittest.mock import Mock, PropertyMock

    from microjail.adapters.workshop import Workshop, WorkshopInfo
    from microjail.caps.endpoint import WorkshopEndpointCapability
    from microjail.microjail import EndpointCapabilityInfo

    cap_plain = WorkshopEndpointCapability(
        name="plain",
        host_endpoint="127.0.0.1:8080",
    )
    cap_remapped = WorkshopEndpointCapability(
        name="remapped",
        host_endpoint="10.0.0.1:443",
        container_endpoint="api:443",
        fatal=True,
    )
    microjail = MicroJail(
        workshop=Workshop(name=tmp_microjail.name, project=tmp_microjail.project_path),
        lockdown=Lockdown(caps=[cap_plain, cap_remapped], gates=[]),
    )
    monkeypatch.setattr(
        microjail.workshop,
        "info",
        Mock(return_value=WorkshopInfo(name=microjail.name, status="ready")),
    )
    mock_tunnel = Mock()
    mock_tunnel.connections.return_value = []
    monkeypatch.setattr(Workshop, "tunnel", PropertyMock(return_value=mock_tunnel))

    result = microjail.status()

    assert result.endpoint_capabilities == (
        EndpointCapabilityInfo(
            name="plain",
            host_endpoint="127.0.0.1:8080",
            container_endpoint="127.0.0.1:8080",
            fatal=False,
        ),
        EndpointCapabilityInfo(
            name="remapped",
            host_endpoint="10.0.0.1:443",
            container_endpoint="api:443",
            fatal=True,
        ),
    )


def test_status_reports_unavailable_when_workshop_not_launched(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    from unittest.mock import Mock, PropertyMock

    from microjail.adapters.workshop import Workshop

    monkeypatch.setattr(tmp_microjail.workshop, "info", Mock(return_value=None))
    mock_tunnel = Mock()
    mock_tunnel.connections.return_value = []
    monkeypatch.setattr(Workshop, "tunnel", PropertyMock(return_value=mock_tunnel))

    result = tmp_microjail.status()

    assert result.workshop_status == "unavailable"
    assert result.connections == ()


def test_status_handles_connection_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    from unittest.mock import Mock, PropertyMock

    from microjail.adapters.workshop import Workshop

    monkeypatch.setattr(
        tmp_microjail.workshop,
        "info",
        Mock(return_value=Mock(name="test", status="ready")),
    )
    mock_tunnel = Mock()
    mock_tunnel.connections.side_effect = subprocess.CalledProcessError(
        1, ["workshop", "connections"]
    )
    monkeypatch.setattr(Workshop, "tunnel", PropertyMock(return_value=mock_tunnel))

    result = tmp_microjail.status()

    assert result.workshop_status == "ready"
    assert result.connections == ()


def test_validate_returns_no_errors_for_valid_config() -> None:
    from pathlib import Path

    from microjail.caps.endpoint import WorkshopEndpointCapability

    cap = WorkshopEndpointCapability(name="inference", host_endpoint="127.0.0.1:8080")
    microjail = MicroJail(
        workshop=Workshop(name="test", project=Path("/tmp/test")),
        lockdown=Lockdown(caps=[cap], gates=[]),
    )

    errors = microjail.validate()

    assert errors == []


def test_validate_detects_duplicate_cap_names() -> None:
    from pathlib import Path

    from microjail.caps.endpoint import WorkshopEndpointCapability

    cap_a = WorkshopEndpointCapability(name="inference", host_endpoint="127.0.0.1:8080")
    cap_b = WorkshopEndpointCapability(name="inference", host_endpoint="127.0.0.1:9090")
    microjail = MicroJail(
        workshop=Workshop(name="test", project=Path("/tmp/test")),
        lockdown=Lockdown(caps=[cap_a, cap_b], gates=[]),
    )

    errors = microjail.validate()

    assert len(errors) == 1
    assert any("duplicate" in e.message.lower() for e in errors)
    assert any("inference" in e.message for e in errors)


def test_validate_detects_bad_endpoint_name() -> None:
    from pathlib import Path

    from microjail.caps.endpoint import WorkshopEndpointCapability

    cap = WorkshopEndpointCapability(name="_bad", host_endpoint="127.0.0.1:8080")
    microjail = MicroJail(
        workshop=Workshop(name="test", project=Path("/tmp/test")),
        lockdown=Lockdown(caps=[cap], gates=[]),
    )

    errors = microjail.validate()

    assert len(errors) == 1
    assert any("endpoint name" in e.message.lower() for e in errors)


def test_validate_detects_bad_endpoint_address() -> None:
    from pathlib import Path

    from microjail.caps.endpoint import WorkshopEndpointCapability

    cap = WorkshopEndpointCapability(name="inf", host_endpoint="no-port")
    microjail = MicroJail(
        workshop=Workshop(name="test", project=Path("/tmp/test")),
        lockdown=Lockdown(caps=[cap], gates=[]),
    )

    errors = microjail.validate()

    assert len(errors) == 1
    assert any("port" in e.message.lower() for e in errors)
