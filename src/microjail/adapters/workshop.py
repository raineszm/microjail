import getpass
import pwd
import re
import subprocess
from functools import cache
from typing import TYPE_CHECKING, Literal

import msgspec

if TYPE_CHECKING:
    from pathlib import Path


class WorkshopInfo(msgspec.Struct):
    name: str
    status: Literal["ready", "pending", "stopped"]


class ContainerInfo(msgspec.Struct): ...


_VALID_PROJECT_SUFFIX = re.compile(r"^[a-zA-Z][-a-zA-Z0-9.]{0,31}$")


@cache
def project_suffix() -> str:
    username = getpass.getuser()

    if _VALID_PROJECT_SUFFIX.fullmatch(username):
        return username

    return str(pwd.getpwnam(username).pw_uid)


def lxd_project() -> str:
    return f"workshop.{project_suffix()}"


def init(name: str, sdks: list[str] | None = None):
    if sdks is None:
        sdks = []
    sdks = sdks.copy()
    sdks.append("direnv")
    subprocess.run(["workshop", "init", name, "--sdks", ",".join(sdks)], check=True)


def launch(name: str, project: Path):
    subprocess.run(["workshop", "launch", name, "--project", str(project)], check=True)


def info(name: str, project: Path) -> WorkshopInfo | None:
    try:
        result = subprocess.run(
            ["workshop", "info", name, "--project", str(project)],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        if b"workshop not launched" in exc.stderr:
            return None
        raise
    return msgspec.yaml.decode(result.stdout, type=WorkshopInfo)


def get_container(name: str, project: Path) -> ContainerInfo | None:  # noqa: ARG001
    return None
