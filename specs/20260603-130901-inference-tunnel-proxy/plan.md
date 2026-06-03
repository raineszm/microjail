# Implementation Plan: Inference Tunnel Proxy

**Branch**: `20260603-130901-inference-tunnel-proxy` | **Date**: 2026-06-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/20260603-130901-inference-tunnel-proxy/spec.md`

## Summary

Pivot the inference passthrough from a Unix domain socket (UDS) bind-mount to Workshop's tunnel
interface. When `--inference llama-cpp` is specified, `microjail init` generates a `workshop.yaml`
that includes a `system` SDK with a tunnel slot named `llama-cpp` and a project SDK named
`llama-cpp` with a corresponding tunnel plug. The inference gate pivots from checking for a UDS
socket file to verifying that the host-side TCP endpoint is accepting connections. The `socket_url`
in `state.json` and `opencode.jsonc` remains an HTTP URL (`http://localhost:8080/v1`); what changes
is how that URL becomes reachable — via Workshop's tunnel, not via bind-mount.

## Technical Context

**Language/Version**: Python 3.14 (per `pyproject.toml`, `requires-python = ">=3.14"`)

**Primary Dependencies**:
- `typer` — CLI framework (existing)
- `ruamel.yaml` — YAML generation (existing, already used by `config/workshop.py`)
- `stdlib: subprocess, pathlib, socket, dataclasses` — LXD/Workshop subprocess calls,
  TCP reachability check, filesystem operations

**Storage**: `.microjail/state.json` (workspace directory). The `EnvironmentState` dataclass
already has `socket_url` and `inference` fields — no schema change required.

**Testing**: pytest + anyio (existing). LXD-dependent tests marked `@pytest.mark.lxd`. Unit tests
mock `subprocess` and `socket`; integration tests require a live Workshop + LXD installation.

**Target Platform**: Linux (Ubuntu). LXD container management is Linux-only.

**Project Type**: CLI tool (extending existing `src/microjail/` layout)

**Performance Goals**: Inference gate TCP check MUST complete within 5 seconds (SC-002). Workshop
`launch`/`refresh` latency is unchanged.

**Constraints**:
- `lock_egress` enumerates ALL NIC devices and clears routes on each; `unlock_egress` restores routes on ALL NICs and re-adds the container to `workshopbr0` if running.
- The tunnel survives lock/unlock because it is a non-NIC device.
- The tunnel slot/plug names are derived from the inference provider value (e.g., `llama-cpp`).
- The system SDK name is `system` (Workshop convention for host-level connectivity).
- `socket_url` in state.json remains an HTTP URL, not a UDS path.
- Backward compatibility: no `--inference` → identical `workshop.yaml` output (no system SDK,
  no tunnel entries) as before this feature.

**Scale/Scope**: Single-user, single-environment CLI tool. One environment per workspace.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
| I. Safety First | ✅ PASS | `lock_egress` is modified to clear routes on ALL NIC devices, making the lock more thorough. The tunnel survives because it's a separate non-NIC device not in the enumeration. FR-007/FR-008: inference gate still blocks the workload when inference is unreachable. |
| II. Correctness Over Confidence | ✅ PASS | FR-007: gate checks TCP reachability (actual connection), not just DNS resolution. FR-010: all UDS code paths are removed, eliminating the stale UDS check path. |
| III. Human Readability & Auditability | ✅ PASS | Slot/plug names match the inference provider (e.g., `llama-cpp`), making the YAML self-documenting. Gate failure messages include host and port (FR-009). |
| IV. Idiomatic Python | ✅ PASS | Uses existing `dataclasses`, `pathlib`, `socket` patterns. `ruamel.yaml` is already a dependency. No new external dependencies. |
| V. Fail Loudly, Fail Clearly | ✅ PASS | FR-009: gate reports host and port on failure. Workshop launch failure propagates. All error paths name the failing component. |

No violations. No Complexity Tracking entry required.

## Project Structure

### Documentation (this feature)

```text
specs/20260603-130901-inference-tunnel-proxy/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code (repository root)

```text
src/microjail/
├── cli.py                              # existing; no changes needed
├── commands/
│   └── init.py                         # MODIFY: pass inference to generate_workshop_yaml; socket_url stays HTTP
├── config/
│   ├── models.py                       # existing; no changes (InferenceBackend is already "llama-cpp")
│   ├── workshop.py                     # MODIFY: generate system SDK + tunnel slot/plug when inference is set
│   └── opencode.py                      # existing; no changes (socket_url is already HTTP)
├── gates/
│   ├── __init__.py                     # existing; no changes
│   ├── inference_socket.py             # MODIFY: rename to inference_tunnel.py; remove UDS paths; change to TCP-only check
│   ├── egress.py                       # existing; no changes
│   ├── workspace.py                    # existing; no changes
│   ├── config_readonly.py              # existing; no changes
├── lxd/
│   ├── __init__.py                     # existing; no changes
│   └── network.py                      # MODIFY: enumerate ALL NIC devices in lock_egress/unlock_egress; unlock_egress re-adds to workshopbr0 if running
├── state.py                            # existing; no changes (socket_url already an HTTP URL)
└── workshop/
    └── client.py                       # existing; no changes

tests/
├── unit/
│   ├── test_gates_inference_socket.py  # MODIFY: rename + rewrite for TCP-only check
│   └── ... (existing tests unchanged)
└── integration/
    └── test_init_command.py            # MODIFY: add assertions for tunnel YAML structure
```

**Structure Decision**: This is a modification of existing modules. No new packages are created.
The `inference_socket.py` gate module is renamed to `inference_tunnel.py` to reflect the pivot
from UDS to TCP. The `config/workshop.py` module gains tunnel slot/plug generation logic.
