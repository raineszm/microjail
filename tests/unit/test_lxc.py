"""Tests for the ``lxc`` CLI adapter helpers."""

import ssl
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import Mock

from microjail.adapters.lxc import lxd_local_connect

if TYPE_CHECKING:
    import pytest


def test_lxd_local_connect_loads_certs_and_passes_ssl_context(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The helper loads the lxc CLI's client cert and passes an SSL context to connect."""
    cert_dir = tmp_path / "lxd-certs"
    cert_dir.mkdir()
    (cert_dir / "client.crt").write_bytes(b"cert")
    (cert_dir / "client.key").write_bytes(b"key")
    (cert_dir / "client.ca").write_bytes(b"ca")

    captured: dict[str, object] = {}
    fake_ctx = Mock()

    def fake_create_default_context(*, cafile: object = None) -> Mock:
        captured["cafile"] = cafile
        return fake_ctx

    def fake_load_cert_chain(
        *, certfile: object = None, keyfile: object = None
    ) -> None:
        captured["certfile"] = certfile
        captured["keyfile"] = keyfile

    fake_ctx.load_cert_chain = fake_load_cert_chain

    monkeypatch.setattr(ssl, "create_default_context", fake_create_default_context)

    def fake_connect(uri: str, **kwargs: object) -> Mock:
        captured["uri"] = uri
        captured["ssl"] = kwargs.get("ssl")
        return Mock()

    import websockets.sync.client

    monkeypatch.setattr(websockets.sync.client, "connect", fake_connect)

    result = lxd_local_connect(
        "wss://127.0.0.1:8443/1.0/events?type=lifecycle",
        cert_dir=cert_dir,
    )

    assert captured["cafile"] == cert_dir / "client.ca"
    assert captured["certfile"] == cert_dir / "client.crt"
    assert captured["keyfile"] == cert_dir / "client.key"
    assert captured["ssl"] is fake_ctx
    assert captured["uri"] == "wss://127.0.0.1:8443/1.0/events?type=lifecycle"
    assert result is not None


def test_lxd_local_connect_uses_default_cert_dir_when_none_given(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When *cert_dir* is omitted, the helper resolves to ``~/.config/lxc``."""
    cert_dir = tmp_path / ".config" / "lxc"
    cert_dir.mkdir(parents=True)
    (cert_dir / "client.crt").write_bytes(b"cert")
    (cert_dir / "client.key").write_bytes(b"key")
    (cert_dir / "client.ca").write_bytes(b"ca")

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    captured: dict[str, object] = {}
    fake_ctx = Mock()
    fake_ctx.load_cert_chain = Mock(
        side_effect=lambda certfile, keyfile: captured.update(
            certfile=certfile, keyfile=keyfile
        )
    )

    def fake_create_default_context(*, cafile: object = None) -> Mock:
        captured["cafile"] = str(cafile)
        return fake_ctx

    monkeypatch.setattr(ssl, "create_default_context", fake_create_default_context)

    import websockets.sync.client

    def fake_connect(uri: str, **kwargs: object) -> Mock:
        captured["uri"] = uri
        return Mock()

    monkeypatch.setattr(websockets.sync.client, "connect", fake_connect)

    lxd_local_connect("wss://127.0.0.1:8443/1.0/events?type=lifecycle")

    assert str(captured["cafile"]).endswith("/.config/lxc/client.ca")
    assert str(captured["certfile"]).endswith("/.config/lxc/client.crt")
    assert str(captured["keyfile"]).endswith("/.config/lxc/client.key")
    assert captured["uri"] == "wss://127.0.0.1:8443/1.0/events?type=lifecycle"
