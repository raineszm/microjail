"""Gate: verify that the inference UDS socket exists and accepts a connection.

Applies only when the environment was initialised with ``--inference llama-cpp``.
Confirms the local model is available before the network disappears, so the
workload always has a model to talk to.
"""

import socket
from pathlib import Path

from microjail.gates import GateResult

# A socket URL looks like "http+unix://<path>" or simply "http://127.0.0.1:<port>/v1"
# For UDS detection we check whether the socket_url looks like a Unix path.
_UDS_SCHEMES = ("http+unix://", "unix://")


def _extract_socket_path(socket_url: str | None) -> Path | None:
    """Extract a filesystem path from a socket URL, or return ``None`` if HTTP."""
    if socket_url is None:
        return None
    for scheme in _UDS_SCHEMES:
        if socket_url.startswith(scheme):
            path_part = socket_url[len(scheme) :]
            # Strip trailing path component if present (e.g. /v1)
            path_part = path_part.split("%2F")[0] if "%2F" in path_part else path_part
            return Path(path_part.rstrip("/"))
    # Not a UDS URL — no socket path to check.
    return None


def check_inference_socket(socket_url: str | None) -> GateResult:
    """Return a :class:`~microjail.gates.GateResult` confirming the inference socket is reachable.

    If *socket_url* is a Unix domain socket URL, the gate verifies the socket
    file exists on the filesystem and accepts a connection attempt.

    If *socket_url* is an HTTP URL (e.g. ``http://127.0.0.1:8080/v1``), the
    gate checks that the port is open via a brief TCP connect attempt.

    If *socket_url* is ``None``, the gate returns a failed result (this
    function should not be called with ``None`` but handles it defensively).
    """
    if socket_url is None:
        return GateResult(
            name="inference-socket",
            passed=False,
            message=(
                "Inference socket URL is not set in state. "
                "Re-run 'microjail init --inference llama-cpp' to configure it."
            ),
        )

    socket_path = _extract_socket_path(socket_url)
    if socket_path is not None:
        return _check_uds(socket_path)
    return _check_tcp(socket_url)


def _check_uds(socket_path: Path) -> GateResult:
    """Check that *socket_path* exists and accepts a Unix socket connection."""
    if not socket_path.exists():
        return GateResult(
            name="inference-socket",
            passed=False,
            message=(
                f"Inference socket '{socket_path}' does not exist. "
                "Start llama.cpp on the host before running the workload: "
                "it must create a socket file at the configured path."
            ),
        )

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(2.0)
            sock.connect(str(socket_path))
    except OSError as exc:
        return GateResult(
            name="inference-socket",
            passed=False,
            message=(
                f"Inference socket '{socket_path}' exists but is not accepting "
                f"connections: {exc}. "
                "Ensure llama.cpp is running and listening on the socket."
            ),
        )

    return GateResult(
        name="inference-socket",
        passed=True,
        message=f"Inference socket '{socket_path}' is reachable.",
    )


def _parse_tcp_host_port(socket_url: str) -> tuple[str, int]:
    """Extract (host, port) from an HTTP URL string.

    Raises :exc:`ValueError` if the URL cannot be parsed.
    """
    without_scheme = socket_url.split("://", 1)[1]
    host_port = without_scheme.split("/")[0]
    if ":" in host_port:
        host, port_str = host_port.rsplit(":", 1)
        return host, int(port_str)
    return host_port, 80


def _check_tcp(socket_url: str) -> GateResult:
    """Check that the TCP endpoint in *socket_url* is accepting connections."""
    try:
        host, port = _parse_tcp_host_port(socket_url)
    except (IndexError, ValueError) as exc:
        return GateResult(
            name="inference-socket",
            passed=False,
            message=f"Cannot parse inference URL '{socket_url}': {exc}.",
        )

    try:
        with socket.create_connection((host, port), timeout=2.0):
            pass
    except OSError as exc:
        return GateResult(
            name="inference-socket",
            passed=False,
            message=(
                f"Inference endpoint '{host}:{port}' is not reachable: {exc}. "
                "Ensure llama.cpp is running and listening on the configured port."
            ),
        )

    return GateResult(
        name="inference-socket",
        passed=True,
        message=f"Inference endpoint '{host}:{port}' is accepting connections.",
    )
