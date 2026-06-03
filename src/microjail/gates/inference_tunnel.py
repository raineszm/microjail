"""Gate: verify that the inference TCP endpoint is reachable.

Applies only when the environment was initialised with ``--inference llama-cpp``.
Confirms the local model is available before the network disappears, so the
workload always has a model to talk to.
"""

import socket

from microjail.gates import GateResult


def check_inference_tunnel(socket_url: str | None) -> GateResult:
    """Return a :class:`~microjail.gates.GateResult` confirming the inference endpoint is reachable.

    If *socket_url* is an HTTP URL (e.g. ``http://127.0.0.1:8080/v1``), the
    gate checks that the port is open via a brief TCP connect attempt.

    If *socket_url* is ``None``, the gate returns a failed result (this
    function should not be called with ``None`` but handles it defensively).
    """
    if socket_url is None:
        return GateResult(
            name="inference-tunnel",
            passed=False,
            message="Inference is configured but no socket URL is set. "
            "Re-initialise the environment with --inference llama-cpp.",
        )

    return _check_tcp(socket_url)


def _parse_tcp_host_port(socket_url: str) -> tuple[str, int]:
    """Extract (host, port) from an HTTP URL string.

    Handles ``http://host:port/path`` and falls back to port 80 when no
    explicit port is present.
    """
    host_port = socket_url.split("://", 1)[1].split("/", 1)[0]
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
            name="inference-tunnel",
            passed=False,
            message=f"Cannot parse inference URL '{socket_url}': {exc}.",
        )

    try:
        with socket.create_connection((host, port), timeout=2.0):
            pass
    except OSError as exc:
        return GateResult(
            name="inference-tunnel",
            passed=False,
            message=(
                f"Inference endpoint '{host}:{port}' is not reachable: {exc}. "
                "Ensure llama.cpp is running and listening on the configured port."
            ),
        )

    return GateResult(
        name="inference-tunnel",
        passed=True,
        message=f"Inference endpoint '{host}:{port}' is accepting connections.",
    )
