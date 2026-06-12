## Context

Currently, the `microjail` codebase communicates with Workshop environments solely using blocking commands via `subprocess.run` wrapped in `workshop.exec_` and `MicroJail.exec_`. For the upcoming Warden component (which supervises and monitors policy compliance for a Workload), we need a way to execute the Workload asynchronously and retain a host-side Workload process handle (`subprocess.Popen` instance) to control it.

## Goals / Non-Goals

**Goals:**
- Expose a `popen` function in the `workshop` adapter that mimics the parameter list of `exec_` but runs `subprocess.Popen` instead of `subprocess.run` and returns a Workload process handle (`subprocess.Popen` object).
- Expose a `popen` method in `MicroJail` that routes to `workshop.popen`.
- Validate that the target Workshop environment exists and is launched before starting the process, raising `WorkshopNotFoundError` and `WorkshopNotLaunchedError` as appropriate.
- Allow full customizability of standard streams and other subprocess options via `**kwargs`.

**Non-Goals:**
- Modifying the existing `exec_` methods.
- Implementing any Warden-specific monitoring logic in this change (this change is strictly the execution engine refactoring).

## Decisions

### D1: Dedicated API endpoints (`workshop.popen`, `MicroJail.popen`) over overloaded parameters
- **Rationale**: Python type hints can cleanly differentiate between a `CompletedProcess` return type and a `Popen` return type without using complex `@overload` decorator signatures. This makes it more maintainable and clear.
- **Alternative considered**: Adding a parameter to `exec_` and returning a union. Rejected because union return types force the caller to write type assertions/checks.

### D2: Standard error raising logic alignment
- **Rationale**: We reuse `exists()` and `info()` checks from the workshop adapter so that missing/unlaunched containers raise exact exceptions synchronously before the process is spawned.
- **Alternative considered**: Relying on the underlying command failure. Rejected because running `workshop exec` on a missing workshop yields a standard subprocess return code instead of Python-native semantic errors like `WorkshopNotFoundError`.

### D3: Interactive PTY handling via direct stream inheritance (Option A)
- **Rationale**: Bypassing custom Warden stream proxying avoids complex terminal control replication (such as TTY signal forwarding, echo settings, or dynamically communicating window size changes via ioctls). Since the Warden does not need to intercept or rewrite standard input/output bytes for the user session, direct stream inheritance is both simpler and less error-prone.
- **Alternative considered**: Warden-managed proxy using PTY master/slave loops (Option B). Rejected due to unnecessary complexity.

### D4: Workload signaling and lifecycle escalation
- **Rationale**: Sending signals (like `SIGTERM`) to the host-side Workload process handle (`workshop exec` process) is the primary method for terminating the Workload. If the Workload fails to terminate within a timeout, the Warden or caller will escalate to explicit LXD container-level process termination to guarantee that the Workload is completely stopped.
- **Alternative considered**: Sending all termination signals exclusively at the container level. Rejected because host-side signaling is standard and faster for typical clean shutdowns.

### D5: Synchronous validation phase
- **Rationale**: `workshop.popen` performs synchronous checking of the Workshop environment's existence and status before spawning the process. This guarantees that `WorkshopNotFoundError` or `WorkshopNotLaunchedError` is raised immediately to the caller, preventing silent launch failures.
- **Alternative considered**: Performing checks asynchronously. Rejected because immediate fail-fast error reporting is much more useful and robust for callers.
## Risks / Trade-offs

- **[Risk] Popen resources leak if caller doesn't close them** → **Mitigation**: Standard library guidelines apply. Ensure caller code closes streams or uses a context manager.
