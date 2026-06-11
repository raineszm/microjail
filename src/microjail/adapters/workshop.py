import getpass
import os
import pwd
import re
import subprocess
import tempfile
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


@dataclass
class WorkshopNotFoundError(Exception):
    name: str
    project: Path


@dataclass
class WorkshopNotLaunchedError(Exception):
    name: str
    project: Path


@dataclass
class WorkshopConfigError(Exception):
    name: str
    project: Path


@dataclass
class MicrojailSdkConfigError(Exception):
    project: Path


_VALID_PROJECT_SUFFIX = re.compile(r"^[a-zA-Z][-a-zA-Z0-9.]{0,31}$")
_WORKSHOP_DIRNAME = ".workshop"
_MICROJAIL_SDK_NAME = "microjail"
_PROJECT_MICROJAIL_SDK_NAME = "project-microjail"
_SYSTEM_SDK_NAME = "system"
_TUNNEL_INTERFACE = "tunnel"
_EGRESS_PROBE_TIMEOUT = 10


class TunnelEntry(msgspec.Struct):
    interface: str
    endpoint: str


class WorkshopSdk(msgspec.Struct, omit_defaults=True):
    name: str
    slots: dict[str, TunnelEntry] = msgspec.field(default_factory=dict)


class WorkshopConfig(msgspec.Struct, omit_defaults=True):
    name: str
    base: str = ""
    sdks: list[WorkshopSdk] = msgspec.field(default_factory=list)


class MicrojailSdk(msgspec.Struct):
    name: str = _MICROJAIL_SDK_NAME
    plugs: dict[str, TunnelEntry] = msgspec.field(default_factory=dict)


def _workshop_dec_hook(expected: type, obj: object) -> object:
    if expected is WorkshopSdk and isinstance(obj, str):
        return WorkshopSdk(name=obj)
    raise NotImplementedError(f"cannot decode object of type {expected.__name__}")


def _atomic_write_yaml(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as tmp:
        tmp.write(msgspec.yaml.encode(data))
        tmp.flush()
        os.fsync(tmp.fileno())
    Path(tmp.name).replace(path)


def _tunnel_entry(endpoint: str) -> TunnelEntry:
    return TunnelEntry(interface=_TUNNEL_INTERFACE, endpoint=endpoint)


def _sdk_entry(workshop_data: WorkshopConfig, name: str) -> WorkshopSdk | None:
    for entry in workshop_data.sdks:
        if entry.name == name:
            return entry
    return None


def connections(name: str, project: Path) -> list[tuple[str, str]]:
    result = subprocess.run(
        ["workshop", "connections", name, "--project", str(project)],
        check=True,
        capture_output=True,
        text=True,
    )
    rows: list[tuple[str, str]] = []
    lines = result.stdout.splitlines()
    if len(lines) < 2:
        return rows
    header = lines[0]
    try:
        plug_start = header.index("PLUG")
        slot_start = header.index("SLOT")
        notes_start = header.index("NOTES")
    except ValueError:
        return rows
    for line in lines[1:]:
        if not line.strip():
            continue
        interface = line[:plug_start].strip()
        if interface != _TUNNEL_INTERFACE:
            continue
        plug = line[plug_start:slot_start].strip()
        slot = line[slot_start:notes_start].strip()
        if plug and slot:
            rows.append((plug, slot))
    return rows


def connect(
    name: str, project: Path, plug_sdk: str, plug: str, slot_sdk: str, slot: str
) -> None:
    subprocess.run(
        [
            "workshop",
            "connect",
            f"{name}/{plug_sdk}:{plug}",
            f"{name}/{slot_sdk}:{slot}",
            "--project",
            str(project),
        ],
        check=True,
        capture_output=True,
    )


def disconnect(
    name: str, project: Path, plug_sdk: str, plug: str, slot_sdk: str, slot: str
) -> None:
    try:
        subprocess.run(
            [
                "workshop",
                "disconnect",
                f"{name}/{plug_sdk}:{plug}",
                f"{name}/{slot_sdk}:{slot}",
                "--project",
                str(project),
            ],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        if b"not connected" in exc.stderr:
            return
        raise


def refresh(name: str, project: Path) -> None:
    subprocess.run(
        ["workshop", "refresh", name, "--project", str(project)],
        check=True,
        capture_output=True,
    )


def restore(name: str, project: Path) -> None:
    subprocess.run(
        ["workshop", "restore", name, "--project", str(project)],
        check=True,
        capture_output=True,
    )


def endpoint_reachable(microjail, host: str, port: int | str) -> bool:
    try:
        result = microjail.exec_(
            ["bash", "-c", f": >/dev/tcp/{host}/{port}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=_EGRESS_PROBE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0


@cache
def project_suffix() -> str:
    username = getpass.getuser()

    if _VALID_PROJECT_SUFFIX.fullmatch(username):
        return username

    return str(pwd.getpwnam(username).pw_uid)


def lxd_project() -> str:
    return f"workshop.{project_suffix()}"


def init(
    name: str,
    project: Path,
    sdks: list[str] | None = None,
    base: str | None = None,
):
    if sdks is None:
        sdks = []
    sdks = sdks.copy()
    sdks.append("direnv")

    cmd = [
        "workshop",
        "init",
        name,
        "--project",
        str(project),
        "--sdks",
        ",".join(sdks),
    ]
    if base is not None:
        cmd.extend(["--base", base])

    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        if b"already exists" in exc.stderr:
            raise WorkshopExistsError(name=name, project=project) from exc
        raise


def launch(name: str, project: Path, **kwargs):
    subprocess.run(
        ["workshop", "launch", name, "--project", str(project)], check=True, **kwargs
    )


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


def exists(name: str, project: Path) -> bool:
    try:
        for line in (
            subprocess.run(
                ["workshop", "list", "--project", str(project), "--no-headers"],
                check=True,
                capture_output=True,
            )
            .stdout.decode("utf-8")
            .splitlines()
        ):
            if line.split()[0] == name:
                return True
    except subprocess.CalledProcessError as exc:
        if b"not a project" in exc.stderr:
            return False
        raise
    return False


def exec_(
    name: str, project: Path, command: list[str], **kwargs
) -> subprocess.CompletedProcess:
    if not exists(name, project):
        raise WorkshopNotFoundError(name=name, project=project)

    if info(name, project) is None:
        raise WorkshopNotLaunchedError(name=name, project=project)

    return subprocess.run(
        [
            "workshop",
            "exec",
            "--non-interactive",
            "--project",
            str(project),
            name,
            "--",
            *command,
        ],
        **kwargs,
    )


def read_workshop_yaml(name: str, project: Path) -> WorkshopConfig:
    path = project / _WORKSHOP_DIRNAME / f"{name}.yaml"
    if not path.exists():
        return WorkshopConfig(name=name)
    try:
        return msgspec.yaml.decode(
            path.read_bytes(),
            type=WorkshopConfig,
            dec_hook=_workshop_dec_hook,
        )
    except msgspec.ValidationError as exc:
        raise WorkshopConfigError(name, project) from exc


def write_workshop_yaml(name: str, project: Path, data: WorkshopConfig) -> None:
    _atomic_write_yaml(project / _WORKSHOP_DIRNAME / f"{name}.yaml", data)


def read_microjail_sdk(project: Path) -> MicrojailSdk:
    path = project / _WORKSHOP_DIRNAME / _MICROJAIL_SDK_NAME / "sdk.yaml"
    if not path.exists():
        return MicrojailSdk()
    try:
        return msgspec.yaml.decode(path.read_bytes(), type=MicrojailSdk)
    except msgspec.ValidationError:
        raise MicrojailSdkConfigError(project) from None


def write_microjail_sdk(project: Path, data: MicrojailSdk) -> None:
    _atomic_write_yaml(
        project / _WORKSHOP_DIRNAME / _MICROJAIL_SDK_NAME / "sdk.yaml", data
    )


def add_tunnel_plug(project: Path, plug_name: str, endpoint: str) -> None:
    data = read_microjail_sdk(project)
    entry = data.plugs.get(plug_name)
    if entry is not None and entry.endpoint == endpoint:
        return
    data.plugs[plug_name] = _tunnel_entry(endpoint)
    write_microjail_sdk(project, data)


def remove_tunnel_plug(project: Path, plug_name: str) -> bool:
    data = read_microjail_sdk(project)
    if plug_name not in data.plugs:
        return bool(data.plugs)
    del data.plugs[plug_name]
    write_microjail_sdk(project, data)
    return bool(data.plugs)


def add_tunnel_slot(name: str, project: Path, slot_name: str, endpoint: str) -> None:
    data = read_workshop_yaml(name, project)
    changed = False
    if _sdk_entry(data, _PROJECT_MICROJAIL_SDK_NAME) is None:
        data.sdks.append(WorkshopSdk(name=_PROJECT_MICROJAIL_SDK_NAME))
        changed = True

    system = _sdk_entry(data, _SYSTEM_SDK_NAME)
    if system is None:
        system = WorkshopSdk(name=_SYSTEM_SDK_NAME)
        data.sdks.append(system)
        changed = True

    entry = system.slots.get(slot_name)
    if entry is None or entry.endpoint != endpoint:
        system.slots[slot_name] = _tunnel_entry(endpoint)
        changed = True

    if changed:
        write_workshop_yaml(name, project, data)


def remove_tunnel_slot(
    name: str, project: Path, slot_name: str, remove_sdk: bool
) -> None:
    data = read_workshop_yaml(name, project)
    system = _sdk_entry(data, _SYSTEM_SDK_NAME)
    if system is None or slot_name not in system.slots:
        return

    del system.slots[slot_name]

    if remove_sdk:
        data.sdks = [
            entry for entry in data.sdks if entry.name != _PROJECT_MICROJAIL_SDK_NAME
        ]

    write_workshop_yaml(name, project, data)
