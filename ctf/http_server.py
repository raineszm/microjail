"""Host-side HTTP secret server for CTF runs."""

import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer


@dataclass(frozen=True)
class HostHttpServer:
    server: HTTPServer
    port: int
    thread: threading.Thread


def _handler(secret: str) -> type[BaseHTTPRequestHandler]:
    class SecretHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/secret":
                self.send_response(404)
                self.end_headers()
                return
            payload = secret.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _fmt: str, *_args: object) -> None:
            return

    return SecretHandler


def start_http_server(secret: str, port: int = 0) -> HostHttpServer:
    server = HTTPServer(("127.0.0.1", port), _handler(secret))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return HostHttpServer(server=server, port=server.server_address[1], thread=thread)
