# ADR: Lock, unlock, run, and safety gates

Date: 2026-06-02
Status: Accepted

## Context

After `microjail init`, workloads needed to run inside the container only after containment was actively enforced and verified.

## Decision

- Add `microjail lock`, `microjail unlock`, and `microjail run -- <cmd>`.
- Store lock state as `EnvironmentState.locked: bool` in `.microjail/state.json`.
- Put egress mutation in `microjail.lxd.network` and gate checks in `microjail.gates`.
- Model each gate as a named `GateResult`; `run_all_gates()` owns gate ordering and conditional gates.
- `run` reuses the same lock helper as `lock`; it does not duplicate containment logic.
- If any gate fails after egress is severed, rollback egress before returning an error.
- Enforce state-file read-only status with a named LXD `readonly=true` disk device and verify the LXD device, not POSIX write bits.

## Consequences

- Workloads never start unless containment gates pass.
- Lock/unlock are idempotent at the command layer.
- Gate failures are auditable by name and message.
- LXD/Workshop subprocess interaction remains isolated from CLI orchestration.
