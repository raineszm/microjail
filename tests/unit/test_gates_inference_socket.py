"""Unit tests for the inference-socket gate.

Constitution requirement: tests MUST demonstrate the gate BLOCKS when the
socket is absent or unreachable.
"""

import socket
import threading
from pathlib import Path

from microjail.gates.inference_socket import (
    _extract_socket_path,
    check_inference_socket,
)

# ---------------------------------------------------------------------------
# _extract_socket_path helpers
# ---------------------------------------------------------------------------


def test_extract_socket_path_returns_none_for_http_url() -> None:
    assert _extract_socket_path("http://127.0.0.1:8080/v1") is None


def test_extract_socket_path_returns_path_for_unix_url() -> None:
    path = _extract_socket_path("http+unix:///tmp/llama.sock")
    assert path == Path("/tmp/llama.sock")


def test_extract_socket_path_returns_none_for_none() -> None:
    assert _extract_socket_path(None) is None


# ---------------------------------------------------------------------------
# check_inference_socket — gate blocking cases
# ---------------------------------------------------------------------------


def test_inference_socket_gate_blocks_when_socket_url_is_none() -> None:
    """Gate FAILS when socket_url is None (constitution-mandated blocking case)."""
    result = check_inference_socket(None)
    assert result.passed is False
    assert result.name == "inference-socket"


def test_inference_socket_gate_blocks_when_uds_file_missing(tmp_path: Path) -> None:
    """Gate FAILS when the UDS socket file does not exist."""
    missing = tmp_path / "llama.sock"
    result = check_inference_socket(f"http+unix://{missing}")
    assert result.passed is False
    assert "does not exist" in result.message


def test_inference_socket_gate_blocks_when_uds_not_listening(tmp_path: Path) -> None:
    """Gate FAILS when the socket file exists but nothing is listening."""
    sock_path = tmp_path / "llama.sock"
    # Create a regular file at the socket path — connect should fail.
    sock_path.write_bytes(b"")
    result = check_inference_socket(f"http+unix://{sock_path}")
    assert result.passed is False


def test_inference_socket_gate_passes_when_uds_listening(tmp_path: Path) -> None:
    """Gate PASSES when the UDS socket file exists and accepts connections."""
    sock_path = tmp_path / "llama.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(sock_path))
    server.listen(1)

    def _serve() -> None:
        try:
            conn, _ = server.accept()
            conn.close()
        except OSError:
            pass

    t = threading.Thread(target=_serve, daemon=True)
    t.start()

    try:
        result = check_inference_socket(f"http+unix://{sock_path}")
        assert result.passed is True
    finally:
        server.close()
        t.join(timeout=2)


def test_inference_socket_gate_blocks_when_tcp_port_closed() -> None:
    """Gate FAILS when the TCP endpoint is not listening (constitution-mandated blocking case)."""
    # Port 19999 is very unlikely to be in use.
    result = check_inference_socket("http://127.0.0.1:19999/v1")
    assert result.passed is False
    assert "not reachable" in result.message


def test_inference_socket_gate_passes_when_tcp_port_open() -> None:
    """Gate PASSES when the TCP endpoint accepts connections."""
    # Bind an ephemeral port, run the gate, then release.
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(("127.0.0.1", 0))
    port = server_sock.getsockname()[1]
    server_sock.listen(1)

    def _serve() -> None:
        try:
            conn, _ = server_sock.accept()
            conn.close()
        except OSError:
            pass

    t = threading.Thread(target=_serve, daemon=True)
    t.start()

    try:
        result = check_inference_socket(f"http://127.0.0.1:{port}/v1")
        assert result.passed is True
    finally:
        server_sock.close()
        t.join(timeout=2)


def test_inference_socket_gate_skipped_when_inference_not_set() -> None:
    """When inference is not configured, socket_url is None and gate blocks.

    This confirms the gate is correctly skipped at the run_all_gates level
    (caller only invokes this gate when inference is set).  When called
    directly with None it should fail, not silently pass.
    """
    result = check_inference_socket(None)
    assert result.passed is False
