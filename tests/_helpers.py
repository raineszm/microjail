"""Shared test helpers — importable by all test layers."""

import socket
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

    from microjail.adapters.workshop import Workshop


def has_network_egress(ws: Workshop) -> bool:
    result = ws.exec_(
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


def can_write_microjail_config(ws: Workshop) -> bool:
    result = ws.exec_(
        ["test", "-w", "/project/.microjail/config.yaml"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def can_append_microjail_config(ws: Workshop) -> bool:
    result = ws.exec_(
        ["sh", "-c", "echo probe >> /project/.microjail/config.yaml"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def can_roundtrip_project_file(ws: Workshop) -> bool:
    (ws.project / "input.txt").write_text("ok", encoding="utf-8")
    result = ws.exec_(
        ["sh", "-c", "cat /project/input.txt > /project/out.txt"],
        check=False,
        capture_output=True,
        text=True,
    )
    return (
        result.returncode == 0
        and (ws.project / "out.txt").read_text(encoding="utf-8") == "ok"
    )


def host_tcp_listener() -> Generator[tuple[str, int]]:
    """Yield a passive localhost TCP listener on a random port."""
    host = "127.0.0.1"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((host, 0))
        listener.listen(16)
        yield (host, listener.getsockname()[1])
