# CLI Command Contracts: Thin-Wrapper Init with Lazy Container Launch

**Feature**: `specs/20260605-154611-workshop-init/spec.md`
**Date**: 2026-06-05

These contracts describe the observable behaviour of each affected CLI command — exit codes, output messages, side-effects (file writes, subprocess calls) — as a testable reference.

---

## `microjail init <name> [--inference ...] [--agent ...] [--inference-url ...] [--force]`

### Normal path (no `--force`, no existing state)

**Preconditions**: `.microjail/state.json` does not exist; `.workshop/<name>.yaml` does not exist; workspace is writable.

**Side-effects (in order)**:
1. Validate `name` (regex + length) — exit 2 if invalid
2. Validate `--inference-url` if provided — exit 2 if malformed
3. Check workspace writability — exit 2 if not writable
4. Check `.microjail/state.json` absent — exit 2 with "already exists" if present
5. Check `.workshop/<name>.yaml` absent — exit 2 if present
6. Check `opencode.jsonc` absent (only when `--agent opencode`) — exit 2 if present
7. Write `.workshop/<name>.yaml`
8. Write `.workshop/local-inference/sdk.yaml` (only when `--inference` set)
9. Write `opencode.jsonc` (only when `--agent opencode`)
10. Write `.microjail/state.json` with `launched=false, locked=false`
11. Print success summary (file paths)

**Zero subprocess calls** to `workshop` or `lxc`. Exit 0.

**Exit codes**: 0 success, 2 pre-flight rejection, 3 I/O error on file write.

---

### `--force` on unconfigured workspace (no existing state)

Identical to normal path — `--force` has no special effect when no state exists.

---

### `--force` on `launched=false` (state exists but container not yet created)

**Preconditions**: `.microjail/state.json` exists with `launched=false`; workspace writable.

**Side-effects (in order)**:
1. Validate inputs as above
2. Check workspace writability
3. Read `.microjail/state.json`, detect `launched=false`
4. Overwrite `.workshop/<name>.yaml`, `sdk.yaml` (if applicable), `opencode.jsonc` (if applicable)
5. Overwrite `.microjail/state.json` with `launched=false, locked=false`

**Zero subprocess calls** to `workshop` or `lxc`. Exit 0.

---

### `--force` on `launched=true, locked=false`

**Preconditions**: `.microjail/state.json` exists with `launched=true, locked=false`; workspace writable; `workshop` and `lxc` on PATH and functional.

**Side-effects (in order)**:
1. Validate inputs as above
2. Check workspace writability
3. Read `.microjail/state.json`, detect `launched=true, locked=false`
4. Overwrite local config files (`.workshop/<name>.yaml`, `sdk.yaml`, `opencode.jsonc`)
5. Call `workshop.check_prerequisites()` — exit 3 if prerequisites missing
6. Call `workshop refresh <name> --project <workspace>` — exit 3 if refresh fails
7. Call `workshop info <name> --project <workspace>` — exit 3 if environment not found
8. Call `workshop connect <name>/local-inference:llama <name>/system:llama --project <workspace>` (only when `--inference` set) — exit 3 if connect fails
9. Overwrite `.microjail/state.json` with `launched=true, locked=false`
10. Print success summary

Exit 0 on success.

---

### `--force` on `launched=true, locked=true`

**Preconditions**: `.microjail/state.json` exists with `launched=true, locked=true`.

**Side-effects**: Read state.json only. No file writes. No subprocess calls.

**Output**: `"Error: Environment '<name>' is currently locked. Run 'microjail unlock' first."` to stderr.

**Exit code**: 2.

---

## `microjail lock`

### When `state.launched=false` (lazy launch path)

**Preconditions**: `.microjail/state.json` with `launched=false, locked=false`; `workshop` and `lxc` on PATH.

**Side-effects (in order)**:
1. Load state
2. Confirm `state.locked=false` (idempotency check — not applicable here)
3. Call `workshop.check_prerequisites()`
4. Call `workshop launch <name> --project <workspace>` — exit 3 if fails; `launched` stays `false`
5. Call `workshop info <name> --project <workspace>` (verify_exists) — exit 3 if fails; `launched` stays `false`
6. Persist `state.launched=true` to `state.json` (before any LXD mutation)
7. Call `workshop connect` for inference tunnel (only when `state.inference` set) — exit 3 if fails; `launched` stays `true`, `locked` stays `false`
8. Call `lock_egress(state.name, workspace)` — exit 3 on failure (egress not severed)
9. Run all gates — exit 3 on gate failure; egress is restored before exit
10. Persist `state.locked=true`
11. Print: `"Environment '<name>' locked. All gates passed."`

Exit 0 on success.

**Step 6 is critical**: `launched=true` must be written before step 8 so that if the process crashes between steps 6 and 8, subsequent calls know the container exists and skip the launch step.

---

### When `state.launched=true` (normal path, no change)

No call to `workshop.check_prerequisites()`, `launch`, `verify_exists`, or `connect`. Proceeds directly to `lock_egress` as today.

---

### When `state.locked=true` (idempotent)

No change from current behavior. Exit 0 with informational message.

---

## `microjail run [-- <cmd>]`

### When `state.launched=false`

Passes through `perform_lock` which handles lazy launch (same as `microjail lock` lazy path above, steps 3–10). After lock succeeds, spawns workload via `workshop exec`. On workload exit, calls `unlock_after_run` which sets `locked=false` and dumps state. Final state: `launched=true, locked=false`.

### When `state.launched=true`

No change from current behavior.

---

## `microjail unlock`

**No change**. Does not modify `state.launched`. Always leaves `launched` at its current value. Sets `locked=false`.

---

## Subprocess call matrix (summary)

| Command / Condition | `check_prereqs` | `launch` | `refresh` | `verify_exists` | `connect` | `lock_egress` |
|---|---|---|---|---|---|---|
| `init` (normal) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `init --force` (launched=false) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `init --force` (launched=true) | ✓ | ✗ | ✓ | ✓ | ✓ (if inference) | ✗ |
| `init --force` (locked=true) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `lock` (launched=false) | ✓ | ✓ | ✗ | ✓ | ✓ (if inference) | ✓ |
| `lock` (launched=true) | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `run` (launched=false) | ✓ | ✓ | ✗ | ✓ | ✓ (if inference) | ✓ |
| `run` (launched=true) | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `unlock` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
