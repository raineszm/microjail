# 0007 Gate and Capability protocols split config-state check from behavioral verify

The `Gate` and `Capability` protocols previously conflated config-state inspection with behavioral reachability probing inside a single `check(microjail) -> bool` method. `check()` is now a config-only check (LXD device state, `workshop connections` membership, etc.) and a new `verify(microjail) -> VerificationResult` method on the same protocols performs behavioral probing and returns one of three values: `VERIFIED`, `FAILED`, or `UNSUPPORTED`. Verification runs once at launch time via `MicroJail.pre_launch_verify()`; the runtime polling loop in `Warden` continues to call `check()` and is unaffected by this change. The `lxc`-based bash egress probe that used to live in `NetworkDrop.check()` is removed; `NetworkDrop` and `ReadonlyConfig` return `UNSUPPORTED` from `verify()` because their enforcement is purely config-state and has no meaningful behavioral probe.

## Status

Accepted. Note: a separate, larger refactor on `refactor/event-warden-retry` (its own future ADR, "Warden is event-driven via LXD lifecycle events") replaces the runtime polling loop with event-driven LXD lifecycle monitoring. The protocol split introduced here is a prerequisite for that work; this ADR does not change the runtime polling loop.

## Considered Options

- **Single `check()` returning `bool`** (status quo). Simple signature, but every implementer must do both config and behavioral probing; `pre_launch_verify` cannot iterate "verify all" without re-running config checks; the bash egress probe sits in the runtime polling loop and false-positives on minimal container images.
- **Two methods, both returning `bool`**. Same as status quo in practice, just renamed. The three-valued result is needed to distinguish a gate that explicitly has no behavioral probe (like `ReadonlyConfig`) from a gate that probed and passed. Returning `True` for both would be indistinguishable to the CLI, and the original PR's "return `True` from `verify()` for unsupported gates" was rejected on exactly this ground — see the `Why` section of the proposal and `design.md` Decision 2.
- **Three-valued `check()` returning a status object**. Moves the split into the existing method instead of adding `verify()`. Lower surface area, but `check()` is called in tight runtime loops (the Warden, every second) where producing a status object per call is wasteful; `check()` only needs `bool`. Separating the methods also lets `check()` stay synchronous and side-effect-free, while `verify()` is allowed to take seconds and may raise.
- **Generic `Verification` protocol with no enum**. Allows arbitrary result shapes, but loses the type-level guarantee that `pre_launch_verify` only sees `VERIFIED`/`FAILED`/`UNSUPPORTED`. The enum is small, the alternatives would be larger.

## Decision

**Three-valued `VerificationResult` enum + `verify()` method on `Gate` and `Capability`.**

```python
class VerificationResult(StrEnum):
    VERIFIED = "verified"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"
```

**`check(microjail) -> bool` is config-only.** Implementations may consult LXD device state (`NetworkDrop` reads `InstanceInfo.devices` for entries of `type: nic` — `InstanceInfo.devices` is populated from the LXD `expanded_devices` key), Workshop tunnel state (`WorkshopEndpointCapability` checks `workshop connections` output for the named tunnel), or other local CLI queries. `check()` MUST NOT perform a TCP probe, an HTTP request, or any other behavioral check; it MUST return `False` (not raise) on any LXD query failure or container-unavailable case. Exceptions caught by `NetworkDrop.check()` are narrowed to `(WorkshopNotLaunchedError, subprocess.CalledProcessError, OSError)`; the previous bare `except Exception` was masking programmer errors and led to regressions in `test_cap.py` where `MicroJail.container_name()` raises `WorkshopNotLaunchedError`.

**`verify(microjail) -> VerificationResult` is behavioral, optional in spirit but required by the protocol.** Implementations with a meaningful behavioral probe return `VERIFIED` or `FAILED`. Implementations whose enforcement is purely config-state return `UNSUPPORTED` unconditionally (e.g. `ReadonlyConfig`, `NetworkDrop`). This distinguishes "the gate has no behavioral probe" from "the gate probed and passed", which the CLI surfaces as `Note: Verification not supported for {name}` to stdout via the `info()` helper.

**`MicroJail.pre_launch_verify()` orchestrates launch-time verification.** It iterates every `Gate` and every `Capability` (in that order), collecting `VerificationResult.UNSUPPORTED` names into an `unsupported_verifications` list. A gate returning `FAILED` raises `GateError(name=<gate-name>, unsupported_verifications=tuple(unsupported_verifications))` and short-circuits — no further `verify()` calls. A capability returning `FAILED` either:
- raises `CapabilityError(name=<cap-name>, non_fatal_failures=tuple(non_fatal_failures_collected_so_far), unsupported_verifications=tuple(unsupported_verifications))` if the capability is `fatal=True`, or
- is recorded in `non_fatal_failures` and iteration continues if `fatal=False`.

Both `GateError.unsupported_verifications` and `CapabilityError.unsupported_verifications` may contain a mix of gate and capability names, in the order they were observed.

**Workload-bearing commands (`lock`, `exec`, `shell`) call `pre_launch_verify()` after `ensure_lockdown` succeeds.** All three share the `ensure_lockdown` helper in `commands/lock.py`, which is what invokes `pre_launch_verify()`. On success, the returned `PreLaunchVerifyResult` is surfaced by that helper: each name in `unsupported_verifications` is emitted to stdout via `info(f"Note: Verification not supported for {name}")`; each name in `non_fatal_capability_failures` is emitted to stderr via `warning(name)`. `exec` and `shell` call `microjail.popen` / `microjail.shell()` only after `pre_launch_verify` returns without raising. On `GateError`, exit code 68 (`GATE_APPLICATION_FAILURE`). On `CapabilityError`, exit code 66 (`CAPABILITY_APPLICATION_FAILURE`). Both codes are reused from ADR 0001.

**`NetworkDrop.check()` no longer shells out to `bash`.** The previous implementation ran `bash -c ": >/dev/tcp/1.1.1.1/443"` inside the container on every Warden poll. With this ADR the bash probe is removed from `check()`; the absence of a NIC in `InstanceInfo.devices` is the actual enforcement. Behavioral probing is moved to `pre_launch_verify` — and for `NetworkDrop`, `verify()` returns `UNSUPPORTED` because there is no behavioral probe that adds information beyond the config check.

## Consequences

**Positive**

- The bash egress probe no longer runs on every Warden poll. Probe cost is paid once at launch, not on the polling loop.
- The bash dependency is removed from the check path. Containers without `bash` (alpine, distroless, scratch) no longer trigger false-positive gate violations.
- `check()` is fast, side-effect-free, and safe to call in tight loops; `verify()` is allowed to be slow and may raise. The two concerns are explicitly separated.
- `UNSUPPORTED` is first-class: a gate that does not need behavioral probing can declare so without lying about its verification status. The CLI can tell the user "this was not probed" instead of conflating it with "this passed".
- The exception surface (`non_fatal_failures`, `unsupported_verifications`) gives the CLI enough context to surface partial-failure output alongside a fatal error, in a single exit.
- Exit codes 66 and 68 (already defined by ADR 0001) are reused. No new policy-result codes needed.

**Negative**

- `verify()` is required by the `Gate` and `Capability` protocols, so every implementer (including purely config-only ones like `ReadonlyConfig`) must provide a `verify()` method. The cost is small (a one-liner returning `UNSUPPORTED`) but it does mean the protocol is no longer "add `check()` and you're done."
- The `pre_launch_verify` pass adds a small but measurable cost to `lock`/`exec`/`shell` startup. For a typical 3-gate/1-cap lockdown the pass is sub-second; for endpoint capabilities that include a TCP probe it can be up to the existing 5s probe timeout. The `fatal: false` escape hatch lets a capability be a warning instead of a launch blocker.
- This ADR does not change the runtime polling loop. Capabilities are still monitored at runtime; gate violations are still detected on the next poll. A subsequent ADR on the `refactor/event-warden-retry` branch replaces polling with event-driven LXD lifecycle monitoring and uses the same `check()`/`verify()` split.

**Reversibility**

Low cost. Removing `verify()` and folding its semantics back into `check()` is a one-method-per-implementer revert. The exception fields (`non_fatal_failures`, `unsupported_verifications`) can be dropped by reverting their default to `()`. The CLI surface (`Note: Verification not supported for ...` and `warning: ...`) can be removed by reverting the call site in `commands/lock.py`. The contract change is additive at every call site that uses `check()` (which still works as before).
