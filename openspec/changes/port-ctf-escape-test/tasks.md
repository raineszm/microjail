## 1. Reconstruct baseline escape harness context

- [x] 1.1 Extract the prior CTF escape workflow behavior from main/history (secret generation, host bait setup, monitor loop, verdict mapping, cleanup order) and codify expected invariants for this branch.
- [x] 1.2 Map current branch adapter/test seams (`tests/_helpers.py`, `tests/e2e` fixtures, workshop/lxd wrappers) and decide which pieces are reused vs escape-local helpers.

## 2. Add tests/escape suite structure

- [x] 2.1 Create `tests/escape/` package with `conftest.py` that applies required environment marks (`slow`, `lxd`, `workshop`) using existing marker helpers.
- [x] 2.2 Add escape-local helper module(s) for temporary workspace lifecycle, secret-file/http-server setup, signal-file polling, and deterministic teardown.
- [x] 2.3 Add fixtures that preflight required binaries/import wiring and expose harness inputs for escape scenarios.

## 3. Port harness behavior with branch-compatible integration points

- [x] 3.1 Reintroduce `ctf/` runner modules and entrypoint (`python -m ctf`) as standalone internal tooling; do not wire into `microjail` command auto-paths.
- [x] 3.2 Implement signal-file breach detection with fixed short-interval polling under a single global timeout (no per-iteration cap additions).
- [x] 3.3 Implement teardown guarantees for success, breach, and setup/runtime failure paths (unlock policy state, stop HTTP server, remove secret artifacts, remove workspace/environment by default).
- [x] 3.4 Add failure-only workspace retention debug option.
- [x] 3.5 Implement report-persistence classification as `outcome=ERROR` with `error_kind=report_persistence`, overriding computed PASS/FAIL when report write fails.
- [x] 3.6 Emit operator-visible diagnostics on report-persistence failure (transport/format left implementation-defined for alpha).

## 4. Implement escape test scenarios

- [x] 4.1 Add a no-breach scenario asserting timeout-driven PASS behavior and expected summary/report fields.
- [x] 4.2 Add a breach scenario asserting early FAIL when a planted secret is signaled from inside the container.
- [x] 4.3 Add report-write-failure scenario asserting report-persistence classification overrides a computed PASS verdict.
- [x] 4.4 Add report-write-failure scenario asserting final classification is `ERROR` + `error_kind=report_persistence` for a computed FAIL verdict.
- [x] 4.5 Add preflight-failure scenario asserting no secrets/resources are created on missing dependency/import.
- [x] 4.6 Add workspace-retention scenario asserting default cleanup and failure-only retention behavior.
- [x] 4.7 Add discovery/selection assertions proving CTF remains explicitly invoked and escape tests remain opt-in via `--slow`.

## 5. Verify and document operational usage
- [x] 5.1 Run targeted fast tests for helper/logic modules touched by the port.
- [x] 5.2 Run `uv run pytest --slow tests/escape` in a capable environment and confirm marker gating/selection behavior.
- [x] 5.3 Update CTF help/docs and README cross-reference to clarify naming (`CTF = Capture The Flag`), internal-harness-only scope, and alpha instability of result + `error_kind` semantics.
