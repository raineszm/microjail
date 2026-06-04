"""Cryptographic secret generation for CTF escape tests."""

import secrets as _secrets

from ctf.models import Secret


def generate_secrets() -> tuple[Secret, Secret]:
    """Return (filesystem_secret, network_secret), each a 64-char hex string."""
    return (
        Secret(name="filesystem", value=_secrets.token_hex(32)),
        Secret(name="network", value=_secrets.token_hex(32)),
    )
