from typing import TYPE_CHECKING
from unittest.mock import Mock

from typer.testing import CliRunner

from microjail.adapters.workshop import Workshop
from microjail.caps.endpoint import WorkshopEndpointCapability
from microjail.cli import app
from microjail.microjail import MicroJail
from tests.conftest import create_microjail_config

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_cap_add_endpoint_writes_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Add endpoint capability declaration writes config and succeeds."""
    create_microjail_config(tmp_path)

    # Workshop not launched → declaration-only editing permitted
    monkeypatch.setattr(Workshop, "info", Mock(return_value=None))

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
        ],
    )

    assert result.exit_code == 0
    assert "endpoint capability added: inference -> localhost:8080" in result.stdout

    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 1
    cap = loaded.lockdown.caps[0]
    assert isinstance(cap, WorkshopEndpointCapability)
    assert cap.name == "inference"
    assert cap.host_endpoint == "localhost:8080"
    assert cap.container_endpoint is None
    assert cap.fatal is False


def test_cap_add_endpoint_with_container_endpoint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Add with --container-endpoint persists container_endpoint."""
    create_microjail_config(tmp_path)
    monkeypatch.setattr(Workshop, "info", Mock(return_value=None))

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
            "--container-endpoint",
            "10.0.0.1:9090",
        ],
    )

    assert result.exit_code == 0
    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 1
    cap = loaded.lockdown.caps[0]
    assert isinstance(cap, WorkshopEndpointCapability)
    assert cap.container_endpoint == "10.0.0.1:9090"


def test_cap_add_endpoint_fatal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Add with --fatal sets fatal=True."""
    create_microjail_config(tmp_path)
    monkeypatch.setattr(Workshop, "info", Mock(return_value=None))

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
            "--fatal",
        ],
    )

    assert result.exit_code == 0
    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 1
    cap = loaded.lockdown.caps[0]
    assert cap.fatal is True


def test_cap_add_endpoint_same_value_idempotent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Adding same name+host_endpoint succeeds without duplicates."""
    create_microjail_config(tmp_path)
    monkeypatch.setattr(Workshop, "info", Mock(return_value=None))

    # First add
    r1 = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
        ],
    )
    assert r1.exit_code == 0

    # Second add with same values
    r2 = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
        ],
    )
    assert r2.exit_code == 0

    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 1


def test_cap_add_endpoint_replace_requires_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Adding same name with different host_endpoint fails without --replace."""
    create_microjail_config(tmp_path)
    monkeypatch.setattr(Workshop, "info", Mock(return_value=None))

    # First add
    r1 = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
        ],
    )
    assert r1.exit_code == 0

    # Second add with different host_endpoint, no --replace
    r2 = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:9090",
        ],
    )
    assert r2.exit_code != 0

    # Existing declaration unchanged
    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 1
    existing = loaded.lockdown.caps[0]
    assert isinstance(existing, WorkshopEndpointCapability)
    assert existing.host_endpoint == "localhost:8080"


def test_cap_add_endpoint_replace_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """--replace updates host_endpoint and preserves other fields."""
    create_microjail_config(tmp_path)
    monkeypatch.setattr(Workshop, "info", Mock(return_value=None))

    # First add
    r1 = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
        ],
    )
    assert r1.exit_code == 0

    # Replace with different host_endpoint and container_endpoint
    r2 = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:9090",
            "--container-endpoint",
            "10.0.0.1:9090",
            "--replace",
        ],
    )
    assert r2.exit_code == 0

    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 1
    cap = loaded.lockdown.caps[0]
    assert isinstance(cap, WorkshopEndpointCapability)
    assert cap.host_endpoint == "localhost:9090"
    assert cap.container_endpoint == "10.0.0.1:9090"


def test_cap_add_endpoint_fatal_replace_requires_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Changing --fatal requires --replace."""
    create_microjail_config(tmp_path)
    monkeypatch.setattr(Workshop, "info", Mock(return_value=None))

    # First add with --fatal
    r1 = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
            "--fatal",
        ],
    )
    assert r1.exit_code == 0

    # Same name without --fatal and without --replace should fail
    r2 = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
        ],
    )
    assert r2.exit_code != 0
    assert "already exists" in r2.stderr.lower()

    # Verify original unchanged
    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 1
    assert loaded.lockdown.caps[0].fatal is True

    # With --replace, changing --fatal succeeds
    r3 = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
            "--replace",
        ],
    )
    assert r3.exit_code == 0

    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 1
    assert loaded.lockdown.caps[0].fatal is False


def test_cap_remove_endpoint_writes_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Remove endpoint capability removes it from config."""
    create_microjail_config(tmp_path)
    monkeypatch.setattr(Workshop, "info", Mock(return_value=None))

    # First add one
    r1 = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
        ],
    )
    assert r1.exit_code == 0

    # Now remove it
    r2 = CliRunner().invoke(
        app,
        ["--project", str(tmp_path), "cap", "remove", "endpoint", "inference"],
    )
    assert r2.exit_code == 0
    assert "endpoint capability removed: inference" in r2.stdout

    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 0


def test_cap_remove_endpoint_missing_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Remove missing endpoint fails before saving."""
    create_microjail_config(tmp_path)
    monkeypatch.setattr(Workshop, "info", Mock(return_value=None))

    result = CliRunner().invoke(
        app,
        ["--project", str(tmp_path), "cap", "remove", "endpoint", "nonexistent"],
    )

    assert result.exit_code != 0
    assert "endpoint capability 'nonexistent' not found" in result.stderr
    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 0


def test_remove_apply_ready_unlocked_revokes_and_ensures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Remove --apply on ready+unlocked Workshop revokes endpoint and ensures Lockdown."""
    from microjail.adapters.workshop import WorkshopInfo
    from microjail.microjail import (
        ApplicationIntent,
        ApplicationResult,
        ApplicationStatus,
    )

    create_microjail_config(tmp_path)
    # First add a cap declaration-only
    monkeypatch.setattr(Workshop, "info", Mock(return_value=None))
    r1 = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
        ],
    )
    assert r1.exit_code == 0

    # Re-mock for ready+unlocked state
    mock_tunnel = Mock()
    monkeypatch.setattr(Workshop, "tunnel", mock_tunnel)
    monkeypatch.setattr(Workshop, "refresh", Mock())
    monkeypatch.setattr(
        Workshop,
        "info",
        Mock(return_value=WorkshopInfo(name="test-jail", status="ready")),
    )

    mock_ensure = Mock(
        return_value=ApplicationResult(
            intent=ApplicationIntent.LOCK,
            status=ApplicationStatus.SUCCESS,
        )
    )
    monkeypatch.setattr(MicroJail, "ensure", mock_ensure)

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "remove",
            "endpoint",
            "inference",
            "--apply",
        ],
    )

    assert result.exit_code == 0
    assert "endpoint capability removed: inference" in result.stdout

    # Config was saved without the cap
    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 0

    # Revoke was called on the old endpoint (tunnel disconnect triggered)
    mock_tunnel.disconnect.assert_called_once()

    # Ensure was called with LOCK intent
    mock_ensure.assert_called_once_with(ApplicationIntent.LOCK)


def test_remove_apply_stopped_removes_declarations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Remove --apply for stopped Workshop removes plug/slot declarations."""
    from microjail.adapters.workshop import WorkshopInfo

    create_microjail_config(tmp_path)
    # First add a cap declaration-only
    monkeypatch.setattr(Workshop, "info", Mock(return_value=None))
    r1 = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
        ],
    )
    assert r1.exit_code == 0

    # Re-mock for stopped state
    mock_tunnel = Mock()
    monkeypatch.setattr(Workshop, "tunnel", mock_tunnel)
    monkeypatch.setattr(
        Workshop,
        "info",
        Mock(return_value=WorkshopInfo(name="test-jail", status="stopped")),
    )

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "remove",
            "endpoint",
            "inference",
            "--apply",
        ],
    )

    assert result.exit_code == 0
    assert "endpoint capability removed: inference" in result.stdout

    # Config was saved without the cap
    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 0

    # Workshop declarations were updated
    mock_tunnel.remove_plug.assert_called_once_with("inference")
    mock_tunnel.remove_slot.assert_called_once_with("inference", remove_sdk=False)


def test_remove_apply_off_removes_declarations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Remove --apply for off Workshop removes plug/slot declarations."""
    from microjail.adapters.workshop import WorkshopInfo

    create_microjail_config(tmp_path)
    monkeypatch.setattr(Workshop, "info", Mock(return_value=None))
    r1 = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
        ],
    )
    assert r1.exit_code == 0

    mock_tunnel = Mock()
    monkeypatch.setattr(Workshop, "tunnel", mock_tunnel)
    monkeypatch.setattr(
        Workshop,
        "info",
        Mock(return_value=WorkshopInfo(name="test-jail", status="off")),
    )

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "remove",
            "endpoint",
            "inference",
            "--apply",
        ],
    )

    assert result.exit_code == 0
    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 0
    mock_tunnel.remove_plug.assert_called_once_with("inference")
    mock_tunnel.remove_slot.assert_called_once_with("inference", remove_sdk=False)


def test_remove_declaration_only_pending_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Remove fails when Workshop is pending."""
    from microjail.adapters.workshop import WorkshopInfo

    create_microjail_config(tmp_path)
    monkeypatch.setattr(Workshop, "info", Mock(return_value=None))
    # Add a cap first
    r1 = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
        ],
    )
    assert r1.exit_code == 0

    # Re-mock for pending
    monkeypatch.setattr(
        Workshop,
        "info",
        Mock(return_value=WorkshopInfo(name="test-jail", status="pending")),
    )

    result = CliRunner().invoke(
        app,
        ["--project", str(tmp_path), "cap", "remove", "endpoint", "inference"],
    )

    assert result.exit_code != 0
    assert "pending" in result.stderr.lower()

    # Config unchanged
    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 1


def test_remove_declaration_only_ready_locked_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Remove fails when Workshop is ready and locked."""
    from microjail.adapters.workshop import WorkshopInfo
    from microjail.gates.readonly_config import ReadonlyConfig

    create_microjail_config(tmp_path)
    monkeypatch.setattr(Workshop, "info", Mock(return_value=None))
    r1 = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
        ],
    )
    assert r1.exit_code == 0

    # Re-mock for ready+locked
    (tmp_path / ".microjail" / "config.yaml").write_text(
        "workshop:\n  name: test-jail\n  project: "
        + str(tmp_path)
        + "\nlockdown:\n  caps:\n"
        "    - type: endpoint-tunnel\n      name: inference\n      host_endpoint: localhost:8080\n"
        "  gates:\n    - name: readonly-config\n      removed: false\n"
    )
    monkeypatch.setattr(ReadonlyConfig, "check", Mock(return_value=True))
    monkeypatch.setattr(
        Workshop,
        "info",
        Mock(return_value=WorkshopInfo(name="test-jail", status="ready")),
    )

    result = CliRunner().invoke(
        app,
        ["--project", str(tmp_path), "cap", "remove", "endpoint", "inference"],
    )

    assert result.exit_code != 0
    assert "unlock" in result.stderr.lower()


def test_cap_add_endpoint_rejects_invalid_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Endpoint name must start with a letter."""
    create_microjail_config(tmp_path)
    monkeypatch.setattr(Workshop, "info", Mock(return_value=None))

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "123_api",
            "localhost:8080",
        ],
    )

    assert result.exit_code != 0
    assert "invalid" in result.stderr.lower()

    # Config unchanged
    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 0


def test_cap_add_endpoint_rejects_invalid_address(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Endpoint address must be simple HOST:PORT."""
    create_microjail_config(tmp_path)
    monkeypatch.setattr(Workshop, "info", Mock(return_value=None))

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "http://localhost:8080",
        ],
    )

    assert result.exit_code != 0
    assert "invalid" in result.stderr.lower()

    # Config unchanged
    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 0


def test_cap_add_endpoint_rejects_address_without_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Endpoint address must include port."""
    create_microjail_config(tmp_path)
    monkeypatch.setattr(Workshop, "info", Mock(return_value=None))

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost",
        ],
    )

    assert result.exit_code != 0
    assert "invalid" in result.stderr.lower()

    # Config unchanged
    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 0


def test_cap_add_endpoint_rejects_non_numeric_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Endpoint port must be an integer."""
    create_microjail_config(tmp_path)
    monkeypatch.setattr(Workshop, "info", Mock(return_value=None))

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:abc",
        ],
    )

    assert result.exit_code != 0
    assert "port is not an integer" in result.stderr.lower()

    # Config unchanged
    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 0


def test_cap_add_endpoint_rejects_out_of_range_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Endpoint port must be 1-65535."""
    create_microjail_config(tmp_path)
    monkeypatch.setattr(Workshop, "info", Mock(return_value=None))

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:70000",
        ],
    )

    assert result.exit_code != 0
    assert "port out of range" in result.stderr.lower()

    # Config unchanged
    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 0


def test_declaration_only_not_launched_saves(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Declaration-only add saves without warning when Workshop not launched."""
    create_microjail_config(tmp_path)
    monkeypatch.setattr(Workshop, "info", Mock(return_value=None))

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
        ],
    )

    assert result.exit_code == 0
    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 1


def test_declaration_only_pending_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Declaration-only add fails when Workshop is pending."""
    from microjail.adapters.workshop import WorkshopInfo

    create_microjail_config(tmp_path)
    monkeypatch.setattr(
        Workshop,
        "info",
        Mock(return_value=WorkshopInfo(name="test-jail", status="pending")),
    )

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
        ],
    )

    assert result.exit_code != 0
    assert "not launched" in result.stderr.lower() or "pending" in result.stderr.lower()


def test_declaration_only_stopped_warns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Declaration-only add saves with warning when Workshop is stopped."""
    from microjail.adapters.workshop import WorkshopInfo

    create_microjail_config(tmp_path)
    monkeypatch.setattr(
        Workshop,
        "info",
        Mock(return_value=WorkshopInfo(name="test-jail", status="stopped")),
    )

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
        ],
    )

    assert result.exit_code == 0
    assert result.stderr_bytes is not None
    assert b"warning" in result.stderr_bytes.lower()

    # Config was saved
    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 1
    assert loaded.lockdown.caps[0].name == "inference"


def test_declaration_only_off_warns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Declaration-only add saves with warning when Workshop is off."""
    from microjail.adapters.workshop import WorkshopInfo

    create_microjail_config(tmp_path)
    monkeypatch.setattr(
        Workshop,
        "info",
        Mock(return_value=WorkshopInfo(name="test-jail", status="off")),
    )

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
        ],
    )
    assert result.exit_code == 0
    assert result.stderr_bytes is not None
    assert b"warning" in result.stderr_bytes.lower()

    # Config was saved
    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 1
    assert loaded.lockdown.caps[0].name == "inference"


def test_declaration_only_ready_unlocked_saves_with_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Declaration-only add saves with warning for ready unlocked Workshop."""
    from microjail.adapters.workshop import WorkshopInfo

    create_microjail_config(tmp_path)
    monkeypatch.setattr(
        Workshop,
        "info",
        Mock(return_value=WorkshopInfo(name="test-jail", status="ready")),
    )

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
        ],
    )

    assert result.exit_code == 0
    assert result.stderr_bytes is not None
    assert b"warning" in result.stderr_bytes.lower()
    # Config was saved
    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 1
    assert loaded.lockdown.caps[0].name == "inference"


def test_declaration_only_ready_locked_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Declaration-only add fails when Workshop is ready and locked (Gates active)."""
    from microjail.adapters.workshop import WorkshopInfo
    from microjail.gates.readonly_config import ReadonlyConfig

    create_microjail_config(tmp_path)
    # Populate config with a gate
    (tmp_path / ".microjail" / "config.yaml").write_text(
        "workshop:\n  name: test-jail\n  project: "
        + str(tmp_path)
        + "\nlockdown:\n  caps: []\n  gates:\n    - name: readonly-config\n      removed: false\n"
    )
    # Gate's check returns True to simulate locked state
    monkeypatch.setattr(ReadonlyConfig, "check", Mock(return_value=True))
    monkeypatch.setattr(
        Workshop,
        "info",
        Mock(return_value=WorkshopInfo(name="test-jail", status="ready")),
    )

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
        ],
    )

    assert result.exit_code != 0
    assert "unlock" in result.stderr.lower()


def test_declaration_only_unknown_state_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Declaration-only add fails when Workshop state lookup errors."""
    monkeypatch.setattr(
        Workshop, "info", Mock(side_effect=RuntimeError("connection failed"))
    )
    create_microjail_config(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
        ],
    )

    assert result.exit_code != 0


def test_apply_not_launched_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """--apply fails when Workshop is not launched."""
    create_microjail_config(tmp_path)
    monkeypatch.setattr(Workshop, "info", Mock(return_value=None))

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
            "--apply",
        ],
    )

    assert result.exit_code != 0
    assert (
        b"--apply" in result.stderr_bytes.lower()
        or b"apply" in result.stderr_bytes.lower()
    )

    # Config was NOT saved (fails before saving)
    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 0


def test_apply_pending_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """--apply fails when Workshop is pending."""
    from microjail.adapters.workshop import WorkshopInfo

    create_microjail_config(tmp_path)
    monkeypatch.setattr(
        Workshop,
        "info",
        Mock(return_value=WorkshopInfo(name="test-jail", status="pending")),
    )

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
            "--apply",
        ],
    )

    assert result.exit_code != 0

    # Config was NOT saved (fails before saving)
    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 0


def test_apply_stopped_updates_declarations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """--apply for stopped Workshop saves config and updates declarations."""
    from microjail.adapters.workshop import WorkshopInfo

    create_microjail_config(tmp_path)
    monkeypatch.setattr(
        Workshop,
        "info",
        Mock(return_value=WorkshopInfo(name="test-jail", status="stopped")),
    )
    mock_tunnel = Mock()
    monkeypatch.setattr(Workshop, "tunnel", mock_tunnel)

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
            "--apply",
        ],
    )

    assert result.exit_code == 0
    assert "endpoint capability added: inference -> localhost:8080" in result.stdout

    # Config was saved
    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 1
    assert loaded.lockdown.caps[0].name == "inference"

    # Workshop declarations were updated without refresh or connect
    mock_tunnel.add_plug.assert_called_once_with("inference", "localhost:8080")
    mock_tunnel.add_slot.assert_called_once_with("inference", "localhost:8080")
    mock_tunnel.connect.assert_not_called()


def test_apply_ready_locked_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """--apply fails when Workshop is ready and locked."""
    from microjail.adapters.workshop import WorkshopInfo
    from microjail.gates.readonly_config import ReadonlyConfig

    create_microjail_config(tmp_path)
    (tmp_path / ".microjail" / "config.yaml").write_text(
        "workshop:\n  name: test-jail\n  project: "
        + str(tmp_path)
        + "\nlockdown:\n  caps: []\n  gates:\n    - name: readonly-config\n      removed: false\n"
    )
    monkeypatch.setattr(ReadonlyConfig, "check", Mock(return_value=True))
    monkeypatch.setattr(
        Workshop,
        "info",
        Mock(return_value=WorkshopInfo(name="test-jail", status="ready")),
    )

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
            "--apply",
        ],
    )

    assert result.exit_code != 0

    # Config was NOT saved (fails before saving)
    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 0


def test_apply_ready_unlocked_saves_and_ensures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """--apply for ready unlocked Workshop saves config and calls MicroJail.ensure."""
    from microjail.adapters.workshop import WorkshopInfo
    from microjail.microjail import (
        ApplicationIntent,
        ApplicationResult,
        ApplicationStatus,
    )

    create_microjail_config(tmp_path)
    monkeypatch.setattr(
        Workshop,
        "info",
        Mock(return_value=WorkshopInfo(name="test-jail", status="ready")),
    )

    mock_result = ApplicationResult(
        intent=ApplicationIntent.LOCK,
        status=ApplicationStatus.SUCCESS,
    )
    mock_ensure = Mock(return_value=mock_result)
    monkeypatch.setattr(MicroJail, "ensure", mock_ensure)

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
            "--apply",
        ],
    )

    assert result.exit_code == 0
    assert "endpoint capability added: inference -> localhost:8080" in result.stdout

    # Config was saved
    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 1
    assert loaded.lockdown.caps[0].name == "inference"

    # Ensure was called with LOCK intent
    mock_ensure.assert_called_once_with(ApplicationIntent.LOCK)


def test_cap_add_endpoint_rejects_duplicate_names_in_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Duplicate capability names in config are rejected before editing."""
    monkeypatch.setattr(Workshop, "info", Mock(return_value=None))

    # Create microjail directory and write config with duplicate names
    (tmp_path / ".microjail").mkdir()
    (tmp_path / ".microjail" / "config.yaml").write_text(
        "workshop:\n  name: test-jail\n  project: "
        + str(tmp_path)
        + "\nlockdown:\n  caps:\n"
        "    - type: endpoint-tunnel\n      name: duplicate\n      host_endpoint: localhost:8080\n"
        "    - type: endpoint-tunnel\n      name: duplicate\n      host_endpoint: localhost:9090\n"
        "  gates: []\n"
    )

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:7070",
        ],
    )

    assert result.exit_code != 0
    assert "duplicate" in result.stderr.lower()


def test_cap_add_endpoint_succeeds_after_init_when_workshop_unlaunched(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression: declaration-only add must succeed against the real default Lockdown
    when the workshop has never been launched.

    Before the fix, iterating gates to compute ``is_locked`` triggered
    ``NetworkDrop.check()`` which called ``microjail.exec_()``, which raised
    ``WorkshopNotLaunchedError`` (or ``WorkshopNotFoundError`` when no workshop
    directory exists) and produced a raw traceback. The fix catches
    ``MicrojailError`` in ``NetworkDrop.check()`` and returns ``False``, matching
    the contract already used by ``ReadonlyConfig``.
    """
    create_microjail_config(tmp_path)
    monkeypatch.setattr(Workshop, "info", Mock(return_value=None))

    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "cap",
            "add",
            "endpoint",
            "inference",
            "localhost:8080",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "endpoint capability added: inference -> localhost:8080" in result.stdout
    assert "Traceback" not in result.output

    loaded = MicroJail.load(tmp_path)
    assert len(loaded.lockdown.caps) == 1
    cap = loaded.lockdown.caps[0]
    assert isinstance(cap, WorkshopEndpointCapability)
    assert cap.name == "inference"
    assert cap.host_endpoint == "localhost:8080"
