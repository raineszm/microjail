import getpass
import pwd
import re
import subprocess
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal

import msgspec


class WorkshopInfo(msgspec.Struct):
    name: str
    status: Literal["ready", "pending", "stopped"]


class ContainerInfo(msgspec.Struct):
    name: str


@dataclass
class WorkshopExistsError(Exception):
    name: str
    project: Path


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

    try:
        subprocess.run(
            ["workshop", "init", name, "--sdks", ",".join(sdks)],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        if b"already exists" in exc.stderr:
            raise WorkshopExistsError(name=name, project=Path.cwd()) from exc
        raise


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


def container_name(name: str, project: Path) -> str | None:
    lock_file = project / ".workshop.lock"
    if not lock_file.exists():
        return None
    return f"{name}-{lock_file.read_text(encoding='utf-8').strip()}"


def get_container(name: str, project: Path) -> ContainerInfo | None:
    c_name = container_name(name, project)
    if c_name is None:
        return None

    result = subprocess.run(
        ["lxc", "query", f"/1.0/instances/{c_name}?project={lxd_project()}"],
        check=True,
        capture_output=True,
    )
    return msgspec.json.decode(result.stdout, type=ContainerInfo)
