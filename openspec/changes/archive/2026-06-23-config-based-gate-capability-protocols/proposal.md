## Why

The current gate and capability protocols conflate configuration checks with behavioral verification, and run expensive behavioral probes (like `NetworkDrop`'s bash-based egress check) on a periodic runtime polling loop. This causes high CPU usage, introduces runtime dependencies (e.g. requiring `bash` inside alpine/distroless/scratch containers for the egress probe, leading to false positives), and mixes liveness with configuration enforcement. Splitting these checks into quick config-only checks at runtime and behavioral verification at launch-time improves stability, removes runtime bash dependencies, and separates concern between configuration alignment and endpoint reachability.

## What Changes

- **Protocol Extension**: `Gate` and `Capability` protocols gain a new `verify(microjail)` method for behavioral verification returning a `VerificationResult` enum (`VERIFIED`, `FAILED`, `UNSUPPORTED`). The semantic of `check(microjail)` is narrowed to a lightweight configuration-state check only.
- **Config-Only Gates**:
  - `NetworkDrop.check()` becomes config-only (validates that the workshop container's `expanded_devices` contains no devices of `type: nic`). **BREAKING**: the old behavioral bash probe is removed from `check()`.
  - `NetworkDrop.verify()` returns `VerificationResult.UNSUPPORTED` unconditionally (no behavioral probe).
  - `ReadonlyConfig.check()` remains config-only.
  - `ReadonlyConfig.verify()` returns `VerificationResult.UNSUPPORTED` unconditionally.
- **Config/Behavioral Split for Capabilities**:
  - `WorkshopEndpointCapability.check()` becomes config-only (validates that the Workshop tunnel connection is present in `workshop connections`). **BREAKING**: it no longer performs a TCP reachability probe.
  - `WorkshopEndpointCapability.verify()` performs the TCP reachability probe from inside the container, returning `VERIFIED` or `FAILED`.
- **Pre-Launch Verification**:
  - A new `MicroJail.pre_launch_verify() -> PreLaunchVerifyResult` method executes `verify()` on all gates and capabilities.
  - Workload commands (`lock`, `exec`, and `shell`) call `pre_launch_verify()` after `ensure_lockdown` but before starting any workload process.
  - Verification failure (`FAILED`) raises `GateError` or `CapabilityError` and blocks the launch (exits command with code 68 or 66).
  - Unsupported verification (`UNSUPPORTED`) is treated as success (treated as yes) but causes the CLI to display an extra note to the user.
  - Non-fatal capability verification failure (`fatal=False`) returns warnings, which are printed to stderr and do not block the launch.

## Capabilities

### New Capabilities
- `pre-launch-verify`: Behavioral pre-launch verification of all gates and capabilities in a lockdown before workload execution.
- `network-drop`: Gate config-state check (no NICs in expanded devices) and verify protocol.

### Modified Capabilities
- `endpoint-capability`: Split `check()` (config check for tunnel connections) and `verify()` (behavioral TCP probe returning `VERIFIED` or `FAILED`).
- `readonly-config`: Add `verify()` method returning `UNSUPPORTED`.

## Impact

- **`src/microjail/gates/base.py` & `src/microjail/caps/base.py`**: Extend protocol definitions with `verify(microjail: MicroJail) -> VerificationResult`. Define `VerificationResult` StrEnum.
- **`src/microjail/gates/network_drop.py`**: Replace egress check in `check()` with `expanded_devices` NIC check; add `verify() -> VerificationResult` returning `UNSUPPORTED`.
- **`src/microjail/gates/readonly_config.py`**: Add `verify() -> VerificationResult` returning `UNSUPPORTED`.
- **`src/microjail/caps/endpoint.py`**: Narrow `check()` to connection list inspection; add `verify() -> VerificationResult` doing TCP reachability check.
- **`src/microjail/microjail.py`**: Add `PreLaunchVerifyResult` and `pre_launch_verify()`.
- **`src/microjail/commands/lock.py`, `exec.py`, `shell.py`**: Call `pre_launch_verify()` and map exceptions to exit codes 68/66 or print warnings/notes.
- **Tests**: Update unit and functional tests to align with the new protocols and assert verification behavior.
