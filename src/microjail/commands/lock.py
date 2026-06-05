"""Implementation of ``microjail lock`` and the shared ``perform_lock`` helper.

``perform_lock`` is the single source of truth for the lock sequence.  Both
``microjail lock`` (this module) and ``microjail run`` (commands/run.py) call
it — no duplication of locking logic.

Lock sequence (FR-001 through FR-010):
1. Cut network egress via ``lxd.network.lock_egress()``.
2. Run all applicable gates via ``gates.run_all_gates()``.
3. If any gate fails: restore egress, raise ``RuntimeError`` naming the gate.
4. On success: update ``state.locked = True`` and persist state.
"""

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from microjail.commands import load_state_or_exit
from microjail.gates import run_all_gates
from microjail.output import err
from microjail.wrappers.lxd import lock_egress, unlock_egress

if TYPE_CHECKING:
    from microjail.state import State


def perform_lock(state: State, workspace: Path) -> None:
    """Sever egress and verify all gates for *state*.

    On success the state file is updated with ``locked = True``.

    Raises :exc:`RuntimeError` if egress cannot be cut or any gate fails.
    When a gate fails after egress has been severed, egress is restored before
    raising so the container is never left in a partially-locked state
    (FR-007, constitution §I).
    """
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
    the environment.  Exits zero when all gates pass; exits non-zero and
    names the failing gate when any gate fails.

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
