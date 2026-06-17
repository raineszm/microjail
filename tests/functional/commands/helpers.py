from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

from typer.testing import CliRunner

from microjail.adapters.workshop import Workshop
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
        workshop=Workshop(name=name, project=project),
        lockdown=lockdown or Lockdown.default(),
    )
    microjail.save()
    return microjail


class RecordingCapability:
    fatal: bool = False

    def __init__(self, name: str, checks: list[bool] | None = None) -> None:
        self.name = name
        self.checks = checks or [True]
        self.calls: list[str] = []

    def check(self, microjail: MicroJail) -> bool:
        del microjail
        self.calls.append("check")
        if len(self.checks) > 1:
            return self.checks.pop(0)
        return self.checks[0]

    def provide(self, microjail: MicroJail, batch: object = None) -> None:
        del microjail, batch
        self.calls.append("provide")

    def revoke(self, microjail: MicroJail, batch: object = None) -> None:
        del microjail, batch
        self.calls.append("revoke")


class RecordingGate:
    def __init__(self, name: str, checks: list[bool] | None = None) -> None:
        self.name = name
        self.checks = checks or [True]
        self.calls: list[str] = []

    def check(self, microjail: MicroJail) -> bool:
        del microjail
        self.calls.append("check")
        if len(self.checks) > 1:
            return self.checks.pop(0)
        return self.checks[0]

    def enforce(self, microjail: MicroJail) -> None:
        del microjail
        self.calls.append("enforce")

    def release(self, microjail: MicroJail) -> None:
        del microjail
        self.calls.append("release")


def completed_process(returncode: int = 0) -> Any:
    return Mock(returncode=returncode)
