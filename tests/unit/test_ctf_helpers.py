"""Unit tests for ctf.report, ctf.secrets_gen, and ctf.http_server."""

import json
import re
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

import pytest

from ctf.http_server import HostHttpServer, start_http_server
from ctf.report import CtfReport, write_report
from ctf.secrets_gen import Secret, generate_secrets

if TYPE_CHECKING:
    from pathlib import Path

# ── report.py ──────────────────────────────────────────────────────────


class TestCtfReport:
    def test_creates_with_all_fields(self) -> None:
        report = CtfReport(
            outcome="pass",
            error_kind=None,
            elapsed=1.5,
            timeout=30.0,
            secret_match=True,
            breach_vector=None,
            run_id="abc-123",
        )
        assert report.outcome == "pass"
        assert report.error_kind is None
        assert report.elapsed == 1.5
        assert report.timeout == 30.0
        assert report.secret_match is True
        assert report.breach_vector is None
        assert report.run_id == "abc-123"

    def test_frozen(self) -> None:
        report = CtfReport(
            outcome="fail",
            error_kind="timeout",
            elapsed=0.0,
            timeout=10.0,
            secret_match=False,
            breach_vector="http",
            run_id="xyz",
        )
        with pytest.raises(AttributeError):
            report.outcome = "changed"  # type: ignore[misc]


class TestWriteReport:
    def test_writes_valid_json(self, tmp_path: Path) -> None:
        report_file = tmp_path / "sub" / "report.json"
        report = CtfReport(
            outcome="pass",
            error_kind=None,
            elapsed=2.0,
            timeout=60.0,
            secret_match=True,
            breach_vector=None,
            run_id="run-1",
        )
        write_report(report_file, report)

        assert report_file.exists()
        data = json.loads(report_file.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_json_contains_all_expected_fields(self, tmp_path: Path) -> None:
        report_file = tmp_path / "report.json"
        report = CtfReport(
            outcome="fail",
            error_kind="secret_mismatch",
            elapsed=0.5,
            timeout=15.0,
            secret_match=False,
            breach_vector="dns",
            run_id="run-2",
        )
        write_report(report_file, report)

        data = json.loads(report_file.read_text(encoding="utf-8"))
        expected_keys = {
            "outcome",
            "error_kind",
            "elapsed",
            "timeout",
            "secret_match",
            "breach_vector",
            "run_id",
        }
        assert set(data.keys()) == expected_keys
        assert data["outcome"] == "fail"
        assert data["error_kind"] == "secret_mismatch"
        assert data["elapsed"] == 0.5
        assert data["timeout"] == 15.0
        assert data["secret_match"] is False
        assert data["breach_vector"] == "dns"
        assert data["run_id"] == "run-2"

    def test_none_path_is_noop(self) -> None:
        report = CtfReport(
            outcome="pass",
            error_kind=None,
            elapsed=0.0,
            timeout=5.0,
            secret_match=True,
            breach_vector=None,
            run_id="noop",
        )
        # Must not raise
        write_report(None, report)

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        report_file = tmp_path / "a" / "b" / "c" / "report.json"
        report = CtfReport(
            outcome="pass",
            error_kind=None,
            elapsed=0.1,
            timeout=5.0,
            secret_match=True,
            breach_vector=None,
            run_id="nested",
        )
        write_report(report_file, report)
        assert report_file.exists()


# ── secrets_gen.py ─────────────────────────────────────────────────────


class TestGenerateSecrets:
    def test_returns_two_secrets(self) -> None:
        fs, net = generate_secrets()
        assert isinstance(fs, Secret)
        assert isinstance(net, Secret)

    def test_each_has_name_and_value(self) -> None:
        fs, net = generate_secrets()
        assert fs.name == "filesystem"
        assert net.name == "network"
        assert isinstance(fs.value, str)
        assert isinstance(net.value, str)

    def test_values_are_different(self) -> None:
        fs, net = generate_secrets()
        assert fs.value != net.value

    def test_values_are_hex_of_length_64(self) -> None:
        fs, net = generate_secrets()
        hex_pattern = re.compile(r"^[0-9a-f]{64}$")
        assert hex_pattern.match(fs.value), f"bad hex: {fs.value!r}"
        assert hex_pattern.match(net.value), f"bad hex: {net.value!r}"


# ── http_server.py ─────────────────────────────────────────────────────


class TestStartHttpServer:
    def test_returns_host_http_server(self) -> None:
        hs = start_http_server("test-secret")
        try:
            assert isinstance(hs, HostHttpServer)
            assert hasattr(hs, "server")
            assert hasattr(hs, "port")
            assert hasattr(hs, "thread")
            assert isinstance(hs.port, int)
            assert hs.port > 0
            assert hs.thread.is_alive()
        finally:
            hs.server.shutdown()

    def test_binds_to_localhost(self) -> None:
        hs = start_http_server("s")
        try:
            assert hs.server.server_address[0] == "127.0.0.1"
        finally:
            hs.server.shutdown()

    def test_get_secret_returns_secret(self) -> None:
        secret = "my-ctf-secret-value"
        hs = start_http_server(secret)
        try:
            url = f"http://127.0.0.1:{hs.port}/secret"
            with urllib.request.urlopen(url, timeout=5) as resp:
                body = resp.read().decode("utf-8")
            assert body == secret
        finally:
            hs.server.shutdown()

    def test_other_paths_return_404(self) -> None:
        hs = start_http_server("s")
        try:
            url = f"http://127.0.0.1:{hs.port}/other"
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(url, timeout=5)
            assert exc_info.value.code == 404
        finally:
            hs.server.shutdown()

    def test_shutdown_stops_server(self) -> None:
        hs = start_http_server("s")
        hs.server.shutdown()
        # Thread should finish shortly after shutdown
        hs.thread.join(timeout=5)
        assert not hs.thread.is_alive()
