"""Shared test helpers — importable by all test layers."""

import socket
from dataclasses import dataclass
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING

from microjail.adapters import workshop

if TYPE_CHECKING:
    from collections.abc import Generator


@dataclass(frozen=True)
class SharedWorkshop:
    name: str
    path: Path


def has_network_egress(ws: SharedWorkshop) -> bool:
    result = workshop.exec_(
        ws.name,
        ws.path,
        [
            "python3",
            "-c",
            "import socket; socket.create_connection(('1.1.1.1', 443), timeout=5).close()",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.returncode == 0


def can_write_microjail_config(ws: SharedWorkshop) -> bool:
    result = workshop.exec_(
        ws.name,
        ws.path,
        ["test", "-w", "/project/.microjail/config.yaml"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def can_append_microjail_config(ws: SharedWorkshop) -> bool:
    result = workshop.exec_(
        ws.name,
        ws.path,
        ["sh", "-c", "echo probe >> /project/.microjail/config.yaml"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def can_roundtrip_project_file(ws: SharedWorkshop) -> bool:
    (ws.path / "input.txt").write_text("ok", encoding="utf-8")
    result = workshop.exec_(
        ws.name,
        ws.path,
        ["sh", "-c", "cat /project/input.txt > /project/out.txt"],
        check=False,
        capture_output=True,
        text=True,
    )
    return (
        result.returncode == 0
        and (ws.path / "out.txt").read_text(encoding="utf-8") == "ok"
    )


def host_tcp_listener() -> Generator[tuple[str, int]]:
    """Yield a passive localhost TCP listener on a random port."""
    host = "127.0.0.1"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((host, 0))
        listener.listen(16)
        yield (host, listener.getsockname()[1])
