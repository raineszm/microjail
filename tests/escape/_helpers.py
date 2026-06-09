"""Escape-suite-local helpers for workspace and signal handling."""

import contextlib
import http.server
import socketserver
import tempfile
import threading
import time
from collections.abc import Callable  # noqa: TC003
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class Teardown(Protocol):
    def __call__(self) -> None: ...


@dataclass(frozen=True)
class EscapeWorkspace:
    path: Path
    teardown: Teardown

    def cleanup(self) -> None:
        self.teardown()


@dataclass(frozen=True)
class HttpSecretServer:
    port: int
    secret_path: Path
    server: socketserver.TCPServer
    thread: threading.Thread

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


@dataclass(frozen=True)
class SignalPollResult:
    observed: str | None
    iterations: int
    elapsed: float


class _SecretHandler(http.server.BaseHTTPRequestHandler):
    secret_text = ""

    def do_GET(self) -> None:
        payload = self.secret_text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _fmt: str, *_args: object) -> None:
        return


def create_workspace(prefix: str = "ctf-escape-") -> EscapeWorkspace:
    tempdir = tempfile.TemporaryDirectory(prefix=prefix)
    return EscapeWorkspace(path=Path(tempdir.name), teardown=tempdir.cleanup)


def write_secret_file(workspace: Path, name: str, secret: str) -> Path:
    path = workspace / name
    path.write_text(secret, encoding="utf-8")
    return path


def start_secret_http_server(secret: str) -> HttpSecretServer:
    handler = type("SecretHandler", (_SecretHandler,), {"secret_text": secret})
    server = socketserver.TCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return HttpSecretServer(
        port=server.server_address[1],
        secret_path=Path("/secret"),
        server=server,
        thread=thread,
    )


def poll_signal_file(
    path: Path,
    *,
    accepted_values: set[str],
    interval: float,
    timeout: float,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> SignalPollResult:
    started = clock()
    observed: str | None = None
    iterations = 0
    while True:
        iterations += 1
        if path.exists():
            observed = path.read_text(encoding="utf-8").strip()
            if observed in accepted_values:
                return SignalPollResult(
                    observed=observed,
                    iterations=iterations,
                    elapsed=clock() - started,
                )

        elapsed = clock() - started
        if elapsed >= timeout:
            return SignalPollResult(
                observed=observed, iterations=iterations, elapsed=elapsed
            )

        sleeper(interval)


@contextlib.contextmanager
def managed_workspace(prefix: str = "ctf-escape-"):
    workspace = create_workspace(prefix)
    try:
        yield workspace
    finally:
        workspace.cleanup()
