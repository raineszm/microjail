## Context

Currently, `microjail` applies a security policy (a Lockdown) and runs the workload inside the Workshop container using `microjail.exec_`, which blocks and waits for completion. During this execution, there is no runtime supervision. If a Gate ceases to hold or if a Capability is modified/removed, the system does not detect the violation or terminate the workload. The Warden is the planned runtime supervisor designed to resolve this gap by continuously monitoring policy invariants.

## Goals / Non-Goals

**Goals:**
- Implement a `Warden` class that supervises a workload process (a `subprocess.Popen` instance) running under an applied Lockdown.
- Polling mechanism: Check all applied Gates and Capabilities at a configurable interval (default: 1.0 seconds).
- Gate violations: If any Gate's `check()` returns `False`, terminate the workload immediately and exit with code 84.
- Capability violations: If any Capability's `check()` returns `False`, log a warning to stderr. If the capability is configured as `fatal=True`, terminate the workload immediately and exit with code 82.
- Integrate Warden supervision into the `microjail run` CLI command.
- Do not release the Lockdown policy upon workload exit or termination.

**Non-Goals:**
- Teardown of the Workshop environment (this is handled by `destroy` command).
- Releasing the Lockdown automatically on exit (it must remain locked until explicitly unlocked).
- Running the supervision loop in a separate thread or process. A synchronous polling loop during command execution is sufficient and simpler.

## Decisions

### 1. Synchronous Polling Loop in `Warden.supervise()`
- **Choice**: A synchronous `while` loop calling `process.wait(timeout=self.interval)` on the main thread.
- **Rationale**: Since `microjail run` is a CLI command that blocks until the workload completes, running the polling loop on the main thread is simple, robust, and avoids thread-safety or async loop coordination issues. Using `process.wait(timeout=self.interval)` allows the loop to block efficiently, waking up immediately if the workload process exits early (eliminating CLI exit lag), or throwing `subprocess.TimeoutExpired` when the interval elapses (at which point we check all Gates and Capabilities).
- **Alternative**:
  * `time.sleep(self.interval)`: Causes up to `self.interval` seconds of exit lag when the workload process terminates.
  * Multi-threading or Asyncio loop: Adds complexity and dependency overhead (e.g., handling thread interruption/signals or managing async event loops in Typer) without providing material benefits.

### 2. Configure Capability Fatality via `fatal` Attribute
- **Choice**: Add a `fatal: bool = False` field to the `Capability` protocol and its `WorkshopEndpointCapability` implementation.
- **Rationale**: This allows users to optionally configure specific capabilities to be fatal on violation directly in `.microjail/config.yaml`.
- **Alternative**: Hardcoding all capability violations as warnings, or making all of them fatal. This doesn't meet the requirement of being "warnings by default and can be promoted to fatal per-capability in config."

### 3. Execution Integration using `MicroJail.popen`
- **Choice**: The CLI `run` command will launch the workload using `microjail.popen` to obtain a `subprocess.Popen` handle, pass it to the `Warden`, and invoke `warden.supervise()`.
- **Rationale**: This separates process launching from process supervision and aligns with the existing architecture.

## Risks / Trade-offs

- **[Risk]** Polling overhead from `gate.check()` / `cap.check()`.
  - *Mitigation*: The default polling interval of 1 second is infrequent enough to prevent measurable CPU overhead on modern systems, while still providing prompt violation detection. The interval is configurable in the `Warden` constructor (e.g., for testing).
- **[Risk]** Workload zombie processes or delayed termination.
  - *Mitigation*: When a violation is detected, `Warden` will call `process.terminate()`. If the process does not terminate within a 2-second timeout, `Warden` will escalate to force-stopping the LXC container (e.g. via `lxc stop <container> --force`). This guarantees the remote workload process inside the container is terminated, preventing it from being orphaned and running unsupervised.
