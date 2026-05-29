"""Subprocess wrappers for the Workshop CLI tool.

All public functions raise :exc:`RuntimeError` with an actionable message on
failure. Callers are responsible for catching and surfacing errors to the user.

No state is held in this module -- every function is a pure subprocess call.

Workshop stores environment definitions at ``<project_dir>/.workshop/<name>.yaml``
and manages its instances in a dedicated LXD project (``workshop.<uid>``).
Use ``workshop info`` for existence checks rather than ``lxc info``, which
targets the default LXD project and will not find workshop instances.
"""

import shutil
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def check_prerequisites() -> None:
    """Verify that ``workshop`` and ``lxc`` are available on the host.

    Raises :exc:`RuntimeError` naming the specific missing tool if either
    prerequisite is absent or non-functional.
    """
    if shutil.which("workshop") is None:
        raise RuntimeError(
            "'workshop' not found on PATH. "
            "Install Workshop: https://canonical.com/blog/introducing-workshop-sandboxed-development-environments"
        )
    result = subprocess.run(
        ["lxc", "version"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "LXD is not available. Ensure LXD is installed and running. "
            f"(lxc version exited {result.returncode}: {result.stderr.decode().strip()})"
        )


def launch(name: str, project_dir: Path) -> None:
    """Run ``workshop launch <name>`` in *project_dir*.

    Expects the definition file at ``<project_dir>/.workshop/<name>.yaml``
    to already be written by the caller.

    Raises :exc:`RuntimeError` with Workshop's stderr if the command fails.
    """
    result = subprocess.run(
        ["workshop", "launch", name, "--project", str(project_dir)],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Workshop environment creation failed: {result.stderr.decode().strip()}"
        )


def verify_exists(name: str, project_dir: Path) -> None:
    """Confirm the workshop environment *name* exists via ``workshop info``.

    This check is independent of the ``workshop launch`` return code --
    it probes the actual Workshop state, satisfying Principle II (correctness
    over confidence).

    Raises :exc:`RuntimeError` if the environment is not found.
    """
    result = subprocess.run(
        ["workshop", "info", name, "--project", str(project_dir)],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Environment '{name}' was not found after creation. "
            f"workshop info output: {result.stderr.decode().strip()}"
        )


def environment_exists(name: str, project_dir: Path) -> bool:
    """Return ``True`` if a workshop environment named *name* already exists.

    Used during pre-flight checks (FR-008) to detect duplicate environments
    before any files are written.
    """
    result = subprocess.run(
        ["workshop", "info", name, "--project", str(project_dir)],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def remove(name: str, project_dir: Path) -> None:
    """Run ``workshop remove <name>`` in *project_dir*.

    Used by integration test teardown. Suppresses errors -- callers that need
    hard failure should check the return value themselves.

    Raises :exc:`RuntimeError` if removal fails (non-zero exit).
    """
    result = subprocess.run(
        ["workshop", "remove", name, "--project", str(project_dir)],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Workshop environment removal failed: {result.stderr.decode().strip()}"
        )
