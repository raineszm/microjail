"""Unit tests for the inference-tunnel gate.

The gate checks TCP reachability of the inference endpoint.  All UDS code
has been removed; only HTTP URLs with host:port are supported.
"""

import socket

from microjail.gates.inference_tunnel import (
    _parse_tcp_host_port,
    check_inference_tunnel,
)

# ---------------------------------------------------------------------------
# _parse_tcp_host_port helpers
# ---------------------------------------------------------------------------


def test_parse_tcp_host_port_for_http_url() -> None:
    assert _parse_tcp_host_port("http://127.0.0.1:8080/v1") == ("127.0.0.1", 8080)


def test_parse_tcp_host_port_defaults_to_80() -> None:
    assert _parse_tcp_host_port("http://example.com/path") == ("example.com", 80)


# ---------------------------------------------------------------------------
# check_inference_tunnel — gate blocking cases
# ---------------------------------------------------------------------------


def test_inference_tunnel_gate_blocks_when_socket_url_is_none() -> None:
    """Gate FAILS when socket_url is None (constitution-mandated blocking case)."""
    result = check_inference_tunnel(None)
    assert result.passed is False
    assert result.name == "inference-tunnel"


def test_inference_tunnel_gate_blocks_when_tcp_port_closed() -> None:
    """Gate FAILS when the TCP endpoint is not listening."""
    result = check_inference_tunnel("http://127.0.0.1:1/v1")
    assert result.passed is False
    assert "not reachable" in result.message
    assert "127.0.0.1:1" in result.message


# ---------------------------------------------------------------------------
# check_inference_tunnel — gate passing cases
# ---------------------------------------------------------------------------


def test_inference_tunnel_gate_passes_when_tcp_port_open() -> None:
    """Gate PASSES when the TCP endpoint accepts connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        _, port = srv.getsockname()

        result = check_inference_tunnel(f"http://127.0.0.1:{port}/v1")
        assert result.passed is True
        assert f"127.0.0.1:{port}" in result.message


def test_inference_tunnel_gate_skipped_when_inference_not_set() -> None:
    """When inference is not configured, socket_url is None and gate blocks."""
    result = check_inference_tunnel(None)
    assert (
        "no socket url" in result.message.lower() or "not set" in result.message.lower()
    )
