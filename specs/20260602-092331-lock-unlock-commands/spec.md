# Feature Specification: Lock and Unlock Commands

**Feature Branch**: `20260602-092331-lock-unlock-commands`

**Created**: 2026-06-02

**Status**: Draft

**Input**: User description: "Implement the lock and unlock commands as paired operations. Lock should ensure that all conditions mentioned in the lock section of the README.md apply. Unlock should restore us to the previous state."

## Clarifications

### Session 2026-06-02

- Q: Should the microjail state file (`.microjail/state.json`) be readonly inside the container? → A: Yes. The state file MUST be verified as not writable from inside the container before the workload is spawned; this is an unconditional lock gate. The mechanism is a `readonly=true` LXD bind-mount device that overlays the state file path inside the container. The gate verifies that this device is present and active via `lxc config device show`.
- Q: Must `microjail run` produce a persistent log of each invocation? → A: Yes (constitution §Security). Every `run` invocation MUST write a log entry recording the gate results, the workload command, start time, and exit code. The log MUST be retained after `unlock`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Lock and run a workload (Priority: P1)

A developer has initialised and provisioned a microjail environment. They run `microjail run -- <command>` to execute a workload with full network isolation. Before spawning the command, microjail locks the environment (cuts egress) and runs all lock gates. If every gate passes the workload starts; if any gate fails the command exits non-zero without ever starting the workload.

**Why this priority**: This is the primary value of microjail. Without `run`, the tool cannot fulfil its stated purpose of executing workloads in a network-sealed container.

**Independent Test**: Run `microjail run -- echo hello` in a workspace with a fully provisioned environment; verify `echo hello` executes and exits zero, and that during its execution no external network destination is reachable from inside the container.

**Acceptance Scenarios**:

1. **Given** an initialised, provisioned environment with all prerequisites satisfied, **When** the user runs `microjail run -- <workload>`, **Then** egress is severed, all lock gates pass, the workload executes, and the command exits with the workload's exit code.

2. **Given** an environment where a lock gate fails (e.g., egress is still reachable), **When** the user runs `microjail run -- <workload>`, **Then** the command exits non-zero, names the failing gate in the error message, and the workload is never spawned.

3. **Given** no initialised environment in the workspace (missing state file), **When** the user runs `microjail run`, **Then** the command exits non-zero with a clear message explaining that `microjail init` must be run first.

---

### User Story 2 - Unlock to restore networking (Priority: P1)

After a workload run is complete (or was manually interrupted), the developer runs `microjail unlock` to restore normal network egress so they can continue provisioning, debugging, or tearing down the environment.

**Why this priority**: `unlock` is required to complete the lifecycle. An environment left permanently locked is unusable for further provisioning or teardown.

**Independent Test**: After a `microjail run` completes, run `microjail unlock`; verify that the environment can reach external network destinations and that the environment state reflects the unlocked status.

**Acceptance Scenarios**:

1. **Given** a locked environment, **When** the user runs `microjail unlock`, **Then** network egress is restored to the container, the command exits zero, and the state file records the environment as unlocked.

2. **Given** an environment that is already unlocked, **When** the user runs `microjail unlock`, **Then** the command exits zero with an informational message indicating the environment is already unlocked; no error is raised.

3. **Given** no initialised environment in the workspace, **When** the user runs `microjail unlock`, **Then** the command exits non-zero with a message directing the user to run `microjail init` first.

---

### User Story 3 - Lock the environment without running a workload (Priority: P1)

A developer wants to seal the environment before manually entering it or running a workload via another mechanism. They run `microjail lock` to sever egress and verify all lock gates without spawning any workload command.

**Why this priority**: `lock` is the paired counterpart to `unlock`. Making it a standalone command lets users apply the same egress-sealing and gate-checking logic outside of `microjail run`, and makes the lock/unlock symmetry explicit at the CLI level. `microjail run` internally delegates to `lock` rather than reimplementing the locking logic.

**Independent Test**: Run `microjail lock` on a provisioned environment; verify all gates pass, the state file records the environment as locked, and network egress is unreachable from inside the container — without any workload being spawned.

**Acceptance Scenarios**:

1. **Given** an initialised, provisioned environment with all prerequisites satisfied, **When** the user runs `microjail lock`, **Then** egress is severed, all lock gates pass, the state file is updated to locked, and the command exits zero.

2. **Given** a lock gate fails (e.g., workspace not mounted), **When** the user runs `microjail lock`, **Then** the command exits non-zero naming the failing gate; the environment is unlocked again (egress restored) before exit.

3. **Given** the environment is already locked, **When** the user runs `microjail lock`, **Then** the command exits zero with an informational message indicating it is already locked; no double-lock occurs.

4. **Given** no initialised environment in the workspace, **When** the user runs `microjail lock`, **Then** the command exits non-zero directing the user to run `microjail init` first.

---

### User Story 4 - Inference socket verified before workload starts (Priority: P2)

When the environment was initialised with `--inference llama-cpp`, the developer relies on the local model being ready before the agent starts. The lock gate verifies the socket file exists and is reachable before any workload is spawned.

**Why this priority**: An agent that starts without a reachable model will fail silently or attempt remote fallback. The gate prevents this class of failure.

**Independent Test**: Initialise with `--inference llama-cpp` but do not place a socket file; run `microjail run -- opencode run "..."` and verify the command exits non-zero naming the missing inference socket.

**Acceptance Scenarios**:

1. **Given** `--inference llama-cpp` was set at init and the UDS socket file is present and accepting connections, **When** `microjail run` evaluates the inference gate, **Then** the gate passes and the workload proceeds.

2. **Given** `--inference llama-cpp` was set at init but the socket file is absent, **When** `microjail run` evaluates the inference gate, **Then** the gate fails with a message naming the expected socket path.

3. **Given** no `--inference` flag was set at init, **When** `microjail run` evaluates gates, **Then** the inference gate is skipped entirely.

---

### Edge Cases

- What happens when the LXD container is not running when `microjail lock` or `microjail run` is called? The command MUST exit non-zero, name the container, and advise the user to check the environment status.
- What happens when the lock operation itself fails (e.g., `lxc` call errors)? The command MUST exit non-zero before running any gates or spawning the workload.
- What happens when the workload command is empty (e.g., `microjail run --`)? The command MUST exit non-zero with a clear error before any locking occurs.
- What happens when the workspace mount check fails (expected path not bind-mounted)? The command MUST exit non-zero, name the missing mount, restore egress, and not start the workload.
- What happens when the state file readonly gate fails (state file is writable from inside the container)? The command MUST exit non-zero naming the gate, restore egress, and not start the workload.
- What happens when `microjail lock` or `microjail run` is called on an environment that is already locked (e.g., a previous run was interrupted and did not unlock)? Both commands MUST detect this via the state file and handle it without double-locking: `lock` exits zero with an informational message; `run` proceeds to gate checks and spawns the workload.

## Requirements *(mandatory)*

### Functional Requirements

**`microjail lock`**

- **FR-001**: `microjail lock` MUST read `.microjail/state.json` from the workspace to determine the environment name and intent flags before taking any action.
- **FR-002**: `microjail lock` MUST cut network egress on the named LXD container.
- **FR-003**: `microjail lock` MUST verify that egress is actually down (not merely requested) by probing from inside the container to an external destination and confirming it is unreachable.
- **FR-004**: `microjail lock` MUST verify that the workspace directory is bind-mounted inside the container at the expected path.
- **FR-005**: `microjail lock` MUST verify that the OpenCode config file (`opencode.jsonc`) in the workspace is not writable by the workload, when `--agent opencode` was set at init.
- **FR-005a**: `microjail lock` MUST verify that `.microjail/state.json` is protected against writes from inside the container. The protection mechanism is a `readonly=true` LXD device that bind-mounts the state file over the workspace's mutable mount, added to the container at lock time by microjail. The gate verifies that this readonly device is present and active by inspecting `lxc config device show <container>` and confirming the device entry exists with `readonly=true`. The gate is unconditional — it applies regardless of intent flags.
- **FR-006**: When `--inference llama-cpp` was set at init, `microjail lock` MUST verify that the UDS socket file recorded in state exists and is reachable.
- **FR-007**: If any gate fails after egress has been severed, `microjail lock` MUST restore egress before exiting, to avoid leaving the container in an inconsistent partially-locked state.
- **FR-008**: `microjail lock` MUST exit non-zero and name the failing gate if any gate check does not pass.
- **FR-009**: `microjail lock` MUST update the locked flag in `.microjail/state.json` when locking succeeds.
- **FR-010**: `microjail lock` MUST be idempotent: calling it on an already-locked environment (state records locked) MUST exit zero with an informational message, skipping re-lock.

**`microjail unlock`**

- **FR-011**: `microjail unlock` MUST read `.microjail/state.json` to identify the environment name.
- **FR-012**: `microjail unlock` MUST restore network egress to the named LXD container.
- **FR-013**: `microjail unlock` MUST update the locked flag in `.microjail/state.json` to reflect the unlocked state.
- **FR-014**: `microjail unlock` MUST be idempotent: calling it on an already-unlocked environment MUST succeed (exit zero) with an informational message.

**`microjail run`**

- **FR-015**: `microjail run` MUST accept a `--` separator followed by one or more command tokens as the workload to execute; an empty workload MUST cause a non-zero exit before locking.
- **FR-016**: `microjail run` MUST delegate to the same locking logic as `microjail lock` (not reimplement it) before spawning the workload.
- **FR-017**: `microjail run` MUST NOT spawn the workload if locking or any gate fails; it MUST exit non-zero and name the cause.
- **FR-018**: `microjail run` MUST spawn the workload inside the LXD container and exit with the workload's exit code when all gates pass.
- **FR-019**: `microjail run` MUST update the locked flag in `.microjail/state.json` after the workload exits (returning to unlocked).

**All commands**

- **FR-020**: All three commands MUST exit non-zero with a human-readable message if no state file is found in the workspace.

**`microjail run` — audit log**

- **FR-021**: Every `microjail run` invocation MUST append a log entry to `.microjail/run-log.jsonl` in the workspace directory recording: the workload command tokens, UTC start time, gate results (name + pass/fail for each gate evaluated), and the workload's exit code. The log entry MUST be written after the workload exits. The log file MUST be retained after `microjail unlock` and MUST NOT be cleared or rotated by any microjail command.

### Key Entities

- **Lock state**: A boolean flag in `.microjail/state.json` recording whether the environment's egress is currently severed. Set to true by `lock` (and by `run` via `lock`); set to false by `unlock` (and by `run` after the workload exits). The file MUST be readonly from inside the container while the environment is locked.
- **Lock gate**: A single pre-flight check that must pass before the workload is spawned. Each gate has a name, a pass/fail result, and a human-readable failure message.
- **`microjail lock`**: Standalone command that severs egress and runs all lock gates without spawning a workload. The locking logic in `microjail run` delegates to this same implementation.
- **Workload**: The command tokens passed after `--` to `microjail run`. Executed inside the container; its exit code becomes the exit code of `microjail run`.
- **Egress**: The container's ability to send packets to destinations outside the LXD network. Severed at lock; restored at unlock.
- **Run log** (`.microjail/run-log.jsonl`): Append-only JSONL file in the workspace directory. Each line is one `run` invocation record: workload command, start time, gate results, exit code. Persists across lock/unlock cycles; never cleared by microjail.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer can run `microjail run -- <command>` and have the workload execute inside a network-isolated container in under 10 seconds of overhead (excluding workload runtime) on a local machine with a running LXD instance.
- **SC-002**: Every lock gate failure produces a human-readable error message that names the failing gate and the remediation step; zero ambiguous failures.
- **SC-003**: Running `microjail unlock` after any `microjail run` (including interrupted runs) always restores networking; the unlocked state is verifiable by running a network probe from inside the container.
- **SC-004**: A developer unfamiliar with the tool can understand all `microjail run` and `microjail unlock` options from `--help` alone.
- **SC-005**: No workload has ever been spawned when any gate failed, across all test scenarios.

## Assumptions

- The workspace directory is the current working directory at invocation time; no `--workspace` flag is introduced by this feature.
- Network egress is controlled via LXD ACLs or `lxc config device` manipulation on the container; microjail does not need to manage iptables on the host directly.
- The workload is executed inside the container using `workshop exec` or an equivalent subprocess call; process isolation is provided by LXD, not by microjail.
- The egress probe used in gate FR-004 targets a well-known external IP (e.g., `8.8.8.8`) and uses a short timeout; the specific probe method is an implementation detail.
- Config readonly gate (FR-006) checks filesystem permissions on the config file from the host side; it does not require entering the container.
- The `unlock` command does not automatically re-run after every `run`; the user is expected to call it explicitly when they want egress restored.
- Multiple concurrent `microjail run` invocations against the same environment are out of scope; behaviour is undefined if two processes race.
- The unlock mechanism is the symmetric inverse of the lock mechanism; if lock uses LXD ACLs, unlock removes the same ACL entries.
