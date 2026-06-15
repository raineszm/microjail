from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest
from anyio.abc import Process

from microjail.adapters import workshop
from microjail.adapters.workshop import (
    WorkshopExistsError,
)
from tests.marks import requires_workshop

pytestmark = [
    requires_workshop(),
]


@pytest.fixture
async def initialized_workshop(tmp_workshop):
    await workshop.init(tmp_workshop.name, project=tmp_workshop.path)
    return tmp_workshop


async def test_init_minimal_args(tmp_workshop):
    await workshop.init(tmp_workshop.name, project=tmp_workshop.path)


async def test_init_throws_on_existing_workshop(initialized_workshop):
    with pytest.raises(WorkshopExistsError):
        await workshop.init(
            initialized_workshop.name, project=initialized_workshop.path
        )


async def test_ready_after_launch(launched_workshop):
    info = await workshop.info(launched_workshop.name, project=launched_workshop.path)
    assert info is not None
    assert info.status == "ready"


async def test_info_returns_none_if_not_launched(initialized_workshop):
    info = await workshop.info(
        initialized_workshop.name, project=initialized_workshop.path
    )
    assert info is None


async def test_get_container_returns_none_if_not_launched(initialized_workshop):
    container = await workshop.get_container(
        initialized_workshop.name, project=initialized_workshop.path
    )
    assert container is None


def test_lxd_project_returns_existing_project():
    project = workshop.lxd_project()
    assert project is not None
    assert project.startswith("workshop.")


async def test_get_container_returns_container_if_launched(launched_workshop):
    container = await workshop.get_container(
        launched_workshop.name, project=launched_workshop.path
    )
    assert container is not None


async def test_exec_executes_command_in_launched_workshop_container(launched_workshop):
    marker = "/tmp/microjail-workshop-exec-marker"
    await workshop.exec_(
        launched_workshop.name,
        launched_workshop.path,
        ["rm", "-f", marker],
    )

    await workshop.exec_(
        launched_workshop.name,
        launched_workshop.path,
        ["sh", "-c", f"echo ran > {marker}"],
    )

    result = await workshop.exec_(
        launched_workshop.name,
        launched_workshop.path,
        ["cat", marker],
        capture_output=True,
        text=True,
    )
    assert result.stdout == "ran\n"


async def test_exec_returns_stdout_to_caller(launched_workshop):
    result = await workshop.exec_(
        launched_workshop.name,
        launched_workshop.path,
        ["printf", "from stdout"],
        capture_output=True,
        text=True,
    )
    assert result.stdout == "from stdout"


async def test_exec_passes_stdin_to_command(launched_workshop):
    result = await workshop.exec_(
        launched_workshop.name,
        launched_workshop.path,
        ["cat"],
        input=b"from stdin\n",
        capture_output=True,
        text=True,
    )
    assert result.stdout == "from stdin\n"


async def test_exec_fails_if_workshop_is_not_launched(initialized_workshop):
    with pytest.raises(workshop.WorkshopNotLaunchedError) as exc_info:
        await workshop.exec_(
            initialized_workshop.name,
            initialized_workshop.path,
            ["true"],
        )

    assert exc_info.value.name == initialized_workshop.name
    assert exc_info.value.project == initialized_workshop.path


async def test_exec_fails_if_workshop_does_not_exist(tmp_workshop):
    with pytest.raises(workshop.WorkshopNotFoundError) as exc_info:
        await workshop.exec_(
            tmp_workshop.name,
            tmp_workshop.path,
            ["true"],
        )

    assert exc_info.value.name == tmp_workshop.name
    assert exc_info.value.project == tmp_workshop.path


async def test_exists_returns_true_for_existing_workshop(initialized_workshop):
    assert await workshop.exists(
        initialized_workshop.name, project=initialized_workshop.path
    )


async def test_exists_returns_false_for_nonexistent_workshop(tmp_workshop):
    assert not await workshop.exists(tmp_workshop.name, project=tmp_workshop.path)


async def test_exists_returns_false_if_name_doesnt_match(initialized_workshop):
    assert not await workshop.exists("bad-name", project=initialized_workshop.path)


@patch("microjail.adapters.workshop.anyio.run_process", new_callable=AsyncMock)
async def test_workshop_init_subprocess_receives_project_flag(
    mock_run: AsyncMock,
) -> None:
    # Set return value to CompletedProcess to avoid errors decoding stdout
    mock_run.return_value = MagicMock()
    mock_run.return_value.stdout = b""
    await workshop.init("myproj", project=Path("/tmp/myproject"))

    args, _ = mock_run.call_args
    cmd = args[0]
    assert "--project" in cmd
    project_idx = cmd.index("--project")
    assert cmd[project_idx + 1] == "/tmp/myproject"


@patch("microjail.adapters.workshop.anyio.run_process", new_callable=AsyncMock)
async def test_workshop_launch_subprocess_receives_project_flag(
    mock_run: AsyncMock,
) -> None:
    mock_run.return_value = MagicMock()
    mock_run.return_value.stdout = b""
    await workshop.launch("myproj", project=Path("/tmp/myproject"))

    args, _ = mock_run.call_args
    cmd = args[0]
    assert "--project" in cmd
    project_idx = cmd.index("--project")
    assert cmd[project_idx + 1] == "/tmp/myproject"


async def test_popen_executes_command_in_background(launched_workshop) -> None:
    proc = await workshop.popen(
        launched_workshop.name,
        launched_workshop.path,
        ["sleep", "2"],
    )
    try:
        assert isinstance(proc, Process)
        assert proc.returncode is None  # Still running in background
    finally:
        proc.terminate()
        await proc.wait()


async def test_microjail_popen_executes_command_in_background(
    launched_workshop,
) -> None:
    from microjail.lockdown import Lockdown
    from microjail.microjail import MicroJail

    mj = MicroJail(
        name=launched_workshop.name,
        project_path=launched_workshop.path,
        lockdown=Lockdown.default(),
    )
    proc = await mj.popen(["sleep", "2"])
    try:
        assert isinstance(proc, Process)
        assert proc.returncode is None
    finally:
        proc.terminate()
        await proc.wait()


async def test_popen_interactive_direct_inheritance(launched_workshop) -> None:
    proc = await workshop.popen(
        launched_workshop.name,
        launched_workshop.path,
        ["sh", "-c", "echo interactive-ok"],
        interactive=True,
        stdout=workshop.subprocess.PIPE,
    )
    try:
        assert isinstance(proc, Process)
        await proc.wait()
        stdout_bytes = b""
        while True:
            try:
                chunk = await proc.stdout.receive()
                stdout_bytes += chunk
            except anyio.EndOfStream:
                break
        stdout = stdout_bytes.decode()
        assert "interactive-ok" in stdout
    finally:
        if proc.returncode is None:
            proc.terminate()
            await proc.wait()


async def test_popen_interacts_with_standard_streams(launched_workshop) -> None:
    proc = await workshop.popen(
        launched_workshop.name,
        launched_workshop.path,
        ["cat"],
        stdin=workshop.subprocess.PIPE,
        stdout=workshop.subprocess.PIPE,
    )
    try:
        assert isinstance(proc, Process)
        await proc.stdin.send(b"hello-streams\n")
        await proc.stdin.aclose()

        await proc.wait()
        stdout_bytes = b""
        while True:
            try:
                chunk = await proc.stdout.receive()
                stdout_bytes += chunk
            except anyio.EndOfStream:
                break
        stdout = stdout_bytes.decode()
        assert stdout == "hello-streams\n"
    finally:
        if proc.returncode is None:
            proc.terminate()
            await proc.wait()


async def test_popen_fails_if_workshop_does_not_exist(tmp_workshop) -> None:
    with pytest.raises(workshop.WorkshopNotFoundError) as exc_info:
        await workshop.popen(
            tmp_workshop.name,
            tmp_workshop.path,
            ["true"],
        )

    assert exc_info.value.name == tmp_workshop.name
    assert exc_info.value.project == tmp_workshop.path


async def test_popen_fails_if_workshop_is_not_launched(initialized_workshop) -> None:
    with pytest.raises(workshop.WorkshopNotLaunchedError) as exc_info:
        await workshop.popen(
            initialized_workshop.name,
            initialized_workshop.path,
            ["true"],
        )

    assert exc_info.value.name == initialized_workshop.name
    assert exc_info.value.project == initialized_workshop.path
