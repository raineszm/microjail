"""Unit tests for the CLI output helpers in ``microjail.commands._output``."""

from typing import TYPE_CHECKING

from microjail.commands import _output

if TYPE_CHECKING:
    import pytest


def test_helpers_emit_plain_text_under_non_tty(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When writing to a non-TTY stream, the helpers must emit plain text
    with no ANSI escape sequences, and the message text must include the
    substrings that existing functional tests assert on.
    """
    _output.success("hello")
    _output.info("status update")
    _output.error("bad thing")
    _output.warning("careful")

    captured = capsys.readouterr()
    out, err = captured.out, captured.err

    # No ANSI escape sequences in either captured stream.
    assert "\x1b[" not in out
    assert "\x1b[" not in err

    # Stdout helpers: success carries the checkmark; info is verbatim.
    assert "✓ hello" in out
    assert "status update" in out

    # Stderr helpers: error and warning carry the literal prefixes that
    # existing functional tests assert on.
    assert "✗ error: bad thing" in err
    assert "⚠ warning: careful" in err
