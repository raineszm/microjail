import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from microjail.adapters import workshop
from microjail.adapters.workshop import WorkshopExistsError
from tests.marks import requires_workshop

pytestmark = [
    requires_workshop(),
]


@pytest.fixture
def initialized_workshop(tmp_workshop):
    workshop.init(tmp_workshop.name, project=tmp_workshop.path)
    return tmp_workshop


def test_init_minimal_args(tmp_workshop):
    workshop.init(tmp_workshop.name, project=tmp_workshop.path)


def test_init_throws_on_existing_workshop(initialized_workshop):
    with pytest.raises(WorkshopExistsError):
        workshop.init(initialized_workshop.name, project=initialized_workshop.path)


def test_ready_after_launch(launched_workshop):
    info = workshop.info(launched_workshop.name, project=launched_workshop.path)
    assert info is not None
    assert info.status == "ready"


def test_info_returns_none_if_not_launched(initialized_workshop):
    info = workshop.info(initialized_workshop.name, project=initialized_workshop.path)
    assert info is None


def test_get_container_returns_none_if_not_launched(initialized_workshop):
    container = workshop.get_container(
        initialized_workshop.name, project=initialized_workshop.path
    )
    assert container is None


def test_lxd_project_returns_existing_project():
    project = workshop.lxd_project()
    assert project is not None
    assert project.startswith("workshop.")


def test_get_container_returns_container_if_launched(launched_workshop):
    container = workshop.get_container(
        launched_workshop.name, project=launched_workshop.path
    )
    assert container is not None


def test_exec_executes_command_in_launched_workshop_container(launched_workshop):
    marker = "/tmp/microjail-workshop-exec-marker"

    workshop.exec_(
        launched_workshop.name,
        launched_workshop.path,
        ["sh", "-c", f"echo ran > {marker}"],
    )

    container = workshop.get_container(
        launched_workshop.name, project=launched_workshop.path
    )
    assert container is not None

    result = subprocess.run(
        [
            "lxc",
            "--project",
            workshop.lxd_project(),
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
    result = workshop.exec_(
        launched_workshop.name,
        launched_workshop.path,
        ["printf", "from stdout"],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout == "from stdout"


def test_exec_passes_stdin_to_command(launched_workshop):
    result = workshop.exec_(
        launched_workshop.name,
        launched_workshop.path,
        ["cat"],
        input="from stdin\n",
        capture_output=True,
        text=True,
    )

    assert result.stdout == "from stdin\n"


def test_exec_fails_if_workshop_is_not_launched(initialized_workshop):
    with pytest.raises(workshop.WorkshopNotLaunchedError) as exc_info:
        workshop.exec_(
            initialized_workshop.name,
            initialized_workshop.path,
            ["true"],
        )

    assert exc_info.value.name == initialized_workshop.name
    assert exc_info.value.project == initialized_workshop.path


def test_exec_fails_if_workshop_does_not_exist(tmp_workshop):
    with pytest.raises(workshop.WorkshopNotFoundError) as exc_info:
        workshop.exec_(
            tmp_workshop.name,
            tmp_workshop.path,
            ["true"],
        )

    assert exc_info.value.name == tmp_workshop.name
    assert exc_info.value.project == tmp_workshop.path


def test_exists_returns_true_for_existing_workshop(initialized_workshop):
    assert workshop.exists(initialized_workshop.name, project=initialized_workshop.path)


def test_exists_returns_false_for_nonexistent_workshop(tmp_workshop):
    assert not workshop.exists(tmp_workshop.name, project=tmp_workshop.path)


def test_exists_returns_false_if_name_doesnt_match(initialized_workshop):
    assert not workshop.exists("bad-name", project=initialized_workshop.path)


@patch("subprocess.run")
def test_workshop_init_subprocess_receives_project_flag(mock_run: MagicMock) -> None:
    workshop.init("myproj", project=Path("/tmp/myproject"))

    args, _ = mock_run.call_args
    cmd = args[0]
    assert "--project" in cmd
    project_idx = cmd.index("--project")
    assert cmd[project_idx + 1] == "/tmp/myproject"


@patch("subprocess.run")
def test_workshop_launch_subprocess_receives_project_flag(mock_run: MagicMock) -> None:
    workshop.launch("myproj", project=Path("/tmp/myproject"))

    args, _ = mock_run.call_args
    cmd = args[0]
    assert "--project" in cmd
    project_idx = cmd.index("--project")
    assert cmd[project_idx + 1] == "/tmp/myproject"


def test_popen_executes_command_in_background(launched_workshop) -> None:
    proc = workshop.popen(
        launched_workshop.name,
        launched_workshop.path,
        ["sleep", "2"],
    )
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
        name=launched_workshop.name,
        project_path=launched_workshop.path,
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
    proc = workshop.popen(
        launched_workshop.name,
        launched_workshop.path,
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
    proc = workshop.popen(
        launched_workshop.name,
        launched_workshop.path,
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
        workshop.popen(
            tmp_workshop.name,
            tmp_workshop.path,
            ["true"],
        )

    assert exc_info.value.name == tmp_workshop.name
    assert exc_info.value.project == tmp_workshop.path


def test_popen_fails_if_workshop_is_not_launched(initialized_workshop) -> None:
    with pytest.raises(workshop.WorkshopNotLaunchedError) as exc_info:
        workshop.popen(
            initialized_workshop.name,
            initialized_workshop.path,
            ["true"],
        )

    assert exc_info.value.name == initialized_workshop.name
    assert exc_info.value.project == initialized_workshop.path
