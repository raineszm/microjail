"""Unit tests for ctf.http_server."""

import urllib.error
import urllib.request

import pytest

from ctf.http_server import start_http_server


def test_secret_endpoint_returns_secret():
    """GET /secret returns 200 and the secret body."""
    srv = start_http_server(secret="test-secret-abc")
    try:
        port = srv.port
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/secret") as resp:
            body = resp.read().decode()
        assert body == "test-secret-abc"
    finally:
        srv.server.shutdown()


def test_unknown_path_returns_404():
    """GET on an unknown path returns 404."""
    srv = start_http_server(secret="irrelevant")
    try:
        port = srv.port
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/other")
        assert exc_info.value.code == 404
    finally:
        srv.server.shutdown()


def test_port_zero_gets_assigned():
    """Passing port=0 results in a non-zero OS-assigned port."""
    srv = start_http_server(secret="x", port=0)
    try:
        assert srv.port > 0
    finally:
        srv.server.shutdown()


def test_two_servers_bind_different_ports():
    """Two servers started with port=0 receive distinct ports."""
    srv1 = start_http_server(secret="a", port=0)
    srv2 = start_http_server(secret="b", port=0)
    try:
        assert srv1.port != srv2.port
    finally:
        srv1.server.shutdown()
        srv2.server.shutdown()
