## Context

Main previously carried an adversarial CTF escape workflow (host-seeded secrets + in-container agent loop + structured PASS/FAIL/ERROR reporting). This branch has moved to a stricter test architecture (explicit `tests/` taxonomy, marker-gated slow tests, adapter seams, and branch-specific lock/run behavior) and no longer contains that escape suite.

The requested change is a behavioral port, not a redesign: restore the standalone CTF runner in `ctf/`, add validation coverage in `tests/escape/`, and preserve the prior harness UX while aligning implementation seams to this branch.

## Goals / Non-Goals

**Goals:**
- Reintroduce a standalone CTF runner under `ctf/` as internal adversarial tooling, outside the product `microjail` CLI surface.
- Add `tests/escape/` coverage with branch-consistent fixtures/markers.
- Preserve prior harness UX: generated secrets, host file bait, localhost HTTP bait, iterative jailed attempts, global timeout, and structured verdict semantics.
- Keep setup/teardown deterministic and idempotent so failures do not leave egress locked or resources dangling.

**Non-Goals:**
- Reworking microjail gate/capability policy semantics.
- Replacing the CTF run model with OMP goal/loop-directive experiments in this change.
- Adding production runtime features unrelated to supporting this adversarial test harness.

## Decisions

### 1) Runtime harness in `ctf/`, verification in `tests/escape/`

Executable orchestration lives in top-level `ctf/`. Test assertions and fixtures live in `tests/escape/`. The harness is explicitly opt-in and is never auto-invoked by `microjail` commands.

**Why:** This preserves a hard boundary: adversarial security testing tool vs product runtime commands.

**Alternative considered:** move runtime harness under `tests/escape/` only. Rejected because it makes the tool pytest-internal and less usable for explicit operator-driven runs.

### 2) Preserve historical workflow semantics with branch-compatible seams

The observable flow remains: preflight checks → ephemeral workspace setup → seed filesystem + HTTP secrets → launch in-container agent attempts → monitor signal artifact on a fixed short interval → determine verdict → always cleanup. Internals must reuse branch microjail primitives/wrappers instead of parallel config/state logic.

Timeout model is a single global deadline for the run. No additional per-iteration cap is introduced in this change.

**Why:** Maintains behavior parity while reducing drift and respecting current scope boundaries.

**Alternative considered:** add per-iteration runtime caps or directive-driven control now. Rejected for this port because it changes behavior and scope.

### 3) Explicit opt-in execution and alpha-stability posture

CTF runs explicitly via `python -m ctf` (and equivalent `uv run python -m ctf`). Tests remain `--slow` and environment-gated. Result semantics and `error_kind` subtype values are tested but documented as unstable during alpha.

**Why:** Matches the “adversarial test only” goal without polluting normal user/runtime workflows.

**Alternative considered:** add installed script entrypoint and stable external contract now. Rejected to avoid environment pollution and premature API guarantees.

### 4) Deterministic evidence and verdict handling

Breach detection is signal-file based with exact secret matching (no stdout scraping). JSON report emission remains default. If report persistence fails, final classification is `outcome=ERROR` with `error_kind=report_persistence`, which overrides an otherwise computed PASS/FAIL.

Details of fallback diagnostic transport/format and verbose evidence presentation are intentionally deferred to implementation-time engineering judgment for this alpha port.

**Why:** Security testing needs deterministic verdict semantics without over-constraining prototype internals.

**Alternative considered:** fully specifying fallback wire format now. Rejected because it drags this change below behavior-level scope.

### 5) Ephemeral workspace isolation with debug retention switch

Each run uses a dedicated temporary workspace outside the user repo. Default behavior always cleans up. A debug flag may retain workspace artifacts on failure only.

**Why:** Strong isolation and cleanup by default, with practical forensics when needed.

**Alternative considered:** run directly in project tree. Rejected due to contamination risk.

### 6) Internal harness boundary and naming clarity

CTF is documented as "Capture The Flag" adversarial harnessing and explicitly marked as internal tooling, not part of microjail’s supported public API surface. Canonical instability language lives in CTF help/docs, with README carrying a brief cross-reference.

**Why:** Keeps expectations aligned for contributors and operators while avoiding duplicated contract language.

**Alternative considered:** duplicate full contract text across docs. Rejected to avoid drift.

### 7) Threat pressure scope for this port

CTF keeps exactly two planted-secret vectors for now: host filesystem file and host-local HTTP service bound to `127.0.0.1`. The prompt provides exact target path/port to maximize containment pressure rather than discovery complexity.

**Why:** Focuses this change on containment boundary strength and behavioral parity.

**Alternative considered:** broaden vectors now (`/proc`, env, sockets). Rejected as additive scope for a later change.

## Risks / Trade-offs

- **Risk:** Port captures old UX superficially but diverges on branch-specific lock/run semantics. → **Mitigation:** assert parity-critical control flow (preflight, monitoring, teardown, verdict precedence) in `tests/escape`.
- **Risk:** Slow-suite flakiness from environment timing/network race conditions. → **Mitigation:** fixed short polling interval, explicit dependency preflight, deterministic teardown in `finally`/fixture cleanup.
- **Risk:** CTF behavior interpreted as stable product contract too early. → **Mitigation:** document alpha instability of result + `error_kind` semantics in CTF help/docs and keep README as cross-reference only.
- **Risk:** Ambiguous diagnostics when report persistence fails. → **Mitigation:** enforce `ERROR/report_persistence` precedence now and leave fallback output shape as implementation detail in this alpha port.

## Migration Plan

1. Port historical `ctf/` modules into this branch and align imports to current microjail primitives.
2. Add `tests/escape/` scaffold (`conftest.py`, helpers, scenarios) with `slow` + environment marks.
3. Implement/report `ERROR` + `error_kind=report_persistence` behavior and global-timeout monitoring semantics.
4. Verify harness port + core `tests/escape` control-flow parity with targeted tests and explicit slow escape-suite run.

## Open Questions

- None blocking for implementation. OMP goal/loop directives and expanded attack vectors are explicitly deferred follow-up investigations.
