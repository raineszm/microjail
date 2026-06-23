"""Subprocess execution protocol and local default.

The :class:`CommandExecutor` protocol lets callers inject a substitute for
``subprocess.run`` and ``subprocess.Popen`` — typically for tests, but also
for any other reason a caller might want to intercept subprocess execution
(remote execution, dry-run, etc.). :class:`LocalExecutor` is the default
implementation that delegates straight to the stdlib.
"""

import subprocess
from typing import Any, Protocol


class CommandExecutor(Protocol):
    """The interface for spawning and running subprocesses.

    Implementations are responsible for translating the ``command`` list and
    ``kwargs`` into whatever subprocess mechanism they wrap. ``LocalExecutor``
    passes them straight through to :mod:`subprocess`.
    """

    def run(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess: ...

    def popen(self, command: list[str], **kwargs: Any) -> subprocess.Popen: ...


class LocalExecutor:
    """Default :class:`CommandExecutor` that delegates to :mod:`subprocess`."""

    def run(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        return subprocess.run(command, **kwargs)

    def popen(self, command: list[str], **kwargs: Any) -> subprocess.Popen:
        return subprocess.Popen(command, **kwargs)
