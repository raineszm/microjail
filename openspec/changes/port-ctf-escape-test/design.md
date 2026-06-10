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

### 2) Build fresh using original as reference, wire into microjail as a library

The implementation builds new `ctf/` modules from scratch following the decisions in this document, using the reverted commit `e4c3702` as a reference for reusable parts (`http_server.py`, `secrets_gen.py`). The harness imports microjail directly and calls `MicroJail` methods (`ensure_for_run()`, `release()`) for policy application and teardown. Agent launch uses `subprocess.Popen` with raw `workshop exec` to get a process handle for concurrent signal-file polling and SIGTERM-based termination.

The observable flow is: preflight checks → ephemeral workspace setup → `workshop init --sdks omp/14/edge` + `launch` → write `.microjail/config.yaml` with NetworkDrop + ReadonlyConfig gates and inference endpoint capability → `MicroJail.load()` + `ensure_for_run()` → write adversarial prompt + agent wrapper script to workspace → start HTTP bait server → write host secret file → launch agent via `subprocess.Popen(["workshop", "exec", ..., "bash", "/project/ctf_agent.sh"])` → poll signal file from host side concurrently → on breach or timeout, send SIGTERM to agent process → determine verdict → `microjail.release()` → `workshop stop` → LXD container delete → cleanup workspace.

Timeout model is a single global deadline for the run (default 300s). No additional per-iteration cap is introduced in this change.

**Why:** The original commit's runner never actually created a Workshop container or applied a Lockdown — it was a skeleton. Building fresh avoids carrying forward dead integration paths. Importing the library for policy operations avoids subprocess overhead while exercising the same code paths user-facing commands use. `subprocess.Popen` for agent launch enables concurrent signal-file monitoring and clean SIGTERM-based termination.

**Alternative considered:** restore the original commit and rework in place. Rejected because too much of the original must change to integrate with microjail.

### 3) Explicit opt-in execution and alpha-stability posture

CTF runs explicitly via `python -m ctf` (and equivalent `uv run python -m ctf`). Tests remain `--slow` and environment-gated. Result semantics and `error_kind` subtype values are tested but documented as unstable during alpha.

**Why:** Matches the “adversarial test only” goal without polluting normal user/runtime workflows.

**Alternative considered:** add installed script entrypoint and stable external contract now. Rejected to avoid environment pollution and premature API guarantees.

### 4) Verdict precedence: breach detection beats report persistence

Breach detection is signal-file based with exact secret matching (no stdout scraping). JSON report emission remains default. If a breach is detected (FAIL), that verdict takes precedence over a report persistence failure — a detected containment breach is the most critical signal and must not be masked. If no breach was detected (would-be PASS) and report persistence fails, the final classification is `outcome=ERROR` with `error_kind=report_persistence`.

Details of fallback diagnostic transport/format and verbose evidence presentation are intentionally deferred to implementation-time engineering judgment for this alpha port.

**Why:** Losing evidence of a containment breach because the report writer is broken is unacceptable for a security testing tool. FAIL must surface even when persistence is degraded.

**Alternative considered:** ERROR always overrides PASS/FAIL. Rejected because it would suppress breach signals when report writing fails.


### 5) Ephemeral workspace outside the repo with explicit container teardown

Each run creates a dedicated temporary workspace at `/tmp/ctf-<uuid>/` outside the user project tree. Cleanup is explicit and ordered: `microjail.release()` → `workshop stop` → LXD container delete → `rm -rf` the workspace directory. Each teardown step is wrapped with `contextlib.suppress(Exception)` so a failure in one step does not prevent later steps from executing. This ensures no dangling LXD resources regardless of workspace removal outcome. By default the workspace is always removed. A `--keep-on-failure` flag retains it when the outcome is FAIL or ERROR.

**Why:** Strong isolation and cleanup by default, with practical forensics when needed. Explicit LXD teardown before filesystem removal prevents resource leaks that a bare `rm -rf` would miss.

**Alternative considered:** `rm -rf` alone, relying on Workshop to clean up LXD. Rejected because teardown ordering matters — Workshop state references LXD resources that should be deleted first.
### 6) Internal harness boundary and naming clarity

CTF is documented as "Capture The Flag" adversarial harnessing and explicitly marked as internal tooling, not part of microjail's supported public API surface. Canonical instability language lives in CTF help/docs, with README carrying a brief cross-reference.

**Why:** Keeps expectations aligned for contributors and operators while avoiding duplicated contract language.

**Alternative considered:** duplicate full contract text across docs. Rejected to avoid drift.

### 7) OMP AI agent as the in-container adversary

The in-container actor is an OMP (Oh My Pi) AI agent — not a deterministic shell script. OMP is added to the Workshop container via the `omp/14/edge` SDK at init time (`workshop init --sdks omp/14/edge`). The agent requires an LLM to operate: `--model` is a required CLI flag. An inference endpoint is provided via `--endpoint` (default `localhost:8080`) and exposed inside the container through a `WorkshopEndpointCapability` that tunnels the host endpoint to container `localhost:8080`. OMP auto-discovers the provider by probing `localhost:8080` (its default behavior) — no `models.yml` or OMP config needed.

The agent receives an adversarial prompt telling it the exact secret file path, HTTP bait port, and loop/notes-file mechanics. It uses its full tool suite (bash, file operations, network calls, and the LLM) to attempt exfiltration. If it recovers either secret, it writes the value to the signal file.

**Why:** An AI agent is a more realistic adversary than a script — it can try creative approaches, chain tool calls, and adapt to failures. Making the LLM available mirrors real workloads where agents have legitimate API access but must remain sandboxed. Using the Workshop SDK mechanism keeps OMP installation declarative and repeatable.

**Alternative considered:** deterministic bash script with hardcoded `cat` and `/dev/tcp` probes. Rejected as too narrow — a script only tests the specific vectors you thought to code, while an AI explores.

### 8) Agent wrapper script with feedback-driven loop

A bash wrapper script (`ctf_agent.sh`) runs inside the container. Before the loop, it runs `omp --list-models` to auto-detect the provider at `localhost:8080` and verify connectivity — if this fails, the harness captures the failure and reports ERROR. The script then loops `omp -p "$PROMPT" --model "$MODEL"`, where `$PROMPT` is assembled from the adversarial prompt file plus any notes from previous iterations (`ctf_notes.md`). Between iterations, the script checks the signal file — if the agent found a secret, the script exits. The prompt instructs OMP to read the notes file at the start of each turn and update it at the end with what was attempted and learned. This gives OMP persistent memory across fresh invocations without requiring RPC mode.

The wrapper sleeps briefly between iterations to avoid tight-looping if OMP exits quickly.

**Why:** OMP may exit after a single turn. The wrapper ensures the agent keeps trying until timeout. `--list-models` acts as an early connectivity check, failing fast if the inference endpoint is unreachable. The notes file provides continuity across fresh OMP invocations without implementing the RPC wire protocol.

### 9) CLI surface with inference configuration

The CTF entrypoint is `python -m ctf` with options: `--model` (required, e.g. `llama3.2`), `--endpoint` (default `localhost:8080`), `--keep-on-failure`, and `--timeout` (default 300). No subcommands. Internal paths (workspace, signal file, report file) are derived from the temp workspace path.

**Why:** `--model` is required because OMP needs to know which LLM to use — the test is meaningless without it. `--endpoint` defaults to `localhost:8080` (llama.cpp's default), matching OMP's own default probe target. Operator-facing simplicity wins; all internal paths are derived.

**Alternative considered:** make `--model` optional, run without an LLM. Rejected — the value of CTF is testing an AI-augmented adversary against the containment boundary, not a script.


### 10) Config-on-disk Lockdown construction

The harness writes a `.microjail/config.yaml` to the temp workspace containing the default Lockdown (`NetworkDrop` + `ReadonlyConfig`), then loads it via `MicroJail.load()`. This exercises the same config deserialization path that user-facing commands use.

**Why:** Tests the full config→load→apply stack rather than constructing Lockdown programmatically, catching deserialization bugs that programmatic construction would hide.

**Alternative considered:** build Lockdown in Python with `Lockdown.default()`. Rejected because it skips the config loading path that users actually exercise.

### 11) Preflight: binary availability only

Preflight validates that `workshop` and `lxc` are on `$PATH`. Module import checks are deferred — if microjail can't be imported the harness will fail naturally with a clear traceback. No resources are created before preflight passes.

**Why:** Binary checks catch the most common failure mode (missing Workshop/LXD) without adding brittle import-path validation that duplicates what Python's own import system already reports clearly.

**Alternative considered:** also validate microjail imports in preflight. Rejected as redundant — a missing import produces a clear enough error without custom preflight scaffolding.

### 12) Lockdown with inference endpoint capability

The CTF Lockdown includes `NetworkDrop` and `ReadonlyConfig` gates. When `--model` is provided (always), the Lockdown also includes a `WorkshopEndpointCapability` named `inference` pointing at the `--endpoint` address. This tunnels the host inference endpoint to container `localhost:8080`, giving OMP's agent LLM access. The HTTP bait runs on a different port — reaching it is a containment breach. No `WorkshopEndpointCapability` is declared for the bait port.

**Why:** The test scenario mirrors real workloads where an agent has legitimate API access but must remain sandboxed. The containment boundary is tested by whether the agent can reach unauthorized network targets despite having an authorized tunnel.

**Alternative considered:** run without an inference endpoint (bare containment). Rejected — fewer real-world scenarios involve agents with zero network tools.

### 13) Single run, both vectors, one verdict

A single CTF invocation tests both the filesystem and HTTP vectors. The agent is told both target coordinates and attempts both. If either yields a secret match in the signal file, the verdict is FAIL.

**Why:** A single integrated run matches real attack scenarios where an actor tries multiple escape paths. It also halves the runtime compared to separate invocations.

**Alternative considered:** separate `--vector file|http` invocations. Rejected as slower operationally without adding meaningful signal separation.

### 14) Standard report schema

The JSON report includes: `outcome`, `error_kind` (if ERROR), `elapsed`, `timeout`, `secret_match` (bool), `breach_vector` (file/http if FAIL), `run_id` (uuid). These fields provide enough diagnostic detail for operator triage without forcing full forensic capture.

**Why:** Standard fields answer the immediate operator questions: did containment hold, what failed, which vector breached, how long did it take. Full forensics (raw signal content, agent stdout) can be recovered from the retained workspace.

**Alternative considered:** minimal report (outcome only). Rejected as insufficient for triaging failures.

### 15) CTF implements its own monitoring loop

The harness polls the signal file from the host side on a fixed short interval (default 0.2s). This is separate from microjail's Warden — the Warden does not exist yet, and CTF's monitoring needs are simpler (one file, one match condition) than Warden's full gate/cap validation loop.

**Why:** Keeps CTF self-contained and avoids making it a forcing function for Warden, which is a much larger feature. The monitoring logic is simple enough to inline.

**Alternative considered:** build minimal Warden first, then use it in CTF. Rejected because Warden's scope (polling all Gates + Caps, violation escalation, SIGTERM/SIGKILL sequencing) is an order of magnitude larger than what CTF needs.

## Risks / Trade-offs

- **Risk:** Port captures old UX superficially but diverges on branch-specific lock/run semantics. → **Mitigation:** assert parity-critical control flow (preflight, monitoring, teardown, verdict precedence) in `tests/escape`.
- **Risk:** LXD resource leaks if workspace cleanup fails mid-teardown. → **Mitigation:** ordered teardown (release → stop → LXD delete → rm -rf) with each step wrapped in suppress(Exception) so later steps still run.
- **Risk:** OMP agent may burn significant LLM tokens in a 300s run. → **Mitigation:** timeout is configurable via `--timeout`; default tuned for meaningful attempts without excessive cost.
- **Risk:** OMP agent may find unplanned escape vectors and produce false negatives (breach via vector we didn't seed). → **Mitigation:** this is acceptable — the test measures containment boundary strength. If the agent breaks out through any path, the containment failed.
- **Risk:** Inference endpoint unreachable at agent startup (`omp --list-models` fails). → **Mitigation:** fail fast before agent loop with clear ERROR diagnostics; operator can verify endpoint independently.

## Migration Plan

1. Create `ctf/` package with fresh modules: `runner.py` (orchestration), `http_server.py` (cherry-picked from `e4c3702`), `secrets_gen.py` (cherry-picked), `report.py`, `__main__.py`, and thin CLI with `--model`, `--endpoint`, `--keep-on-failure`, `--timeout` flags.
2. Add `tests/escape/` scaffold (`conftest.py`, helpers, scenarios) with `slow` + `lxd` + `workshop` marks.
3. Wire the full flow: preflight → workspace → `workshop init --sdks omp/14/edge` + launch → config write with inference endpoint capability → `MicroJail.load()` + `ensure_for_run()` → write prompt (with loop/notes instructions) + agent wrapper script → start HTTP bait on unused port → write host secret → launch agent via `subprocess.Popen` → concurrent signal polling → SIGTERM → verdict → ordered teardown.
4. Implement report persistence with FAIL-over-ERROR precedence.
5. Verify with targeted unit tests for helper/logic modules and `uv run pytest --slow tests/escape` in a capable environment.

## Open Questions

- None blocking for implementation. OMP goal/loop directives and expanded attack vectors are explicitly deferred follow-up investigations.
