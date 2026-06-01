"""Unit tests for workshop/client.py prerequisite checking."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from microjail.workshop import client

FAKE_PROJECT = Path("/tmp/fake-project")


def test_check_prerequisites_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    """check_prerequisites succeeds when both workshop and lxc are available."""
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/workshop")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        client.check_prerequisites()  # must not raise


def test_check_prerequisites_missing_workshop(monkeypatch: pytest.MonkeyPatch) -> None:
    """check_prerequisites raises RuntimeError naming 'workshop' when absent."""
    monkeypatch.setattr("shutil.which", lambda _: None)
    with pytest.raises(RuntimeError, match="'workshop' not found"):
        client.check_prerequisites()


def test_check_prerequisites_lxc_not_running(monkeypatch: pytest.MonkeyPatch) -> None:
    """check_prerequisites raises RuntimeError when lxc version fails."""
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/workshop")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr=b"LXD socket not found")
        with pytest.raises(RuntimeError, match="LXD is not available"):
            client.check_prerequisites()


def test_environment_exists_true() -> None:
    """environment_exists returns True when workshop info exits 0."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        assert client.environment_exists("myenv", FAKE_PROJECT) is True
        mock_run.assert_called_once_with(
            ["workshop", "info", "myenv", "--project", str(FAKE_PROJECT)],
            capture_output=True,
            check=False,
        )


def test_environment_exists_false() -> None:
    """environment_exists returns False when workshop info exits non-zero."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr=b"not found")
        assert client.environment_exists("ghost", FAKE_PROJECT) is False


def test_verify_exists_raises_on_missing() -> None:
    """verify_exists raises RuntimeError when workshop info returns non-zero."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr=b"Error: not found")
        with pytest.raises(RuntimeError, match="was not found after creation"):
            client.verify_exists("myenv", FAKE_PROJECT)


def test_launch_raises_on_failure() -> None:
    """Launch raises RuntimeError with workshop stderr on non-zero exit."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr=b"invalid yaml")
        with pytest.raises(RuntimeError, match="creation failed"):
            client.launch("myenv", FAKE_PROJECT)


def test_launch_passes_project_flag() -> None:
    """Launch invokes workshop launch with --project <project_dir>."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        client.launch("myenv", FAKE_PROJECT)
        mock_run.assert_called_once_with(
            ["workshop", "launch", "myenv", "--project", str(FAKE_PROJECT)],
            capture_output=True,
            check=False,
        )


def test_refresh_passes_project_flag() -> None:
    """Refresh invokes workshop refresh with --project <project_dir>."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        client.refresh("myenv", FAKE_PROJECT)
        mock_run.assert_called_once_with(
            ["workshop", "refresh", "myenv", "--project", str(FAKE_PROJECT)],
            capture_output=True,
            check=False,
        )


def test_refresh_raises_on_failure() -> None:
    """Refresh raises RuntimeError with workshop stderr on non-zero exit."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr=b"not Ready")
        with pytest.raises(RuntimeError, match="refresh failed"):
            client.refresh("myenv", FAKE_PROJECT)
