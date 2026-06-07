# Microjail Design Specification

## Overview

Microjail is a lightweight orchestration layer for establishing, monitoring, and maintaining a secure execution environment for autonomous agents and other untrusted workloads.

Microjail is not itself a sandbox implementation. Instead, it composes existing isolation mechanisms, with a strong preference for delegating functionality to Workshop whenever possible.

Microjail manages:

* Desired security policy
* Capability provisioning
* Restriction enforcement
* Runtime integrity monitoring
* Workload execution

Microjail does not persist runtime state.

---

# Goals

* Secure-by-default execution environment
* Explicit capability granting
* Continuous enforcement of security invariants
* Runtime detection of policy violations
* Minimal statefulness
* Maximal delegation to Workshop
* Simple CLI workflow

---

# Architecture

## Core Components

### Lockdown

Represents a desired security posture.

A Lockdown consists of:

* Capabilities
* Gates

A Lockdown can:

* Ensure capabilities exist
* Ensure gates are enforced
* Release capabilities and gates when explicitly requested

Public interface:

```python
class Lockdown:
    def ensure(self) -> None
    def release(self) -> None
```

Lockdown is not a public context manager.

---

### Capability

A capability represents functionality intentionally exposed to workloads.

Examples:

* Endpoint proxy
* Read-only project mount
* Writable overlay
* MCP endpoint
* Workshop SDK connection

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

A gate represents a restriction that must hold.

Examples:

* Deny network access
* Hide host secrets
* Restrict filesystem visibility
* Drop Linux capabilities
* Enforce read-only root filesystem

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

Interface:

```python
class Warden:
    def run(args: list[str]) -> int
```

The Warden never unlocks the environment.

---

# Lockdown Lifecycle

## Ensuring Lockdown

When Lockdown is ensured:

### Phase 1: Capabilities

For every capability:

```text
check
if missing:
    provide
verify
```

### Phase 2: Gates

For every gate:

```text
check
if unsatisfied:
    enforce
verify
```

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

No automatic release occurs after workload execution.

---

# Runtime Enforcement

The Warden continuously validates:

```python
capability.check()
gate.check()
```

while workloads execute.

If any capability disappears unexpectedly:

```text
policy violation
```

If any gate becomes unsatisfied:

```text
policy violation
```

Upon violation:

1. Send SIGTERM to process group
2. Wait grace period
3. Send SIGKILL if required
4. Return failure

---

# Workshop Integration

## Architectural Principle

Microjail delegates to Workshop whenever Workshop can express the functionality.

Microjail should orchestrate.

Workshop should implement.

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

Endpoint proxies are implemented using Workshop tunnel interfaces.

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
  lockdown.yaml
```

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
lockdown.ensure()
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

## init

Create project configuration.

```bash
microjail init
```

Responsibilities:

* Create .microjail directory
* Create lockdown.yaml
* Validate Workshop availability
* Validate local SDK accessibility

Does not lock the environment.

---

## lock

Apply configured policy.

```bash
microjail lock
```

Responsibilities:

* Load configuration
* Build Lockdown
* Ensure capabilities
* Enforce gates
* Report results

Does not persist runtime state.

---

## run

Run workload under supervision.

```bash
microjail run -- <command>
```

Responsibilities:

* Load configuration
* Ensure Lockdown
* Launch workload
* Start Warden
* Monitor policy compliance
* Terminate on violation

Does not unlock afterward.

---

## unlock

Explicitly release policy.

```bash
microjail unlock
```

Responsibilities:

* Load configuration
* Release gates
* Revoke capabilities
* Report failures

This is the only command that weakens the lockdown.

---

# Secure Defaults

Default configuration grants no capabilities.

Default restrictions include:

```text
deny network access
hide host secrets
drop host mounts
read-only root
drop dangerous Linux capabilities
```

Users must explicitly opt into capabilities.

---

# Design Decisions

1. Lockdown is explicit and long-lived.
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
