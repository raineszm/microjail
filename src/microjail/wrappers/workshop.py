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
    if shutil.which("lxc") is None:
        raise RuntimeError(
            "'lxc' not found on PATH. Install LXD: https://canonical.com/lxd"
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

    Raises :exc:`RuntimeError` with the exit code if the command fails.
    """
    result = subprocess.run(
        ["workshop", "launch", name, "--project", str(project_dir)],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Workshop environment creation failed (exit {result.returncode}; see output above)."
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


def ensure_launched(name: str, project_dir: Path) -> None:
    """Provision the Workshop environment *name* and verify it exists.

    Calls :func:`check_prerequisites`, :func:`launch`, and then
    :func:`verify_exists` (constitution §II: always verify the postcondition
    independently after ``workshop launch`` reports success).

    Raises :exc:`RuntimeError` with an actionable message on any failure.
    The caller is responsible for persisting ``State.launched = True`` after
    this returns — state mutation belongs in the command layer, not here.
    """
    check_prerequisites()
    launch(name, project_dir)
    verify_exists(name, project_dir)


def refresh(name: str, project_dir: Path) -> None:
    """Run ``workshop refresh <name>`` in *project_dir*.

    Applies the updated definition (base image, SDKs, connections) to an
    environment that already exists.  Used by ``microjail init --force`` when
    the named environment is present.

    Raises :exc:`RuntimeError` with the exit code if the command fails.
    """
    result = subprocess.run(
        ["workshop", "refresh", name, "--project", str(project_dir)],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Workshop environment refresh failed (exit {result.returncode}; see output above)."
        )


def connect(
    name: str,
    plug_ref: str,
    slot_ref: str,
    project_dir: Path,
) -> None:
    """Run ``workshop connect <name>/<plug_ref> <name>/<slot_ref>``.

    *plug_ref* and *slot_ref* are ``sdk:interface`` strings that match
    Workshop's own connect syntax, e.g. ``"local-inference:llama"``.

    Explicitly wires a plug to a slot when auto-connection is not reliable.
    Raises :exc:`RuntimeError` with the exit code if the command fails.
    """
    result = subprocess.run(
        [
            "workshop",
            "--project",
            str(project_dir),
            "connect",
            f"{name}/{plug_ref}",
            f"{name}/{slot_ref}",
        ],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Workshop connect failed (exit {result.returncode}; see output above)."
        )


def remove(name: str, project_dir: Path) -> None:
    """Run ``workshop remove <name>`` in *project_dir*.

    Used by integration test teardown.

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


def exec_in_env(
    name: str,
    cmd: list[str],
    project_dir: Path,
) -> subprocess.CompletedProcess[bytes]:
    """Run *cmd* inside the Workshop environment *name*.

    Uses ``workshop exec <name> -- <cmd>`` so the command executes in the
    LXD container associated with the named environment.

    Returns the :class:`subprocess.CompletedProcess` result so callers can
    inspect ``returncode``, ``stdout``, and ``stderr`` themselves.

    Does NOT raise on non-zero exit — the caller (``microjail run``) is
    responsible for propagating the workload's exit code to the user.

    Raises :exc:`RuntimeError` only if the ``workshop exec`` process itself
    cannot be started (e.g. Workshop is not installed).
    """
    try:
        return subprocess.run(
            ["workshop", "exec", name, "--project", str(project_dir), "--", *cmd],
            check=False,
        )
    except FileNotFoundError as exc:
        msg = (
            "'workshop' not found on PATH. "
            "Install Workshop: https://canonical.com/blog/introducing-workshop-sandboxed-development-environments"
        )
        raise RuntimeError(msg) from exc
