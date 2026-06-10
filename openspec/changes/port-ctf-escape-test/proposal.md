## Why

This branch does not include the CTF runner or the adversarial escape workflow that existed on main. We need both ported so containment regressions are caught early while preserving this branch's test architecture and conventions.

## What Changes

- Build fresh `ctf/` package (using reverted commit `e4c3702` as reference for `http_server.py` and `secrets_gen.py`) as explicit, standalone adversarial tooling — not part of `microjail` product CLI.
- In-container adversary is an OMP AI agent (`omp/14/edge` SDK). A `WorkshopEndpointCapability` tunnels the inference endpoint (default `localhost:8080`) to container `localhost:8080`. OMP auto-discovers the provider via `omp --list-models`.
- `--model` is a required CLI flag (e.g. `llama3.2`). `--endpoint` defaults to `localhost:8080`.
- A bash wrapper script runs `omp --list-models` (fail-fast connectivity check), then loops `omp -p "$PROMPT" --model "$MODEL"` with a notes file (`ctf_notes.md`) for cross-iteration memory. The prompt instructs OMP to read notes at the start of each turn and update them at the end.
- Harness imports microjail for policy operations (`ensure_for_run()`, `release()`). Agent launch uses `subprocess.Popen` with raw `workshop exec` for concurrent signal-file polling and SIGTERM termination.
- Full flow: preflight → `workshop init --sdks omp/14/edge` + launch → write `.microjail/config.yaml` (NetworkDrop + ReadonlyConfig + inference endpoint capability) → `MicroJail.load()` + `MicroJail.ensure_for_run()` → write adversarial prompt + agent wrapper → start HTTP bait (different port) + host secret → launch agent via Popen → concurrent signal polling → SIGTERM + verdict → ordered teardown.
- CLI: `python -m ctf --model <MODEL> [--endpoint localhost:8080] [--keep-on-failure] [--timeout N]`. Default 300s timeout. Both file and HTTP vectors in one run.
- Verdict precedence: FAIL (breach) beats ERROR (report persistence). ERROR/`report_persistence` only overrides would-be PASS.
- JSON report: `outcome`, `error_kind`, `elapsed`, `timeout`, `secret_match`, `breach_vector`, `run_id`.
- Preflight: binary availability (`workshop`, `lxc`) only.
- Workspace at `/tmp/ctf-<uuid>/` with explicit ordered teardown.

## Capabilities

### New Capabilities

- `ctf-escape-test`: End-to-end containment regression testing that validates a jailed workload cannot exfiltrate seeded host secrets via filesystem or network vectors within a bounded timeout.

### Modified Capabilities

*(none — no existing spec requirements change)*

## Impact

- **Added source**: reintroduce `ctf/` runner modules as internal repository tooling with a standalone entrypoint; depends on OMP being available as a Workshop SDK.
- **Added tests**: add `tests/escape/` suite and shared helpers required to validate harness control flow and outcomes.
- **Operational behavior**: preserve JSON report output with FAIL-over-ERROR verdict precedence and ordered teardown guaranteeing no LXD resource leaks.
- **CLI boundary**: existing `microjail` command surface (`init`, `lock`, `run`, `unlock`) remains unchanged.
