from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess, TimeoutExpired
from unittest.mock import Mock

import msgspec
import pytest

from microjail.adapters import workshop
from microjail.adapters.workshop import (
    MicrojailSdk,
    MicrojailSdkConfigError,
    TunnelEntry,
    WorkshopConfig,
    WorkshopSdk,
)


def test_connections_parses_tunnel_rows_from_column_slices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = Mock(
        return_value=CompletedProcess(
            args=["workshop"],
            returncode=0,
            stdout=(
                "INTERFACE  PLUG              SLOT              NOTES\n"
                "tunnel     api               ingress           ok\n"
                "tunnel     db                storage           ok\n"
                "bridge     ignored           ignored           ignored\n"
                "tunnel                       missing-slot      ok\n"
            ),
            stderr="",
        )
    )
    monkeypatch.setattr(workshop.subprocess, "run", run)

    assert workshop.connections("mj-workshop", Path("/tmp/project")) == [
        ("api", "ingress"),
        ("db", "storage"),
    ]
    run.assert_called_once_with(
        ["workshop", "connections", "mj-workshop", "--project", "/tmp/project"],
        check=True,
        capture_output=True,
        text=True,
    )


def test_connections_returns_empty_when_headers_are_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        workshop.subprocess,
        "run",
        Mock(
            return_value=CompletedProcess(
                args=["workshop"], returncode=0, stdout="no headers here\n", stderr=""
            )
        ),
    )

    assert workshop.connections("mj-workshop", Path("/tmp/project")) == []


def test_connect_builds_expected_command(monkeypatch: pytest.MonkeyPatch) -> None:
    run = Mock(return_value=CompletedProcess(args=["workshop"], returncode=0))
    monkeypatch.setattr(workshop.subprocess, "run", run)

    workshop.connect(
        "mj-workshop", Path("/tmp/project"), "microjail", "plug", "system", "slot"
    )

    run.assert_called_once_with(
        [
            "workshop",
            "connect",
            "mj-workshop/microjail:plug",
            "mj-workshop/system:slot",
            "--project",
            "/tmp/project",
        ],
        check=True,
        capture_output=True,
    )


def test_disconnect_ignores_not_connected_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = Mock(
        side_effect=CalledProcessError(
            returncode=1,
            cmd=["workshop", "disconnect"],
            stderr=b"error: not connected\n",
        )
    )
    monkeypatch.setattr(workshop.subprocess, "run", run)

    workshop.disconnect(
        "mj-workshop", Path("/tmp/project"), "microjail", "plug", "system", "slot"
    )

    run.assert_called_once()


def test_disconnect_raises_for_other_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        workshop.subprocess,
        "run",
        Mock(
            side_effect=CalledProcessError(
                returncode=1,
                cmd=["workshop", "disconnect"],
                stderr=b"something else\n",
            )
        ),
    )

    with pytest.raises(CalledProcessError):
        workshop.disconnect(
            "mj-workshop", Path("/tmp/project"), "microjail", "plug", "system", "slot"
        )


def test_refresh_builds_expected_command(monkeypatch: pytest.MonkeyPatch) -> None:
    run = Mock(return_value=CompletedProcess(args=["workshop"], returncode=0))
    monkeypatch.setattr(workshop.subprocess, "run", run)

    workshop.refresh("mj-workshop", Path("/tmp/project"))

    run.assert_called_once_with(
        ["workshop", "refresh", "mj-workshop", "--project", "/tmp/project"],
        check=True,
        capture_output=True,
    )


def test_restore_builds_expected_command(monkeypatch: pytest.MonkeyPatch) -> None:
    run = Mock(return_value=CompletedProcess(args=["workshop"], returncode=0))
    monkeypatch.setattr(workshop.subprocess, "run", run)

    workshop.restore("mj-workshop", Path("/tmp/project"))

    run.assert_called_once_with(
        ["workshop", "restore", "mj-workshop", "--project", "/tmp/project"],
        check=True,
        capture_output=True,
    )


@pytest.mark.parametrize("returncode,expected", [(0, True), (1, False)])
def test_endpoint_reachable_returns_probe_result(
    returncode: int, expected: bool
) -> None:
    microjail = Mock()
    microjail.exec_.return_value = CompletedProcess(
        args=["bash"], returncode=returncode
    )

    assert workshop.endpoint_reachable(microjail, "127.0.0.1", 8080) is expected
    microjail.exec_.assert_called_once_with(
        ["bash", "-c", ": >/dev/tcp/127.0.0.1/8080"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_endpoint_reachable_returns_false_on_timeout() -> None:
    microjail = Mock()
    microjail.exec_.side_effect = TimeoutExpired(cmd=["bash"], timeout=10)

    assert not workshop.endpoint_reachable(microjail, "127.0.0.1", "8080")


def test_read_and_write_workshop_yaml_round_trip(tmp_path: Path) -> None:
    data = WorkshopConfig(
        name="mj-workshop",
        base="ubuntu@24.04",
        sdks=[
            WorkshopSdk(
                name="system",
                slots={
                    "api": TunnelEntry(interface="tunnel", endpoint="127.0.0.1:8080")
                },
            )
        ],
    )

    workshop.write_workshop_yaml("mj-workshop", tmp_path, data)

    path = tmp_path / ".workshop" / "mj-workshop.yaml"
    assert path.exists()
    assert workshop.read_workshop_yaml("mj-workshop", tmp_path) == data
    assert msgspec.yaml.decode(path.read_bytes(), type=WorkshopConfig) == data


def test_read_workshop_yaml_returns_default_for_missing_file(tmp_path: Path) -> None:
    assert workshop.read_workshop_yaml("mj-workshop", tmp_path) == WorkshopConfig(
        name="mj-workshop"
    )


def test_read_workshop_yaml_raises_for_invalid_existing_file(tmp_path: Path) -> None:
    path = tmp_path / ".workshop" / "mj-workshop.yaml"
    path.parent.mkdir(parents=True)
    path.write_text("sdks: [not-a-map]\n", encoding="utf-8")

    with pytest.raises(workshop.WorkshopConfigError) as exc_info:
        workshop.read_workshop_yaml("mj-workshop", tmp_path)

    assert exc_info.value.name == "mj-workshop"
    assert exc_info.value.project == tmp_path


def test_read_and_write_microjail_sdk_round_trip(tmp_path: Path) -> None:
    data = MicrojailSdk(
        plugs={"api": TunnelEntry(interface="tunnel", endpoint="127.0.0.1:8080")}
    )

    workshop.write_microjail_sdk(tmp_path, data)

    path = tmp_path / ".workshop" / "microjail" / "sdk.yaml"
    assert path.exists()
    assert workshop.read_microjail_sdk(tmp_path) == data
    assert msgspec.yaml.decode(path.read_bytes(), type=MicrojailSdk) == data


def test_read_microjail_sdk_returns_default_for_missing_file(tmp_path: Path) -> None:
    assert workshop.read_microjail_sdk(tmp_path) == MicrojailSdk()


def test_read_microjail_sdk_raises_for_invalid_existing_file(tmp_path: Path) -> None:
    path = tmp_path / ".workshop" / "microjail" / "sdk.yaml"
    path.parent.mkdir(parents=True)
    path.write_text("plugs: [not-a-map]\n", encoding="utf-8")

    with pytest.raises(MicrojailSdkConfigError):
        workshop.read_microjail_sdk(tmp_path)


def test_add_tunnel_plug_updates_existing_endpoint_and_is_noop_when_unchanged(
    tmp_path: Path,
) -> None:
    workshop.add_tunnel_plug(tmp_path, "api", "127.0.0.1:8080")
    workshop.add_tunnel_plug(tmp_path, "api", "127.0.0.1:9999")

    assert workshop.read_microjail_sdk(tmp_path) == MicrojailSdk(
        plugs={"api": TunnelEntry(interface="tunnel", endpoint="127.0.0.1:9999")}
    )

    workshop.add_tunnel_plug(tmp_path, "api", "127.0.0.1:9999")

    assert workshop.read_microjail_sdk(tmp_path) == MicrojailSdk(
        plugs={"api": TunnelEntry(interface="tunnel", endpoint="127.0.0.1:9999")}
    )


def test_remove_tunnel_plug_reports_remaining_state_and_is_noop_when_missing(
    tmp_path: Path,
) -> None:
    workshop.add_tunnel_plug(tmp_path, "api", "127.0.0.1:8080")
    assert workshop.remove_tunnel_plug(tmp_path, "missing") is True

    assert workshop.remove_tunnel_plug(tmp_path, "api") is False
    assert workshop.read_microjail_sdk(tmp_path) == MicrojailSdk()


def test_add_and_remove_tunnel_plug_raise_for_invalid_existing_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".workshop" / "microjail" / "sdk.yaml"
    path.parent.mkdir(parents=True)
    path.write_text("plugs: [not-a-map]\n", encoding="utf-8")

    with pytest.raises(MicrojailSdkConfigError):
        workshop.add_tunnel_plug(tmp_path, "api", "127.0.0.1:8080")

    with pytest.raises(MicrojailSdkConfigError):
        workshop.remove_tunnel_plug(tmp_path, "api")

    assert path.read_text(encoding="utf-8") == "plugs: [not-a-map]\n"


def test_add_tunnel_slot_updates_existing_endpoint_and_is_noop_when_unchanged(
    tmp_path: Path,
) -> None:
    workshop.add_tunnel_slot("mj-workshop", tmp_path, "api", "127.0.0.1:8080")
    workshop.add_tunnel_slot("mj-workshop", tmp_path, "api", "127.0.0.1:9999")

    assert workshop.read_workshop_yaml("mj-workshop", tmp_path) == WorkshopConfig(
        name="mj-workshop",
        sdks=[
            WorkshopSdk(name="project-microjail"),
            WorkshopSdk(
                name="system",
                slots={
                    "api": TunnelEntry(interface="tunnel", endpoint="127.0.0.1:9999")
                },
            ),
        ],
    )

    workshop.add_tunnel_slot("mj-workshop", tmp_path, "api", "127.0.0.1:9999")
    assert workshop.read_workshop_yaml("mj-workshop", tmp_path) == WorkshopConfig(
        name="mj-workshop",
        sdks=[
            WorkshopSdk(name="project-microjail"),
            WorkshopSdk(
                name="system",
                slots={
                    "api": TunnelEntry(interface="tunnel", endpoint="127.0.0.1:9999")
                },
            ),
        ],
    )


def test_add_tunnel_slot_raises_for_invalid_existing_file(tmp_path: Path) -> None:
    path = tmp_path / ".workshop" / "mj-workshop.yaml"
    path.parent.mkdir(parents=True)
    path.write_text("sdks: [not-a-map]\n", encoding="utf-8")

    with pytest.raises(workshop.WorkshopConfigError):
        workshop.add_tunnel_slot("mj-workshop", tmp_path, "api", "127.0.0.1:8080")

    with pytest.raises(workshop.WorkshopConfigError):
        workshop.remove_tunnel_slot("mj-workshop", tmp_path, "api", remove_sdk=False)

    assert path.read_text(encoding="utf-8") == "sdks: [not-a-map]\n"


def test_remove_tunnel_slot_can_drop_project_sdk_and_is_noop_when_missing(
    tmp_path: Path,
) -> None:
    workshop.add_tunnel_slot("mj-workshop", tmp_path, "api", "127.0.0.1:8080")
    workshop.remove_tunnel_slot("mj-workshop", tmp_path, "api", remove_sdk=True)

    assert workshop.read_workshop_yaml("mj-workshop", tmp_path) == WorkshopConfig(
        name="mj-workshop", sdks=[WorkshopSdk(name="system")]
    )
    workshop.remove_tunnel_slot("mj-workshop", tmp_path, "missing", remove_sdk=True)

    assert workshop.read_workshop_yaml("mj-workshop", tmp_path) == WorkshopConfig(
        name="mj-workshop", sdks=[WorkshopSdk(name="system")]
    )
