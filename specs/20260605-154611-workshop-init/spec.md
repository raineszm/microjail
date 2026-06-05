# Feature Specification: Thin-Wrapper Init with Lazy Container Launch

**Feature Branch**: `20260605-154611-workshop-init`

**Created**: 2026-06-05

**Status**: Draft

**Input**: User description: "Refactor to make microjail init as thin a wrapper around workshop init as possible while still upholding guarantees. Furthermore try to defer actually spinning up the container with workshop launch until we need it to exist (for run or lock)"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Configure environment without waiting for container creation (Priority: P1)

A developer runs `microjail init <name>` to configure a new jailed environment. Today this blocks until a container is fully provisioned by Workshop, which can take tens of seconds. After this change, `init` only writes configuration files and state metadata; it exits immediately without touching Workshop or LXD. The developer inspects the generated files, confirms they are correct, and carries on. The container is created on-demand the first time `microjail lock` or `microjail run` is invoked.

**Why this priority**: The longest-wait part of the current `init` flow is the container provisioning. Decoupling file setup from container creation makes `init` near-instant, enables offline configuration review, and removes a failure class (network/LXD availability) from the initialisation path. All other stories depend on this new lifecycle model.

**Independent Test**: Run `microjail init <name>`, confirm exit 0 and the three artefact files exist, then confirm `workshop info <name>` exits non-zero (container not yet present).

**Acceptance Scenarios**:

1. **Given** a writable workspace with no existing state, **When** `microjail init <name>` runs, **Then** it exits 0, writes `.workshop/<name>.yaml`, writes `.microjail/state.json` with `launched=false, locked=false`, and does not invoke `workshop launch` or any LXD command.
2. **Given** a workspace where `microjail init <name>` has completed, **When** `workshop info <name>` is queried, **Then** it exits non-zero, confirming no container was created.
3. **Given** a workspace where `microjail init <name>` has completed, **When** a second `microjail init <name>` is invoked (without `--force`), **Then** it exits 2 with an "already exists" message, based on the presence of the local state file — not on Workshop's container registry.

---

### User Story 2 — First lock or run transparently launches the container (Priority: P1)

A developer runs `microjail lock` or `microjail run` in a workspace that has been configured but whose container has not yet been created. The command transparently provisions the container at that point — verifying it exists afterwards — and then proceeds with the lock or run operation as today. The developer sees no extra step; the container launch is an invisible part of the lock/run flow.

**Why this priority**: This is the other half of deferred launch — the point at which the invariant "container must exist before egress mutation or workload execution" is re-established.

**Independent Test**: Run `microjail init <name>`, confirm `workshop info` exits non-zero, then run `microjail lock`; confirm exit 0, `workshop info` exits 0, and `.microjail/state.json` records `launched=true, locked=true`.

**Acceptance Scenarios**:

1. **Given** a configured-not-launched workspace (`launched=false`), **When** `microjail lock` runs, **Then** it calls `workshop launch`, verifies the environment exists, then proceeds with the normal lock sequence; exits 0 on success with `launched=true, locked=true` persisted.
2. **Given** a configured-not-launched workspace, **When** `microjail run <cmd>` runs, **Then** it calls `workshop launch`, verifies, locks, executes the workload, unlocks; state is `launched=true, locked=false` after success.
3. **Given** a workspace with `launched=true, locked=false` (previously locked or run), **When** `microjail lock` runs again, **Then** it does NOT call `workshop launch` again; it proceeds directly to lock.
4. **Given** a configured-not-launched inference workspace, **When** `microjail lock` or `run` triggers lazy launch, **Then** after `workshop launch` succeeds the inference tunnel is connected via `workshop connect` before any gate checks run.

---

### User Story 3 — `--force` reinitialises correctly for both lifecycle states (Priority: P2)

A developer changes configuration options and runs `microjail init <name> --force` to update the environment definition. If the container has never been launched, `--force` simply overwrites the local config and state files without touching Workshop. If the container already exists (`launched=true`), `--force` rewrites the local files and then runs `workshop refresh` to apply the updated definition to the live container, reconnecting the inference tunnel if needed.

**Why this priority**: `--force` is the primary re-initialisation path. Its behaviour must be correct and predictable across both lifecycle states, and it must not attempt `refresh` on a container that does not exist.

**Independent Test**: (a) Run `init`, confirm not-launched, then `init --force --inference llama-cpp --agent opencode`; confirm exit 0, files updated, `workshop info` still non-zero. (b) Run `init`, `lock`, then `init --force`; confirm `workshop refresh` was called, env still present.

**Acceptance Scenarios**:

1. **Given** `launched=false`, **When** `microjail init <name> --force` runs, **Then** it overwrites `.workshop/<name>.yaml`, `opencode.jsonc` (if applicable), and `.microjail/state.json`, does NOT call `workshop refresh` or `workshop launch`, and exits 0.
2. **Given** `launched=true, locked=false`, **When** `microjail init <name> --force` runs, **Then** it overwrites local config files, calls `workshop refresh`, verifies the environment still exists, reconnects the inference tunnel if inference is configured, and exits 0 with `launched=true, locked=false` in state.
3. **Given** `launched=true, locked=true`, **When** `microjail init <name> --force` runs, **Then** it exits 2 with a message instructing the user to run `microjail unlock` first. Rationale: Workshop refresh against a container whose LXD network devices and readonly state mount have been mutated by `lock_egress` is undefined territory; requiring the user to unlock first keeps `init --force` operating only on a quiescent environment.

---

### User Story 4 — `microjail init` is visibly simpler (Priority: P3)

A developer reading `src/microjail/commands/init.py` can understand its responsibility at a glance: validate inputs, write config files, write state. All Workshop subprocess interaction lives in `wrappers/workshop.py`. No workshop-specific logic (prerequisites check, environment existence check) is duplicated in `commands/init.py`.

**Why this priority**: Structural clarity. After this refactor, the module boundary between `commands/` (CLI orchestration) and `wrappers/` (external process calls) becomes sharp and testable in isolation.

**Independent Test**: Count the external subprocess calls triggered through the normal (non-`--force`) `microjail init` path; that count must be zero.

**Acceptance Scenarios**:

1. **Given** a normal `microjail init` invocation (no `--force`), **When** the command runs, **Then** zero calls are made to `workshop` or `lxc` subprocesses.
2. **Given** a source audit of `commands/init.py`, **When** the module is inspected, **Then** it contains no direct `check_prerequisites()` call and no `workshop.environment_exists()` call on the non-`--force` path.

---

### Edge Cases

- What happens when `microjail lock` triggers lazy launch but `workshop launch` exits non-zero? The lock exits 3, `launched` stays `false`, `locked` stays `false`; the user can retry.
- What happens when `workshop launch` succeeds but `workshop verify_exists` fails? The lock exits 3; `launched` stays `false` to prevent a "launch succeeded" assumption from propagating.
- What happens when the container is stopped externally (e.g. `workshop stop`, host reboot) after `launched=true` is persisted? The command exits 3 with a clear error message (e.g. "Environment `<name>` could not be verified — it may have been stopped or removed externally. Run `workshop start <name>` to restore it, or `microjail init --force` to reinitialise."). Automatic recovery is out of scope; `launched` stays `true` because the container was not removed, only stopped.
- What if `workshop connect` for the inference tunnel fails after lazy launch succeeds? The lock exits 3, `launched` is persisted as `true` (the container exists), `locked` stays `false`; a subsequent `lock` retries the tunnel connection without re-launching.
- What if `microjail init` is run without `--force` in a workspace that has a stale `state.json` from an environment that has been manually removed from Workshop? The duplicate detection is based on the local `state.json` presence, so init exits 2 with "already exists". The user must remove `.microjail/state.json` manually or use `--force`.
- What happens when `init --force` is used on a `launched=true` environment with a changed `name` parameter? Same-name reinitialisation is the only supported contract. The `name` in the new config is always used as-is to write `.workshop/<name>.yaml`; no renaming of an existing Workshop environment is attempted. If the new name differs from the old name in `state.json`, that is treated as a fresh configuration (no Workshop call).

## Clarifications

### Session 2026-06-05

- Q: Should `microjail init --force` be blocked, silently proceed, or use a different policy when `state.locked=true`? → A: Exit 2 with a message directing the user to run `microjail unlock` first. No Workshop call is attempted on a locked environment.
- Q: When a container is externally stopped after `launched=true` is persisted, should `lock`/`run` attempt automatic restart or fail loudly? → A: Fail with a clear, actionable error message (name the specific recovery command); no automatic restart. `launched` remains `true`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `microjail init` MUST complete without invoking any `workshop` or `lxc` subprocess on the normal (non-`--force`-refresh) path.
- **FR-002**: `microjail init` MUST write `.workshop/<name>.yaml` (and optionally `sdk.yaml`, `opencode.jsonc`) before writing `.microjail/state.json`, preserving the existing file-writing order.
- **FR-003**: `.microjail/state.json` written by `microjail init` MUST include `launched: false` and `locked: false`.
- **FR-004**: `microjail init` MUST validate `name` format (`^[a-zA-Z][a-zA-Z0-9-]*$`, max 63 chars) and `--inference-url` (scheme + host) before any filesystem I/O.
- **FR-005**: `microjail init` MUST reject a second invocation (without `--force`) in the same workspace by detecting the presence of `.microjail/state.json` — independent of whether a Workshop container exists.
- **FR-006**: `microjail init` MUST check workspace writability before writing any files.
- **FR-007**: `microjail lock` and `microjail run` MUST each call `workshop launch` (and subsequently `workshop verify_exists`) before any LXD egress mutation when `state.launched` is `false`.
- **FR-008**: After a successful lazy launch, `state.launched` MUST be persisted as `true` before any LXD egress mutation occurs, so a crash between launch and lock leaves the state truthful.
- **FR-009**: When `state.inference` is set and a lazy launch is triggered, the inference tunnel MUST be connected via `workshop connect` after `verify_exists` succeeds and before `lock_egress` is called.
- **FR-010**: `microjail lock` and `microjail run` MUST NOT call `workshop launch` when `state.launched` is `true`.
- **FR-011**: `microjail init --force` on a workspace where `state.launched` is `false` MUST overwrite local config files and state without invoking `workshop launch` or `workshop refresh`.
- **FR-012**: `microjail init --force` on a workspace where `state.launched` is `true` MUST call `workshop refresh`, then `workshop verify_exists`, then reconnect the inference tunnel if inference is configured; it MUST NOT call `workshop launch`.
- **FR-013**: `workshop.check_prerequisites()` MUST be called by the lazy-launch path in `lock`/`run` (and by `init --force` when refreshing a launched env), not by the normal `init` path.
- **FR-014**: Existing exit codes MUST be preserved: 0 (success), 2 (pre-flight rejection), 3 (I/O or Workshop/LXD runtime error).
- **FR-015**: `microjail unlock` MUST leave `state.launched` unchanged (it only modifies `locked`).
- **FR-016**: The `State` struct MUST gain a `launched` boolean field that defaults to `true` (for backward compatibility with existing state files written before this change, which were always written after a successful launch).
- **FR-017**: `microjail init --force` MUST exit 2 with an actionable error message when `state.locked=true`; it MUST NOT attempt `workshop refresh` or any LXD call in that state.

### Key Entities

- **State**: `.microjail/state.json` — the persisted record of environment intent and lifecycle. Gains `launched: bool` (default `true` for deserialization compatibility). Valid combinations: `{launched=false, locked=false}` (configured), `{launched=true, locked=false}` (ready), `{launched=true, locked=true}` (running locked). The combination `{launched=false, locked=true}` MUST NOT occur.
- **EnvironmentConfig**: In-memory only; unchanged. Carries user intent from CLI arguments to config generators. Never persisted.
- **Workshop environment**: The LXD container managed by Workshop. Lifecycle is now independent of `init`; it is created by `lock`/`run` on demand.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `microjail init <name>` completes in under 2 seconds on a standard development machine (compared to the current 30–90 seconds for container provisioning).
- **SC-002**: Zero Workshop or LXD subprocess calls are made during normal `microjail init` execution (verifiable via unit test mock inspection).
- **SC-003**: All existing integration tests whose assertions are not directly invalidated by the deferred-launch design continue to pass without modification of their assertion logic. The two tests asserting `workshop info` exits 0 immediately after `init` are replaced with semantically equivalent tests asserting the same outcome after `microjail lock`; all other assertion logic is unchanged. Only fixture setup (adding a post-init launch step) may change.
- **SC-004**: The lazy-launch path in `lock` and `run` is covered by both unit tests (mocked wrappers, ordered call verification) and integration tests (live container created on first `lock`/`run`).
- **SC-005**: `commands/init.py` contains no direct calls to `workshop.check_prerequisites()` or `workshop.environment_exists()` on the non-`--force`-refresh code path.
- **SC-006**: `state.launched` persisted as `true` before any LXD call in the lazy-launch path (verified by unit test asserting call order).

## Assumptions

- `workshop launch` is idempotent enough that re-running it on a container Workshop believes does not exist is safe. If a container was stopped externally and Workshop considers it Stopped (not Absent), `workshop launch` may fail — this is acceptable; the error surfaces cleanly and `launched` stays `false`.
- Same-name reinitialisation is the only supported `--force` contract; rename of the Workshop environment is out of scope.
- `microjail init --force` on a `locked=true` environment is rejected with exit 2; the user must run `microjail unlock` first.
- The inference tunnel connection made by `workshop connect` is not persistent across container restarts; it must be re-established on every lazy launch. This is existing behaviour preserved, not new.
- Python `msgspec` deserialization of `launched` absent from an old `state.json` will use the field default (`true`) without raising, matching the `locked` field precedent.
