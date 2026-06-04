"""Unit tests for ctf.secrets_gen."""

from ctf.secrets_gen import generate_secrets


def test_secrets_are_64_chars() -> None:
    """Each secret value is exactly 64 characters long."""
    a, b = generate_secrets()
    assert len(a.value) == 64
    assert len(b.value) == 64


def test_secrets_are_lowercase_hex() -> None:
    """Each secret value contains only lowercase hexadecimal characters."""
    a, b = generate_secrets()
    hex_chars = "0123456789abcdef"
    assert all(c in hex_chars for c in a.value)
    assert all(c in hex_chars for c in b.value)


def test_secrets_are_distinct() -> None:
    """Four secrets across two calls are all distinct values."""
    a1, b1 = generate_secrets()
    a2, b2 = generate_secrets()
    values = {a1.value, b1.value, a2.value, b2.value}
    assert len(values) == 4
