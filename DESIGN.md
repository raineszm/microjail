# Microjail Design Specification

## Overview

Microjail is a lightweight orchestration layer for establishing, monitoring, and maintaining a secure execution environment for autonomous agents and other untrusted workloads.

Microjail does not implement sandboxing or proxying primitives itself. Workshop and LXD provide the underlying sandbox/proxy mechanisms; Microjail configures, composes, monitors, and releases them to make the secure path safer and less error-prone than manual configuration.

Current microjail instances are Workshop-backed: every instance is associated with a Workshop project and execution environment.

Microjail manages:

* Desired security policy
* Capability provisioning
* Restriction enforcement
* Runtime integrity monitoring
* Workload execution

A workload is the command and process tree executed inside the Workshop environment under an applied Lockdown. The Workshop environment persists after workload termination.

Microjail does not persist runtime state.

Microjail behaves like a safety checklist: it turns declarative Lockdown into ordered, verified, repeatable operations against Workshop/LXD, with live inspection as the source of truth.

A microjail instance is one configured per-project binding between a Workshop project, project path, and Lockdown.

---

# Goals

* Secure-by-default execution environment
* Explicit capability granting
* Continuous enforcement of security invariants
* Runtime detection of policy violations
* Minimal statefulness
* Maximal safe reuse of Workshop and LXD mechanisms
* Simple CLI workflow

---

# Architecture

## Core Components

### Lockdown

Represents desired security policy.

A Lockdown consists of:

* Capabilities
* Gates

A Lockdown is declarative policy data. It does not know whether the environment is currently locked, and it does not apply or release policy by itself.

Microjail applies and releases a Lockdown by inspecting live system state.

Public shape:

```python
class Lockdown:
    caps: list[Capability]
    gates: list[Gate]
```

Lockdown is not a public context manager.

---

### Capability

A capability represents functionality or access intentionally made available to workloads that would otherwise be unavailable.

Examples:

* Endpoint proxy
* Read-only project mount that exposes an otherwise unavailable project path
* Writable overlay
* MCP endpoint
* Workshop SDK connection

Changing already-visible access from writable to read-only is a gate, not a capability.

Interface:

```python
class Capability:
    name: str

    def check(self) -> bool
    def provide(self) -> None
    def revoke(self) -> None
```

Semantics:

```text
check
  verify capability exists

provide
  create capability if missing

revoke
  remove capability
```

Capabilities follow:

```text
check → provide → verify
```

---

### Gate

A gate represents a security invariant that must hold by removing, limiting, or continuously enforcing against ambient access.

Examples:

* Deny network egress
* Hide host secrets
* Restrict filesystem visibility

* Drop Linux capabilities
* Enforce read-only root filesystem
* Make an already-visible project path read-only

Gates are always fatal. A warning-only restriction should not be modeled as a Gate.

Interface:

```python
class Gate:
    name: str

    def check(self) -> bool
    def enforce(self) -> None
    def release(self) -> None
```

Semantics:

```text
check
  verify restriction holds

enforce
  establish restriction

release
  remove restriction
```

Gates follow:

```text
check → enforce → verify
```

---

### Warden

The Warden supervises workload execution.

Responsibilities:

* Launch subprocesses
* Monitor capabilities
* Monitor gates
* Terminate workloads when policy violations occur
* Tag supervised workloads so they can be discovered later without persisted runtime state

Interface:

```python
class Warden:
    def run(args: list[str]) -> int
```

The Warden never unlocks the environment.

Warden-related discovery uses live process and Workshop/LXD inspection. Microjail may tag process groups, environment, or process metadata with microjail instance identity to make active workload discovery reliable, but it does not persist runtime pid files.

The microjail instance identity is derived from configuration, not persisted runtime state. It uses the Workshop name and canonical project path, and may be hashed into a short safe token for process tags or environment variables.

By default, only one Warden-supervised workload may run for a microjail instance at a time. Concurrent workloads require a future explicit run-session model.

---

# Lockdown Lifecycle

## Applying Lockdown

When Microjail applies a Lockdown:

### Phase 1: Capabilities

For every capability:

```text
check
if missing:
    provide
verify
```

If `check()` or verification raises, Microjail treats that as a capability application failure and does not attempt to guess the current state.

Capability application failures are collected so Microjail can report all missing capabilities together. By default, any capability application failure blocks workload launch.

### Phase 2: Gates

For every gate:

```text
check
if unsatisfied:
    enforce
verify
```

If `check()` or verification raises, Microjail treats that as a gate application failure and does not attempt to guess the current state.
Gate application failures stop policy application at the first failed gate.

Before workload launch, Microjail reports collected capability application failures and blocks launch unless configuration explicitly permits degraded startup.

When applying Lockdown for `microjail run`, required capability application failures stop before gate enforcement because no workload will launch.

When applying Lockdown for `microjail lock`, Microjail still proceeds to gate enforcement after capability application failures because the user explicitly requested the safest reachable posture.

Rollback behavior is command-dependent:

* `microjail run` rolls back capabilities and gates applied during the failed attempt when the workload will not launch.
* `microjail lock` does not roll back successfully applied capabilities or gates after partial failure; it leaves the safest reachable posture in place and reports the incomplete or failed result.

Ordering is significant.

Capabilities are established first.

Restrictions are enforced second.

This permits explicitly allowed functionality before broad denial policies are applied.

---

## Releasing Lockdown

Release occurs only through explicit user action.

Release order:

### Phase 1

Release gates in reverse order.

### Phase 2

Revoke capabilities in reverse order.

Release and revoke operations are idempotent. Unlock derives what to release from configured policy and live inspection, not from persisted runtime state. If a configured capability or gate is absent, its revoke or release operation succeeds as a no-op.

Unlock attempts every configured release/revoke operation even after failures, then reports all release failures together.

No automatic release occurs after workload execution.

---

# Runtime Enforcement

The Warden validates policy at a configured polling interval while workloads execute.

Default interval: 1 second.

Polling is the correctness baseline. Event-driven monitoring may be added later as an optimization.

Each monitoring pass validates:

```python
gate.check()
capability.check()
```

If any capability disappears unexpectedly:

```text
capability policy violation
```

If any gate becomes unsatisfied:

```text
gate policy violation
```

If a check errors instead of returning a result, Microjail treats that as a policy violation of the thing being checked. If Microjail cannot prove the Lockdown still holds, it assumes it does not hold.

Capability policy violations are warnings by default and can be upgraded to fatal by configuration.

Gate policy violations are fatal because they can expose access that should be denied.

During each monitoring pass, the Warden:

1. Checks Gates and stops at the first gate policy violation.
2. If a gate policy violation occurred, terminates the workload with a gate policy violation result.
3. Checks all Capabilities and collects all capability policy violations.
4. If any collected capability policy violation is configured as fatal, terminates the workload with a fatal capability policy violation result.
5. Otherwise, reports collected capability policy violations as warnings and continues supervision.

Upon fatal policy violation:

1. Send SIGTERM to the workload process group
2. Wait grace period
3. Send SIGKILL to the workload process group if required
4. Return failure

---

# Workshop Integration

## Architectural Principle

Microjail uses Workshop and LXD as the sandbox/proxy substrate.

Microjail owns orchestration, policy application, monitoring, and user-facing workflow.

Workshop is required for current microjail instances. Direct LXD access is allowed when Workshop does not surface the required control, as long as the operation targets the Workshop-backed environment for the microjail instance.

---

## Examples

Preferred:

```text
Endpoint proxy
  → Workshop tunnel interface

Service visibility
  → Workshop SDK configuration

Connectivity
  → Workshop plugs and slots

Endpoint exposure
  → Workshop connection management
```

Avoid when possible:

```text
Custom TCP proxy
Custom service registry
Custom endpoint manager
Custom connection tracker
```

---

## Endpoint Proxies

Endpoint proxy behavior is provided by Workshop tunnel interfaces. Microjail configures and verifies the Workshop resources needed for those proxies; it does not implement the proxy protocol itself.

A network path is authorized only when represented as a declared Capability in the Lockdown. Pre-existing Workshop tunnels or connections are not treated as Microjail-authorized unless the Lockdown declares them.

Examples:

```text
OpenAI-compatible endpoint
Local inference endpoint
MCP service endpoint
GitHub proxy endpoint
```

Capability implementation:

```python
class WorkshopEndpointProxy(Capability):
    ...
```

Checks include:

* SDK declaration exists
* Plug exists
* Slot exists
* Connection exists
* Endpoint is reachable

Provisioning includes:

* Create SDK declaration if needed
* Refresh Workshop
* Connect plugs and slots

---

# Configuration

## Persistent Data

Only configuration is persisted.

Example:

```text
.microjail/
  config.yaml
```

Capability criticality is configured per capability.

Defaults:

```yaml
application_failure: fatal
runtime_violation: warning
```

Example:

```yaml
capabilities:
  - type: endpoint-tunnel
    name: openai
    application_failure: fatal
    runtime_violation: warning
```

Warden polling interval is configured as a project default:

```yaml
warden:
  poll_interval: 1s
```

Gate criticality is not configurable. Gate application failures and gate policy violations are always fatal.

---

## Runtime State

Runtime state is never persisted.

Microjail does not store:

```text
locked/unlocked status
active capabilities
gate status
connection status
warden state
```

---

# Stateless Safety Model

Configuration is declarative.

Observed system state is authoritative.

Every operation derives state from live inspection.

Example:

```text
microjail lock
```

does not read a cached "locked" flag.

Instead:

```python
gate.check()
capability.check()
```

are executed directly.

Likewise:

```text
microjail run
```

always performs:

```python
microjail.ensure()
```

before execution.

Benefits:

* Crash resistant
* No stale state
* No state drift
* Safe after manual intervention
* Safe after Workshop modifications
* Reduced attack surface

---

# CLI Specification
## Output Style

Default CLI output is concise and result-oriented.

Checklist-style progress is available for `lock` and `run` when verbose output is requested. Verbose output should expose safety-checklist phases such as Workshop readiness, capability verification, gate enforcement, and Warden monitoring.

Default summaries include zero counts. For example, `0 capabilities` is printed explicitly so secure defaults are visible.

---


## init

Create project configuration.

```bash
microjail init
```

Responsibilities:

* Create .microjail directory
* Create config.yaml
* Write only implemented Gates and Capabilities
* Validate Workshop availability
* Validate local SDK accessibility

Does not lock the environment.

`init` does not write placeholder configuration for target secure-default Gates that are not implemented yet.

---

## lock

Apply configured policy.

```bash
microjail lock [--force]
```

Responsibilities:

* Load configuration
* Build Lockdown
* Ensure capabilities
* Enforce gates
* Continue to gates even if capability application failures occurred
* Report results

`microjail lock` reports success only when the full configured Lockdown holds. If capabilities fail but gates are enforced, the result is incomplete rather than locked.

Result wording:

```text
lock applied: <capability-count> capabilities, <gate-count> gates
lock incomplete: <capability-failure-count> capability failures, <gate-count> gates enforced
lock failed: gate <gate-name> failed
```

`lock incomplete` and `lock failed` both return non-zero exit codes, with distinct bitmask codes so callers can distinguish degraded capability state from gate enforcement failure.

Does not persist runtime state.

## Exit Code Classes

Microjail reserves bitmask exit codes for policy results while preserving workload exit-code passthrough when a workload runs without fatal policy failure.

```text
0x00  success
0x01  generic command/config/workshop error

0x40  Microjail policy-result marker
0x10  runtime phase bit
0x20  release phase bit

0x02  capability bit
0x04  gate bit
0x08  workload bit
```

Policy-result examples:

```text
0x42 / 66   capability application failure
0x44 / 68   gate application failure
0x52 / 82   fatal runtime capability policy violation
0x54 / 84   runtime gate policy violation
0x58 / 88   runtime workload termination failure
0x62 / 98   capability release failure
0x64 / 100  gate release failure
0x66 / 102  capability + gate release failures
0x68 / 104  release blocked by active workload termination failure
```

For `microjail run`, if Microjail policy fails before or during execution, return the Microjail bitmask code. If the workload ran and no fatal policy issue occurred, pass through the workload exit code.


---

## run

Run workload under supervision.

```bash
microjail run [--poll-interval 1s] -- <command>
```

Responsibilities:

* Load configuration
* Refuse to start if another Warden-supervised workload is already running for the same microjail instance
* Apply Lockdown, stopping before gates if required capability application failed
* Launch workload
* Start Warden
* Monitor policy compliance
* Terminate on violation
* Use configured Warden poll interval unless overridden by CLI
* Refuse destructive cleanup; users must run `microjail lock --force` first when Gate enforcement requires removing pre-existing undeclared state

Does not unlock afterward.

---

## unlock

Explicitly release policy.

```bash
microjail unlock [--force]
```

Responsibilities:

* Load configuration
* Terminate currently running Microjail-supervised workloads for this microjail instance
* Release gates
* Revoke capabilities
* Report failures
* Treat absent configured capabilities or gates as already released

Before releasing policy, `unlock` terminates any currently running `microjail run` workloads for the same microjail instance using the Warden termination sequence.

If any active workload cannot be terminated or cannot be verified stopped, `unlock` stops before releasing gates or revoking capabilities.

`unlock --force` escalates by forcibly stopping the Workshop/LXD container for the microjail instance, then verifies active workloads are stopped before releasing gates or revoking capabilities. It still does not release policy while a supervised workload may be running.

After `unlock --force` stops the Workshop/LXD container, it leaves the container stopped. Restarting the environment is explicit Workshop lifecycle management, not part of unlock.

Discovery of active workloads uses live process and Workshop/LXD inspection, not persisted runtime state.

`microjail unlock` returns a release-failure bitmask when any release or revoke operation fails.

This is the only command that weakens the lockdown.

---

# Secure Defaults

Default configuration grants no capabilities.

Default restrictions should produce a secure baseline. Some restrictions are inherited from the default Workshop/LXD container configuration; Microjail should not duplicate those mechanisms, but any restriction Microjail promises should be represented by a Gate so it can be verified.

Target baseline:

```text
deny network egress
hide host secrets
drop host mounts
read-only root or project-sensitive paths
drop dangerous Linux capabilities
```

For inherited defaults, `check()` validates the restriction. `enforce()` may be a no-op when the inherited default already holds, or may tighten/restore configuration when it does not.

Currently implemented Microjail Gates:

```text
deny network egress
read-only Microjail config mount
```

Project config should contain only implemented Gates. Target secure-default Gates are added to config only when their implementations exist.

The network-egress Gate currently enforces by removing LXD NIC devices. That mechanism is an implementation detail of the Gate; the design invariant is no unauthorized network egress. Workshop tunnels are confirmed to continue working after NIC removal.

Authorized egress exists only through declared Capabilities. Pre-existing Workshop or LXD connectivity that is not represented in the Lockdown is unauthorized from Microjail's perspective.

When pre-existing undeclared state must be removed to enforce the Lockdown, Microjail requires explicit confirmation such as `--force`. This includes undeclared connectivity, LXD devices, mounts, Workshop connections, and proxy resources. Without confirmation, removal is refused and the relevant Gate application fails.

`microjail run` does not accept destructive cleanup confirmation. If a run would require removing pre-existing undeclared state, it fails before launching the workload and directs the user to run `microjail lock --force` first.

Users must explicitly opt into capabilities.

---

# Design Decisions

1. Lockdown is declarative policy; applying or releasing it is explicit.
2. Lockdown is not a public context manager.
3. Unlocking is always explicit.
4. Capabilities use check → provide → verify semantics.
5. Gates use check → enforce → verify semantics.
6. Warden continuously validates policy invariants.
7. Warden never unlocks.
8. Secure defaults expose no capabilities.
9. Microjail delegates to Workshop whenever possible.
10. Configuration is persisted.
11. Runtime state is never persisted.
12. Live system inspection is always the source of truth.
13. Capability provisioning occurs before restriction enforcement.
14. Release occurs in reverse dependency order.
15. Safety takes precedence over convenience.
