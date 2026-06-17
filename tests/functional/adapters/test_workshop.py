import subprocess
from pathlib import Path

import pytest

from microjail.adapters import workshop
from microjail.adapters.workshop import Workshop, WorkshopExistsError
from tests.marks import requires_lxd, requires_workshop

pytestmark = [
    requires_lxd(),
    requires_workshop(),
]


class FakeExecutor:
    def __init__(self, return_value=None):
        self.calls = []
        self.return_value = return_value

    def run(self, cmd, *args, **kwargs):
        self.calls.append((cmd, args, kwargs))
        if self.return_value is not None:
            return self.return_value
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"")

    def popen(self, cmd, *args, **kwargs):
        from unittest.mock import MagicMock

        self.calls.append((cmd, args, kwargs))
        return MagicMock(spec=subprocess.Popen)


@pytest.fixture
def initialized_workshop(tmp_workshop):
    tmp_workshop.init(tmp_workshop.name, tmp_workshop.project)
    return tmp_workshop


def test_init_minimal_args(tmp_workshop):
    Workshop.init(tmp_workshop.name, tmp_workshop.project)


def test_init_throws_on_existing_workshop(initialized_workshop):
    with pytest.raises(WorkshopExistsError):
        Workshop.init(initialized_workshop.name, initialized_workshop.project)


def test_ready_after_launch(launched_workshop):
    info = launched_workshop.info()
    assert info is not None
    assert info.status == "ready"


def test_info_returns_none_if_not_launched(initialized_workshop):
    info = initialized_workshop.info()
    assert info is None


def test_get_container_returns_none_if_not_launched(initialized_workshop):
    container = initialized_workshop.get_container()
    assert container is None


def test_lxd_project_returns_existing_project():
    ws = Workshop(name="test", project=Path("/tmp"))
    project = ws.lxd_project
    assert project is not None
    assert project.startswith("workshop.")


def test_get_container_returns_container_if_launched(launched_workshop):
    container = launched_workshop.get_container()
    assert container is not None


def test_exec_executes_command_in_launched_workshop_container(launched_workshop):
    marker = "/tmp/microjail-workshop-exec-marker"
    launched_workshop.exec_(["sh", "-c", f"echo ran > {marker}"])
    container = launched_workshop.get_container()
    assert container is not None

    result = subprocess.run(
        [
            "lxc",
            "--project",
            launched_workshop.lxd_project,
            "exec",
            container.name,
            "--",
            "cat",
            marker,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout == "ran\n"


def test_exec_returns_stdout_to_caller(launched_workshop):
    result = launched_workshop.exec_(
        ["printf", "from stdout"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == "from stdout"


def test_exec_passes_stdin_to_command(launched_workshop):
    result = launched_workshop.exec_(
        ["cat"],
        input="from stdin\n",
        capture_output=True,
        text=True,
    )
    assert result.stdout == "from stdin\n"


def test_exec_fails_if_workshop_is_not_launched(initialized_workshop):
    with pytest.raises(workshop.WorkshopNotLaunchedError) as exc_info:
        initialized_workshop.exec_(["true"])
    assert exc_info.value.name == initialized_workshop.name
    assert exc_info.value.project == initialized_workshop.project


def test_exec_fails_if_workshop_does_not_exist(tmp_workshop):
    with pytest.raises(workshop.WorkshopNotFoundError) as exc_info:
        tmp_workshop.exec_(["true"])
    assert exc_info.value.name == tmp_workshop.name
    assert exc_info.value.project == tmp_workshop.project


def test_exists_returns_true_for_existing_workshop(initialized_workshop):
    assert initialized_workshop.exists()


def test_exists_returns_false_for_nonexistent_workshop(tmp_workshop):
    assert not tmp_workshop.exists()


def test_exists_returns_false_if_name_doesnt_match(initialized_workshop):
    ws = Workshop(name="bad-name", project=initialized_workshop.project)
    assert not ws.exists()


def test_workshop_init_subprocess_receives_project_flag() -> None:
    fake_exec = FakeExecutor()
    Workshop.init("myproj", project=Path("/tmp/myproject"), executor=fake_exec)

    assert len(fake_exec.calls) == 1
    cmd = fake_exec.calls[0][0]
    assert "--project" in cmd
    project_idx = cmd.index("--project")
    assert cmd[project_idx + 1] == "/tmp/myproject"


def test_workshop_launch_subprocess_receives_project_flag() -> None:
    fake_exec = FakeExecutor()
    ws = Workshop("myproj", project=Path("/tmp/myproject"), executor=fake_exec)
    ws.launch()

    assert len(fake_exec.calls) == 1
    cmd = fake_exec.calls[0][0]
    assert "--project" in cmd
    project_idx = cmd.index("--project")
    assert cmd[project_idx + 1] == "/tmp/myproject"


def test_popen_executes_command_in_background(launched_workshop) -> None:
    proc = launched_workshop.popen(["sleep", "2"])
    try:
        assert isinstance(proc, subprocess.Popen)
        assert proc.poll() is None  # Still running in background
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_microjail_popen_executes_command_in_background(launched_workshop) -> None:
    from microjail.lockdown import Lockdown
    from microjail.microjail import MicroJail

    mj = MicroJail(
        workshop=launched_workshop,
        lockdown=Lockdown.default(),
    )
    proc = mj.popen(["sleep", "2"])
    try:
        assert isinstance(proc, subprocess.Popen)
        assert proc.poll() is None
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_popen_interactive_direct_inheritance(launched_workshop) -> None:
    proc = launched_workshop.popen(
        ["sh", "-c", "echo interactive-ok"],
        interactive=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert isinstance(proc, subprocess.Popen)
        stdout, _ = proc.communicate(timeout=5)
        assert "interactive-ok" in stdout
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)


def test_popen_interacts_with_standard_streams(launched_workshop) -> None:
    proc = launched_workshop.popen(
        ["cat"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert isinstance(proc, subprocess.Popen)
        stdout, _ = proc.communicate(input="hello-streams\n", timeout=5)
        assert stdout == "hello-streams\n"
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)


def test_popen_fails_if_workshop_does_not_exist(tmp_workshop) -> None:
    with pytest.raises(workshop.WorkshopNotFoundError) as exc_info:
        tmp_workshop.popen(["true"])
    assert exc_info.value.name == tmp_workshop.name
    assert exc_info.value.project == tmp_workshop.project


def test_popen_fails_if_workshop_is_not_launched(initialized_workshop) -> None:
    with pytest.raises(workshop.WorkshopNotLaunchedError) as exc_info:
        initialized_workshop.popen(["true"])
    assert exc_info.value.name == initialized_workshop.name
    assert exc_info.value.project == initialized_workshop.project
