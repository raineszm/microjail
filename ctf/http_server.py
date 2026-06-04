"""Minimal host-side HTTP server serving a single secret for CTF escape tests."""

import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer


@dataclass
class HostHttpServer:
    """Handle to a running HTTP server daemon thread."""

    server: HTTPServer
    port: int
    thread: threading.Thread


def _make_handler(secret: str) -> type[BaseHTTPRequestHandler]:
    """Return a handler class whose GET /secret endpoint returns *secret*."""

    class _SecretHandler(BaseHTTPRequestHandler):
        _secret = secret

        def do_GET(self) -> None:
            if self.path == "/secret":
                body = self._secret.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            """Silence per-request access logs."""

    return _SecretHandler


def start_http_server(secret: str, port: int = 0) -> HostHttpServer:
    """Bind to 127.0.0.1:port (0 = OS-assigned), serve *secret* at GET /secret."""
    handler = _make_handler(secret)
    server = HTTPServer(("127.0.0.1", port), handler)
    actual_port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return HostHttpServer(server=server, port=actual_port, thread=thread)
