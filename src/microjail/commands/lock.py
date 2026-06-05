"""Implementation of ``microjail lock`` and the shared ``perform_lock`` helper.

``perform_lock`` is the single source of truth for the lock sequence.  Both
``microjail lock`` (this module) and ``microjail run`` (commands/run.py) call
it — no duplication of locking logic.

Lock sequence:
0. Ensure container exists, launching on first use if ``state.launched`` is
   ``False`` (via ``ensure_container_ready``).
1. Cut network egress via ``lxd.lock_egress()``.
2. Run all applicable gates via ``gates.run_all_gates()``.
3. If any gate fails: restore egress, raise ``RuntimeError`` naming the gate.
4. On success: update ``state.locked = True`` and persist state.
"""

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from microjail.commands import load_state_or_exit
from microjail.config.workshop import INFERENCE_PLUG_REF, INFERENCE_SLOT_REF
from microjail.gates import run_all_gates
from microjail.output import err
from microjail.wrappers import workshop
from microjail.wrappers.lxd import lock_egress, unlock_egress

if TYPE_CHECKING:
    from microjail.state import State


def ensure_container_ready(state: State, workspace: Path) -> None:
    """Launch the Workshop container on first use and connect the inference tunnel.

    Only called when ``state.launched`` is ``False``.  After a successful
    return the container is running, ``state.launched`` is persisted as
    ``True``, and (when inference is configured) the tunnel is wired.

    FR-008: ``state.launched`` is persisted before any LXD mutation so a
    crash after provisioning but before locking leaves the state truthful
    (the container exists; the next ``lock`` retries only the connect step).

    Raises :exc:`RuntimeError` if launch, verification, or tunnel connection
    fails.  On failure, ``state.launched`` is left unchanged (``False``) so
    the next invocation retries the full launch sequence.
    """
    workshop.ensure_launched(state.name, workspace)
    # Persist launched=True before any LXD mutation (FR-008).
    state.launched = True
    state.dump(workspace)
    if state.inference is not None:
        workshop.connect(state.name, INFERENCE_PLUG_REF, INFERENCE_SLOT_REF, workspace)


def perform_lock(state: State, workspace: Path) -> None:
    """Sever egress and verify all gates for *state*.

    On success the state file is updated with ``locked = True``.

    Step 0 (new): if ``state.launched`` is ``False``, the container is
    provisioned via :func:`ensure_container_ready` before any LXD call is
    made.  On failure: ``launched`` stays ``False``, ``locked`` stays
    ``False``, and a :exc:`RuntimeError` is raised.

    Raises :exc:`RuntimeError` if egress cannot be cut or any gate fails.
    When a gate fails after egress has been severed, egress is restored before
    raising so the container is never left in a partially-locked state
    (constitution §I).
    """
    # Step 0: ensure container exists, launching on first use.
    if not state.launched:
        ensure_container_ready(state, workspace)

    # Step 1: Cut egress.
    lock_egress(state.name, workspace)

    # Step 2: Evaluate all gates.
    results = run_all_gates(state, workspace)
    failures = [r for r in results if not r.passed]

    if failures:
        # Step 3: Gate(s) failed — restore egress before raising.
        with contextlib.suppress(RuntimeError):
            unlock_egress(state.name)
        gate_names = ", ".join(r.name for r in failures)
        first_msg = failures[0].message
        msg = f"Lock gate failed [{gate_names}]: {first_msg}"
        raise RuntimeError(msg)

    # Step 4: All gates passed — persist locked state.
    state.locked = True
    state.dump(workspace)


def lock() -> None:
    r"""Sever network egress and verify all lock gates.

    \b
    Reads .microjail/state.json from the current directory to identify
    the environment.  If the Workshop container has not been created yet
    (``launched=False``), provisions it on demand before locking.  Exits
    zero when all gates pass; exits non-zero and names the failing gate when
    any gate fails.

    If the environment is already locked, exits zero with an informational
    message (idempotent).

    \b
    Examples:
      microjail lock
    """
    workspace = Path.cwd()
    state = load_state_or_exit(workspace)

    if state.locked:
        typer.echo(f"Environment '{state.name}' is already locked.")
        return

    try:
        perform_lock(state, workspace)
    except RuntimeError as exc:
        err(str(exc))

    typer.echo(f"Environment '{state.name}' locked. All gates passed.")
