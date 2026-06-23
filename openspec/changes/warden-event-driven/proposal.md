## Why

The Warden currently polls each gate and capability every second, including behavioral probes (most notably `NetworkDrop`'s `bash -c ": >/dev/tcp/1.1.1.1/443"` egress probe). Polling wastes CPU on stable workloads, the egress probe is bash-dependent (false-positive gate violations on minimal images like alpine or distroless) and tests only one endpoint, and runtime capability checks conflate authorization with liveness. Under the threat model "LXD is the only thing with the power to enforce," the only way a gate can be violated during execution is via LXD configuration change — which the LXD lifecycle event stream sees directly. Switching the Warden to LXD events eliminates the bash-dependency bug, removes redundant probes, drops idle CPU to zero, and aligns the protocol with a clean `check()` (config) / `verify()` (behavioral) split.

## What Changes

- **New `LxdEventWatcher` in `src/microjail/adapters/lxd_events.py`.** Owns a `lxc monitor --type=lifecycle --format=json --quiet --project=<lxd_project> --force-local` subprocess, client-side filters the newline-delimited JSON events by container name (matching `metadata.name` or, when absent, the instance name parsed from `metadata.source`) and `metadata.project`, and pushes matching events onto a `queue.Queue`. A reader thread consumes the subprocess stdout so the Warden stays single-threaded. The subprocess constructor is injected for testability (defaults to `subprocess.Popen`); the LXD CLI handles its own connection to the local daemon (no certs, no socket management from our side).
- **Re-validation at watcher start.** On the initial successful start of the `lxc monitor` subprocess, the watcher pushes a `"reconnect"` sentinel onto the queue. The Warden treats it identically to any other event: re-snapshot the instance and re-validate every gate. The sentinel closes the brief window between the lockdown apply and the first real `instance-updated` event. The sentinel is emitted exactly once per watcher instance; there are no reconnects, so it is never re-emitted.
- **Subprocess exit is an immediate gate violation.** If the `lxc monitor` subprocess exits for any reason (LXD daemon stop, SIGHUP, the `lxc` binary crashing, a terminal readline error, etc.), the watcher raises `LxdEnforcementLost` immediately. There is no restart, no backoff, and no escalation budget. The Warden escalates as `GatePolicyViolation` (`RUNTIME_GATE_POLICY_VIOLATION`, exit code 84). Under the threat model "LXD is the only thing that can enforce," a workload whose event feed has died is a workload we cannot supervise.
- **Warden main loop rewritten.** `process.wait(timeout=0.1)` + `queue.get_nowait()` on `TimeoutExpired`. Non-empty drain → re-snapshot, re-run every gate's `check()`, terminate on first failure. The capability loop is removed from the Warden entirely.
- **Protocol extension.** `Gate` and `Capability` both gain a new `verify()` method (behavioral probe). The existing `check()` method's semantic narrows to a config-state check.
  - `NetworkDrop.check()` becomes a config check (no devices of `type: nic` in `expanded_devices`); `NetworkDrop.verify()` returns `True` (no behavioral probe). **BREAKING**: the old `NetworkDrop.check()` was the bash egress probe; the new one is a config check.
  - `ReadonlyConfig.check()` is unchanged (was already a config check); `ReadonlyConfig.verify()` returns `True`.
  - `WorkshopEndpointCapability.check()` becomes config-only (tunnel connections present in the Workshop SDK); `WorkshopEndpointCapability.verify()` does the TCP reachability probe. **BREAKING**: the old `check()` mixed config and behavioral.
- **`fatal: bool` flag repurposed.** It is no longer a runtime knob. It is a launch-time knob: a `fatal` capability whose `verify()` fails at pre-launch blocks the launch; a non-fatal failure is reported as a warning.
- **New `MicroJail.pre_launch_verify() -> PreLaunchVerifyResult`.** Invoked by `lock`, `exec`, and `shell` after `ensure_lockdown` and before any workload starts. Loops over gates first (stops at first failure, raises `GateError`), then capabilities (collects non-fatal failures, raises `CapabilityError` on first fatal). Returns warnings for the caller to display. `CapabilityError` carries a `non_fatal_failures` field listing the non-fatal capability names collected before the fatal failure, so the CLI can surface the earlier warnings.
- **`lock` exit codes.** `lock` can now exit with `GATE_APPLICATION_FAILURE` (68) or `CAPABILITY_APPLICATION_FAILURE` (66) from the verify step, in addition to the existing `ensure()` failure modes.
- **No new dependency.** The `lxc` CLI is already a system-level dependency; the watcher uses it directly. No new pip package is added.

## Capabilities

### New Capabilities

- `lxd-event-watcher`: The LXD event subscription primitive used by the Warden. Owns the `lxc monitor` subprocess, the `"reconnect"` sentinel (emitted on initial start), the `LxdEnforcementLost` exception (raised immediately on subprocess exit), and the event queue. There is no reconnect or restart logic: subprocess exit is the escalation trigger. The escalation contract (subprocess exit → `LxdEnforcementLost` → `GatePolicyViolation` → `RUNTIME_GATE_POLICY_VIOLATION`) is owned by this capability.
- `pre-launch-verify`: The launch-time behavioral verification step invoked by `lock`, `exec`, and `shell`. Loops over gates (stop at first failure, raise `GateError`) then capabilities (collect non-fatal failures, raise `CapabilityError` on first fatal, return warnings). Result type `PreLaunchVerifyResult` carries the non-fatal capability failure names for caller display. `CapabilityError.non_fatal_failures` carries the names of non-fatal capabilities collected before the fatal one.

### Modified Capabilities

- `warden-monitoring`: The Warden is now event-driven. Gates are checked on every LXD lifecycle event (and on the initial `"reconnect"` sentinel), not on a polling interval. Capabilities are not monitored at runtime. The Warden's escalation path adds `LxdEnforcementLost` (the `lxc monitor` subprocess exited) as a `GatePolicyViolation` with the `RUNTIME_GATE_POLICY_VIOLATION` exit code. The runtime capability violation path is removed entirely (capabilities are launch-time only).
- `endpoint-capability`: The `check()` method's semantic narrows to "tunnel connections present in the Workshop SDK." A new `verify()` method does the TCP reachability probe. The end-to-end behavior (the capability works) is unchanged; the split is at the protocol level.
- `readonly-config`: A new `verify()` method is added that returns `True` (no behavioral probe). No semantic change to the gate.

## Impact

- **New file `src/microjail/adapters/lxd_events.py`** (~150 LOC). `LxdEventWatcher` class plus `LxdEnforcementLost` exception. The watcher spawns the `lxc monitor` subprocess (constructor injected, defaulting to `subprocess.Popen`), reads its stdout line-by-line in a reader thread, enqueues the `"reconnect"` sentinel on initial start, and raises `LxdEnforcementLost` immediately when the subprocess exits. There is no restart logic.
- **`src/microjail/warden.py`**: rewrite of `supervise()` and `check_policies()`. Remove the capability loop. Add `LxdEnforcementLost` exception. Loop on `process.wait(timeout=0.1)` + queue drain.
- **`src/microjail/microjail.py`**: add `PreLaunchVerifyResult` dataclass and `pre_launch_verify()` method.
- **`src/microjail/gates/base.py`**: add `verify()` to the `Gate` protocol.
- **`src/microjail/gates/network_drop.py`**: `check()` becomes config-only (no NICs in `expanded_devices`); add `verify() = True`.
- **`src/microjail/gates/readonly_config.py`**: add `verify() = True`.
- **`src/microjail/caps/base.py`**: add `verify()` to the `Capability` protocol.
- **`src/microjail/caps/endpoint.py`**: split `check()` (tunnel state) and `verify()` (TCP reachability).
- **`src/microjail/commands/lock.py`**: call `microjail.pre_launch_verify()` after `ensure_lockdown`. Print warnings via `warning()`. Map `GateError` → 68, `CapabilityError` → 66.
- **`src/microjail/commands/exec.py`, `shell.py`**: call `microjail.pre_launch_verify()` after `ensure_lockdown` and before `popen`. Same exit code mapping.
- **`src/microjail/commands/supervision.py`**: handle `LxdEnforcementLost` (escalate as `GatePolicyViolation`) in `supervise_workload`.
- **`src/microjail/commands/cap.py`**: no change. `is_locked` continues to call `gate.check()`; under the new model `check()` is config-only, which is exactly what the preflight asks.
- **`src/microjail/policy.py`**: no new codes. `lock` reuses `GATE_APPLICATION_FAILURE` (68) and `CAPABILITY_APPLICATION_FAILURE` (66) for verify-step failures.
- **`pyproject.toml`**: no changes. The watcher uses the system `lxc` CLI; no new pip package is required.
- **`README.md`**: update the "Warden polls policy every second" line in the Technical summary.
- **`CONTEXT.md`**: already updated (`Warden`, `Gate policy violation`, `Capability policy violation`).
- **`docs/adr/0006-warden-event-driven-via-lxd-lifecycle.md`**: needs revision — the decision to use `lxc monitor` (not a raw WebSocket) and the rationale (no cert handling, no socket management) should be reflected, and the "no reconnect, immediate escalation on subprocess exit" revision needs to be captured.
- **Tests** — extensive updates:
  - New `tests/unit/test_lxd_events.py` for the watcher (subprocess start, sentinel emission on initial start, immediate `LxdEnforcementLost` on subprocess exit, stop semantics, distinction between stop-induced and external subprocess exit).
  - Rewrite of `tests/unit/test_warden.py` for the event-driven loop: `process.wait(timeout=0.1)`, queue drain, gate check on each event, sentinel re-snapshot, `LxdEnforcementLost` escalation.
  - Updates to `tests/unit/test_network_drop.py`: new `check()` semantics (no NICs), add `verify() = True` test.
  - Updates to `tests/unit/test_readonly_config.py`: add `verify() = True` test.
  - Updates to `tests/unit/test_endpoint_capability.py`: split `check`/`verify`, add TCP probe test for `verify()`.
  - New `tests/unit/test_pre_launch_verify.py`: gate raise, fatal-capability raise, non-fatal warning collection, non-fatal failures ride along on `CapabilityError`, empty lockdown, locked-down case.
  - Updates to `tests/functional/commands/test_lock.py`, `test_exec.py`, `test_shell.py`: pre_launch_verify integration.
