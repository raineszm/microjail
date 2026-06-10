from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

from typer.testing import CliRunner

from microjail.cli import app
from microjail.lockdown import Lockdown
from microjail.microjail import MicroJail

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def invoke_in_project(
    monkeypatch: pytest.MonkeyPatch,
    project: Path,
    args: list[str],
):
    monkeypatch.chdir(project)
    return CliRunner().invoke(app, args)


def save_config(
    project: Path, *, name: str = "test-jail", lockdown: Lockdown | None = None
) -> MicroJail:
    microjail = MicroJail(
        name=name,
        project_path=project,
        lockdown=lockdown or Lockdown.default(),
    )
    microjail.save()
    return microjail


class RecordingCapability:
    def __init__(self, name: str, checks: list[bool] | None = None) -> None:
        self.name = name
        self.checks = checks or [True]
        self.calls: list[str] = []

    def check(self, _microjail: MicroJail) -> bool:
        self.calls.append("check")
        if len(self.checks) > 1:
            return self.checks.pop(0)
        return self.checks[0]

    def provide(self, _microjail: MicroJail) -> None:
        self.calls.append("provide")

    def revoke(self, _microjail: MicroJail) -> None:
        self.calls.append("revoke")


class RecordingGate:
    def __init__(self, name: str, checks: list[bool] | None = None) -> None:
        self.name = name
        self.checks = checks or [True]
        self.calls: list[str] = []

    def check(self, _microjail: MicroJail) -> bool:
        self.calls.append("check")
        if len(self.checks) > 1:
            return self.checks.pop(0)
        return self.checks[0]

    def enforce(self, _microjail: MicroJail) -> None:
        self.calls.append("enforce")

    def release(self, _microjail: MicroJail) -> None:
        self.calls.append("release")


def completed_process(returncode: int = 0) -> Any:
    return Mock(returncode=returncode)
