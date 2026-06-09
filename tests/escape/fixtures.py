"""Reusable fixtures and preflight wiring for escape tests."""

import importlib
import shutil
from dataclasses import dataclass
from pathlib import Path  # noqa: TC003

import pytest

from tests.escape._helpers import (
    create_workspace,
    start_secret_http_server,
    write_secret_file,
)


@dataclass(frozen=True)
class EscapeInputs:
    workspace: Path
    host_secret_file: Path
    host_http_port: int
    signal_file: Path
    secret_value: str


def escape_preflight_check() -> None:
    if shutil.which("lxc") is None:
        pytest.skip("lxc not installed")
    if shutil.which("workshop") is None:
        pytest.skip("workshop not installed")
    importlib.import_module("microjail.adapters.workshop")
    pytest.importorskip("ctf")


@pytest.fixture(scope="session")
def escape_preflight() -> None:
    escape_preflight_check()


@pytest.fixture
def escape_workspace() -> Path:
    workspace = create_workspace()
    try:
        yield workspace.path
    finally:
        workspace.cleanup()


@pytest.fixture
def escape_inputs(escape_workspace: Path) -> EscapeInputs:
    secret = "ctf-secret"
    secret_file = write_secret_file(escape_workspace, "host-secret.txt", secret)
    signal_file = escape_workspace / "signal.txt"
    http_server = start_secret_http_server(secret)
    try:
        yield EscapeInputs(
            workspace=escape_workspace,
            host_secret_file=secret_file,
            host_http_port=http_server.port,
            signal_file=signal_file,
            secret_value=secret,
        )
    finally:
        http_server.close()
