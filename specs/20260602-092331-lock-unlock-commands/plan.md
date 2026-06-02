# Implementation Plan: microjail lock, unlock, and run Commands

**Branch**: `main` | **Date**: 2026-06-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/20260602-092331-lock-unlock-commands/spec.md`

## Summary

Implement `microjail lock`, `microjail unlock`, and `microjail run -- <cmd>` — the three
commands that form the execution phase of the microjail lifecycle. `lock` severs network
egress on the LXD container and verifies four baseline gates (egress down, workspace mounted,
config readonly, inference socket reachable). `unlock` is the symmetric inverse: it restores
egress. `run` delegates to `lock`, spawns the workload inside the container, then unlocks
after the workload exits. Both `lock` and `run` roll back egress if a gate fails so the
container is never left in a partially-locked state.

## Technical Context

**Language/Version**: Python 3.14 (per `pyproject.toml`, `requires-python = ">=3.14"`)

**Primary Dependencies**:
- `typer` — CLI framework (already declared)
- `rich` — terminal output (already declared)
- `stdlib: subprocess, pathlib, socket, dataclasses` — LXD/Workshop subprocess calls,
  filesystem probes, UDS socket reachability check

Note: Network egress is controlled by manipulating the LXD container's NIC device
(`lxc config device set <container> <nic> ipv4.routes.external ""` or equivalent LXD ACL
approach). The exact mechanism must be confirmed during implementation via `lxc` docs;
the state module records the locked flag, not the mechanism.

**Storage**: `.microjail/state.json` (workspace directory). The `EnvironmentState`
dataclass gains a `locked: bool` field defaulting to `False`.

**Testing**: pytest + anyio (already in dev dependencies). LXD-dependent tests marked
`@pytest.mark.lxd`. Unit tests mock `subprocess` and filesystem; integration tests require
a live Workshop + LXD installation.

**Target Platform**: Linux (Ubuntu). LXD ACL / NIC device manipulation is Linux-only.

**Project Type**: CLI tool (extending existing `src/microjail/` layout)

**Performance Goals**: Lock overhead (egress cut + all gates) MUST complete in under
10 seconds on a local machine with a running LXD instance (SC-001), excluding workload
runtime.

**Constraints**:
- FR-007: If any gate fails after egress is severed, egress MUST be restored before exit.
- No network calls from microjail itself; all LXD interaction is via `lxc` subprocess.
- `lock` logic must not be duplicated in `run`; `run` calls `lock` internals directly.
- State file readonly enforcement: `lxd/network.py` adds a named `readonly=true` disk device targeting `.microjail/state.json` to the container during `lock_egress()`. `unlock_egress()` removes the device. The state-readonly gate in `gates/state_readonly.py` verifies the device is present via `lxc config device show`; it does NOT use `lxc exec -- test -w`, which would check filesystem permissions rather than the bind-mount device.

**Scale/Scope**: Single-user, single-environment CLI tool. One locked environment per
workspace.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Safety First | ✅ PASS | FR-007 mandates egress rollback on gate failure. Workload is never spawned if any gate fails (FR-008/FR-017). Idempotent lock/unlock prevents double-mutation. |
| II. Correctness Over Confidence | ✅ PASS | FR-003/FR-004: egress-down gate probes the actual network path, not the lxc call return code. FR-006: inference socket gate connects to the socket, not just stat-checks the file. |
| III. Human Readability & Auditability | ✅ PASS | Named gate modules; each gate returns a named result. Error messages name the failing gate and remediation. `locked` flag in state.json is human-readable. |
| IV. Idiomatic Python | ✅ PASS | `dataclasses` for gate results, `pathlib` for paths, `typer` for CLI, full type annotations required. |
| V. Fail Loudly, Fail Clearly | ✅ PASS | Every gate failure exits non-zero naming the gate. Missing state file is a named error. Empty workload exits before locking. |

No violations. No Complexity Tracking entry required.

## Project Structure

### Documentation (this feature)

```text
specs/20260602-092331-lock-unlock-commands/
├── plan.md              # This file
└── spec.md              # Feature specification
```

### Source Code (repository root)

```text
src/microjail/
├── cli.py                        # registers lock, unlock, run commands
├── commands/
│   ├── init.py                   # existing
│   ├── lock.py                   # microjail lock command
│   ├── unlock.py                 # microjail unlock command
│   └── run.py                    # microjail run command; delegates to lock internals
├── gates/
│   ├── __init__.py               # GateResult dataclass; run_all_gates()
│   ├── egress.py                 # gate: egress is actually down
│   ├── workspace.py              # gate: workspace bind-mount present
│   ├── config_readonly.py        # gate: opencode.jsonc is not writable (agent gate)
│   ├── state_readonly.py         # gate: readonly=true LXD device for state.json is present and active (unconditional)
│   └── inference_socket.py       # gate: UDS socket file exists and is reachable
├── lxd/
│   ├── __init__.py
│   └── network.py                # lxc subprocess wrappers: lock_egress(), unlock_egress()
├── state.py                      # EnvironmentState gains locked: bool field
└── workshop/
    └── client.py                 # existing; gains exec() wrapper for run command

tests/
├── unit/
│   ├── test_gates_egress.py
│   ├── test_gates_workspace.py
│   ├── test_gates_config_readonly.py
│   ├── test_gates_state_readonly.py
│   ├── test_gates_inference_socket.py
│   └── test_state_locked_field.py
└── integration/
    ├── test_lock_command.py       # @pytest.mark.lxd
    ├── test_unlock_command.py     # @pytest.mark.lxd
    └── test_run_command.py        # @pytest.mark.lxd
```

**Structure Decision**: New `gates/` package holds one module per gate, each a pure function
that takes the `EnvironmentState` and workspace path and returns a `GateResult`. New `lxd/`
package holds the egress-control subprocess calls, parallel to the existing `workshop/`
package. `commands/run.py` calls `lxd.network.lock_egress()` + `gates.run_all_gates()` —
the same functions `commands/lock.py` uses — so there is no duplication.
