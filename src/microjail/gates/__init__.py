"""Lock gate infrastructure for microjail.

A *gate* is a pre-flight check that must pass before a workload is spawned.
All gates are blocking: if any gate fails, the workload MUST NOT start and
egress MUST be restored before the process exits (constitution §I).

Usage::

    from microjail.gates import run_all_gates

    results = run_all_gates(state, workspace)
    failures = [r for r in results if not r.passed]
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from microjail.state import State


@dataclass(frozen=True)
class GateResult:
    """Outcome of a single lock gate evaluation."""

    name: str
    """Human-readable gate name, e.g. ``"egress-down"``."""

    passed: bool
    """``True`` if the gate condition was satisfied."""

    message: str
    """Description of the result — always set.

    On failure: explains what was wrong and how to resolve it.
    On success: brief confirmation of the verified condition.
    """


def resolve_project(gate_name: str) -> tuple[str | None, GateResult | None]:
    """Return the Workshop LXD project name, or a failed GateResult on error.

    Returns ``(project, None)`` on success or ``(None, GateResult(passed=False))``
    when the LXD project cannot be determined.

    Typical usage in gate functions::

        project, err_result = resolve_project("egress-down")
        if err_result is not None:
            return err_result
        assert project is not None
    """
    from microjail.wrappers.lxd import _workshop_project  # local import avoids cycle

    try:
        return _workshop_project(), None
    except RuntimeError as exc:
        return None, GateResult(
            name=gate_name,
            passed=False,
            message=(
                f"Cannot determine LXD project to run {gate_name} check: {exc}. "
                "Ensure Workshop and LXD are running."
            ),
        )

def run_all_gates(state: State, workspace: Path) -> list[GateResult]:
    """Evaluate all gates applicable to *state* and return every result.

    Gates evaluated unconditionally:
    - ``egress-down``: egress is actually unreachable from inside the container.
    - ``workspace-mounted``: workspace directory is bind-mounted inside the container.
    - ``state-readonly``: the readonly=true LXD device for state.json is present.

    Gates evaluated conditionally:
    - ``config-readonly``: ``opencode.jsonc`` is not writable (only when ``agent == "opencode"``).
    - ``inference-tunnel``: TCP endpoint is accepting connections (only when inference is set).

    The list is ordered: unconditional gates first, then conditional.
    The caller is responsible for inspecting ``passed`` on each result and
    handling failures — this function never raises.
    """
    from microjail.gates.egress import check_egress_down
    from microjail.gates.inference_tunnel import check_inference_tunnel
    from microjail.gates.state_readonly import check_state_readonly
    from microjail.gates.workspace import check_workspace_mounted

    results: list[GateResult] = []

    # Unconditional gates — always run regardless of intent flags.
    results.extend(
        (
            check_egress_down(state.name),
            check_workspace_mounted(state.name, workspace),
            check_state_readonly(state.name, workspace),
        )
    )

    # Conditional gates — run only when the relevant intent flag was set at init.
    if state.inference is not None:
        results.append(check_inference_tunnel(state.socket_url))

    return results
