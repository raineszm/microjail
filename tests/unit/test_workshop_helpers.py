import subprocess
from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess, TimeoutExpired
from unittest.mock import Mock, call

import msgspec
import pytest

from microjail.adapters import workshop
from microjail.adapters.workshop import (
    MicrojailSdk,
    MicrojailSdkConfigError,
    TunnelEntry,
    TunnelInterface,
    Workshop,
    WorkshopConfig,
    WorkshopInfo,
    WorkshopNotFoundError,
    WorkshopNotLaunchedError,
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


def test_workshop_info_returns_parsed_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = Workshop(name="test", project=Path("/tmp/test"))
    run = Mock(
        return_value=subprocess.CompletedProcess(
            args=["workshop"],
            returncode=0,
            stdout=b"name: test\nstatus: ready\n",
        )
    )
    monkeypatch.setattr(subprocess, "run", run)
    info = ws.info()
    assert info == WorkshopInfo(name="test", status="ready")
    run.assert_called_once_with(
        ["workshop", "info", "test", "--project", "/tmp/test"],
        check=True,
        capture_output=True,
    )


def test_workshop_info_returns_none_when_not_launched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = Workshop(name="test", project=Path("/tmp/test"))
    exc = subprocess.CalledProcessError(
        1, ["workshop"], stderr=b"workshop not launched: test"
    )
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=exc))
    assert ws.info() is None


def test_workshop_info_propagates_other_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = Workshop(name="test", project=Path("/tmp/test"))
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(side_effect=subprocess.CalledProcessError(1, ["workshop"], stderr=b"")),
    )
    with pytest.raises(subprocess.CalledProcessError):
        ws.info()


def test_workshop_exists_returns_true_when_name_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = Workshop(name="test", project=Path("/tmp/test"))
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(
            return_value=subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=b"test  ready  ubuntu@22.04\nother  stopped  ubuntu@24.04\n",
            )
        ),
    )
    assert ws.exists() is True


def test_workshop_exists_returns_false_when_name_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = Workshop(name="test", project=Path("/tmp/test"))
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(
            return_value=subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=b"other  ready  ubuntu@22.04\n",
            )
        ),
    )
    assert ws.exists() is False


def test_workshop_exists_returns_false_when_not_a_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = Workshop(name="test", project=Path("/tmp/test"))
    exc = subprocess.CalledProcessError(1, [], stderr=b"not a project")
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=exc))
    assert ws.exists() is False


def test_workshop_container_name_returns_none_when_no_lockfile(
    tmp_path: Path,
) -> None:
    ws = Workshop(name="test", project=tmp_path)
    assert ws.container_name() is None


def test_workshop_container_name_reads_lockfile(
    tmp_path: Path,
) -> None:
    lock = tmp_path / ".workshop.lock"
    lock.write_text("abc123\n")
    ws = Workshop(name="test", project=tmp_path)
    assert ws.container_name() == "test-abc123"


def test_workshop_ensure_launched_raises_when_not_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = Workshop(name="test", project=Path("/tmp/test"))
    exc = subprocess.CalledProcessError(1, [], stderr=b"not a project")
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=exc))
    with pytest.raises(WorkshopNotFoundError) as exc_info:
        ws.ensure_launched()
    assert exc_info.value.name == "test"


def test_workshop_ensure_launched_raises_when_not_launched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = Workshop(name="test", project=Path("/tmp/test"))
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(
            side_effect=[
                subprocess.CompletedProcess(
                    args=[], returncode=0, stdout=b"test  ready  ubuntu@22.04\n"
                ),
                subprocess.CalledProcessError(1, [], stderr=b"workshop not launched"),
            ]
        ),
    )
    with pytest.raises(WorkshopNotLaunchedError) as exc_info:
        ws.ensure_launched()
    assert exc_info.value.name == "test"


def test_workshop_exec_builds_correct_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = Workshop(name="test", project=Path("/tmp/test"))
    run = Mock(
        side_effect=[
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout=b"test  ready  ubuntu@22.04\n"
            ),
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout=b"name: test\nstatus: ready\n"
            ),
            subprocess.CompletedProcess(args=[], returncode=0),
        ],
    )
    monkeypatch.setattr(subprocess, "run", run)

    ws.exec_(["echo", "hello"], check=True, capture_output=True)

    assert run.call_count == 3
    assert run.call_args_list[2] == call(
        [
            "workshop",
            "exec",
            "--non-interactive",
            "--project",
            "/tmp/test",
            "test",
            "--",
            "echo",
            "hello",
        ],
        check=True,
        capture_output=True,
    )


def test_workshop_popen_builds_correct_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = Workshop(name="test", project=Path("/tmp/test"))
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(
            side_effect=[
                subprocess.CompletedProcess(
                    args=[], returncode=0, stdout=b"test  ready  ubuntu@22.04\n"
                ),
                subprocess.CompletedProcess(
                    args=[], returncode=0, stdout=b"name: test\nstatus: ready\n"
                ),
            ]
        ),
    )
    popen = Mock(spec=subprocess.Popen)
    monkeypatch.setattr(subprocess, "Popen", popen)

    ws.popen(["echo", "hello"], stdout=subprocess.PIPE)

    popen.assert_called_once_with(
        [
            "workshop",
            "exec",
            "--non-interactive",
            "--project",
            "/tmp/test",
            "test",
            "--",
            "echo",
            "hello",
        ],
        stdout=subprocess.PIPE,
    )


def test_workshop_popen_interactive_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = Workshop(name="test", project=Path("/tmp/test"))
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(
            side_effect=[
                subprocess.CompletedProcess(
                    args=[], returncode=0, stdout=b"test  ready  ubuntu@22.04\n"
                ),
                subprocess.CompletedProcess(
                    args=[], returncode=0, stdout=b"name: test\nstatus: ready\n"
                ),
            ]
        ),
    )
    popen = Mock()
    monkeypatch.setattr(subprocess, "Popen", popen)

    ws.popen(["bash"], interactive=True)

    popen.assert_called_once()
    assert popen.call_args[0][0][2] == "--interactive"


def test_workshop_refresh_builds_correct_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = Workshop(name="test", project=Path("/tmp/test"))
    run = Mock(return_value=subprocess.CompletedProcess(args=[], returncode=0))
    monkeypatch.setattr(subprocess, "run", run)

    ws.refresh()

    run.assert_called_once_with(
        ["workshop", "refresh", "test", "--project", "/tmp/test"],
        check=True,
    )


def test_workshop_launch_builds_correct_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = Workshop(name="test", project=Path("/tmp/test"))
    run = Mock(return_value=subprocess.CompletedProcess(args=[], returncode=0))
    monkeypatch.setattr(subprocess, "run", run)

    ws.launch()

    run.assert_called_once_with(
        ["workshop", "launch", "test", "--project", "/tmp/test"],
        check=True,
    )


def test_workshop_restore_builds_correct_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = Workshop(name="test", project=Path("/tmp/test"))
    run = Mock(return_value=subprocess.CompletedProcess(args=[], returncode=0))
    monkeypatch.setattr(subprocess, "run", run)

    ws.restore()

    run.assert_called_once_with(
        ["workshop", "restore", "test", "--project", "/tmp/test"],
        check=True,
    )


class TestTunnelInterface:
    @staticmethod
    def make_tunnel(name: str = "test", project: Path | None = None, exec_=None):
        if project is None:
            project = Path("/tmp/test")
        if exec_ is None:
            exec_ = Mock(
                return_value=subprocess.CompletedProcess(args=[], returncode=0)
            )
        return TunnelInterface(name, project, exec_=exec_)

    def test_connections_parses_rows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ti = self.make_tunnel()
        run = Mock(
            return_value=subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="INTERFACE  PLUG            SLOT          NOTES\n"
                "tunnel     microjail:app   system:app    manual\n",
            )
        )
        monkeypatch.setattr(subprocess, "run", run)
        assert ti.connections() == [("microjail:app", "system:app")]

    def test_connections_filters_non_tunnel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ti = self.make_tunnel()
        run = Mock(
            return_value=subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="INTERFACE  PLUG         SLOT          NOTES\n"
                "mount      microjail:data  system:mount  -\n"
                "tunnel     microjail:app  system:app    manual\n",
            )
        )
        monkeypatch.setattr(subprocess, "run", run)
        assert ti.connections() == [("microjail:app", "system:app")]

    def test_connections_returns_empty_when_no_header(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ti = self.make_tunnel()
        monkeypatch.setattr(
            subprocess,
            "run",
            Mock(
                return_value=subprocess.CompletedProcess(
                    args=[], returncode=0, stdout=""
                )
            ),
        )
        assert ti.connections() == []

    def test_connections_skips_blank_lines(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ti = self.make_tunnel()
        run = Mock(
            return_value=subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="INTERFACE  PLUG            SLOT          NOTES\n"
                "\n"
                "tunnel     microjail:app   system:app    manual\n",
            )
        )
        monkeypatch.setattr(subprocess, "run", run)
        assert ti.connections() == [("microjail:app", "system:app")]

    def test_connect_builds_expected_command(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ti = self.make_tunnel()
        run = Mock(return_value=subprocess.CompletedProcess(args=[], returncode=0))
        monkeypatch.setattr(subprocess, "run", run)
        ti.connect("microjail", "app", "system", "app")
        run.assert_called_once_with(
            [
                "workshop",
                "connect",
                "test/microjail:app",
                "test/system:app",
                "--project",
                "/tmp/test",
            ],
            check=True,
            capture_output=True,
        )

    def test_disconnect_ignores_not_connected_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ti = self.make_tunnel()
        exc = subprocess.CalledProcessError(1, [], stderr=b"not connected")
        monkeypatch.setattr(subprocess, "run", Mock(side_effect=exc))
        ti.disconnect("microjail", "app", "system", "app")  # does not raise

    def test_disconnect_raises_other_errors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ti = self.make_tunnel()
        exc = subprocess.CalledProcessError(1, [], stderr=b"something else")
        monkeypatch.setattr(subprocess, "run", Mock(side_effect=exc))
        with pytest.raises(subprocess.CalledProcessError):
            ti.disconnect("microjail", "app", "system", "app")

    def test_endpoint_reachable_returns_probe_success(self) -> None:
        ti = self.make_tunnel()
        assert ti.endpoint_reachable("127.0.0.1", "8080") is True
        ti._exec.assert_called_once_with(
            ["bash", "-c", ": >/dev/tcp/127.0.0.1/8080"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_endpoint_reachable_returns_false_on_timeout(self) -> None:
        exec_ = Mock(side_effect=subprocess.TimeoutExpired(cmd=[], timeout=5))
        ti = self.make_tunnel(exec_=exec_)
        assert ti.endpoint_reachable("127.0.0.1", "8080") is False

    def test_endpoint_reachable_returns_false_on_nonzero(self) -> None:
        exec_ = Mock(return_value=subprocess.CompletedProcess(args=[], returncode=1))
        ti = self.make_tunnel(exec_=exec_)
        assert ti.endpoint_reachable("127.0.0.1", "8080") is False

    def test_add_plug_creates_new(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ti = self.make_tunnel()
        read = Mock(return_value=MicrojailSdk())
        write = Mock()
        monkeypatch.setattr(workshop, "read_microjail_sdk", read)
        monkeypatch.setattr(workshop, "write_microjail_sdk", write)
        ti.add_plug("api", "127.0.0.1:8080")
        assert write.call_args[0][1].plugs["api"] == TunnelEntry(
            interface="tunnel", endpoint="127.0.0.1:8080"
        )

    def test_add_plug_is_noop_when_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ti = self.make_tunnel()
        sdk = MicrojailSdk()
        sdk.plugs["api"] = TunnelEntry(interface="tunnel", endpoint="127.0.0.1:8080")
        read = Mock(return_value=sdk)
        write = Mock()
        monkeypatch.setattr(workshop, "read_microjail_sdk", read)
        monkeypatch.setattr(workshop, "write_microjail_sdk", write)
        ti.add_plug("api", "127.0.0.1:8080")
        write.assert_not_called()

    def test_remove_plug_removes_existing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ti = self.make_tunnel()
        sdk = MicrojailSdk()
        sdk.plugs["api"] = TunnelEntry(interface="tunnel", endpoint="127.0.0.1:8080")
        sdk.plugs["other"] = TunnelEntry(interface="tunnel", endpoint="127.0.0.1:9090")
        read = Mock(return_value=sdk)
        write = Mock()
        monkeypatch.setattr(workshop, "read_microjail_sdk", read)
        monkeypatch.setattr(workshop, "write_microjail_sdk", write)
        result = ti.remove_plug("api")
        assert result is True
        assert "api" not in write.call_args[0][1].plugs

    def test_remove_plug_reports_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ti = self.make_tunnel()
        sdk = MicrojailSdk()
        sdk.plugs["api"] = TunnelEntry(interface="tunnel", endpoint="127.0.0.1:8080")
        read = Mock(return_value=sdk)
        write = Mock()
        monkeypatch.setattr(workshop, "read_microjail_sdk", read)
        monkeypatch.setattr(workshop, "write_microjail_sdk", write)
        result = ti.remove_plug("api")
        assert result is False

    def test_remove_plug_is_noop_when_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ti = self.make_tunnel()
        read = Mock(return_value=MicrojailSdk())
        write = Mock()
        monkeypatch.setattr(workshop, "read_microjail_sdk", read)
        monkeypatch.setattr(workshop, "write_microjail_sdk", write)
        ti.remove_plug("missing")
        write.assert_not_called()

    def test_add_slot_creates_new(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ti = self.make_tunnel()
        read = Mock(return_value=WorkshopConfig(name="test"))
        write = Mock()
        monkeypatch.setattr(workshop, "read_workshop_yaml", read)
        monkeypatch.setattr(workshop, "write_workshop_yaml", write)
        ti.add_slot("api", "127.0.0.1:8080")
        written = write.call_args[0][2]
        system = next(s for s in written.sdks if s.name == "system")
        assert system.slots["api"] == TunnelEntry(
            interface="tunnel", endpoint="127.0.0.1:8080"
        )

    def test_add_slot_is_noop_when_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ti = self.make_tunnel()
        data = WorkshopConfig(name="test")
        project_sdk = WorkshopSdk(name="project-microjail")
        system = WorkshopSdk(name="system")
        system.slots["api"] = TunnelEntry(interface="tunnel", endpoint="127.0.0.1:8080")
        data.sdks.extend([project_sdk, system])
        read = Mock(return_value=data)
        write = Mock()
        monkeypatch.setattr(workshop, "read_workshop_yaml", read)
        monkeypatch.setattr(workshop, "write_workshop_yaml", write)
        ti.add_slot("api", "127.0.0.1:8080")
        write.assert_not_called()

    def test_remove_slot_removes_existing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ti = self.make_tunnel()
        data = WorkshopConfig(name="test")
        project_sdk = WorkshopSdk(name="project-microjail")
        system = WorkshopSdk(name="system")
        system.slots["api"] = TunnelEntry(interface="tunnel", endpoint="127.0.0.1:8080")
        data.sdks.extend([project_sdk, system])
        read = Mock(return_value=data)
        write = Mock()
        monkeypatch.setattr(workshop, "read_workshop_yaml", read)
        monkeypatch.setattr(workshop, "write_workshop_yaml", write)
        ti.remove_slot("api")
        written = write.call_args[0][2]
        system_written = next(s for s in written.sdks if s.name == "system")
        assert "api" not in system_written.slots

    def test_remove_slot_is_noop_when_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ti = self.make_tunnel()
        data = WorkshopConfig(name="test")
        data.sdks.append(WorkshopSdk(name="system"))
        read = Mock(return_value=data)
        write = Mock()
        monkeypatch.setattr(workshop, "read_workshop_yaml", read)
        monkeypatch.setattr(workshop, "write_workshop_yaml", write)
        ti.remove_slot("missing")
        write.assert_not_called()
