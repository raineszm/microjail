"""Cryptographic secret generation for CTF runs."""

import secrets
from dataclasses import dataclass


@dataclass(frozen=True)
class Secret:
    name: str
    value: str


def generate_secrets() -> tuple[Secret, Secret]:
    """Return filesystem + network secrets for a single run."""
    return (
        Secret(name="filesystem", value=secrets.token_hex(32)),
        Secret(name="network", value=secrets.token_hex(32)),
    )
