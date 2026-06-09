## Why

This branch does not include the CTF runner or the adversarial escape workflow that existed on main. We need both ported so containment regressions are caught early while preserving this branch’s test architecture and conventions.

## What Changes

- Port the CTF runner modules from main into a top-level `ctf/` package as explicit, standalone adversarial tooling (not part of `microjail` product CLI).
- Add a dedicated `tests/escape/` suite that validates the CTF harness behavior and containment outcomes.
- Keep the harness UX and execution model consistent with the prior flow: per-run secrets, host file + host HTTP bait, iterative in-container agent attempts, deterministic cleanup, and report-backed verdict semantics.
- Use an ephemeral temporary workspace per run, with an optional debug escape hatch to retain it on failure.
- Keep CTF execution explicitly opt-in (`python -m ctf` / slow tests), with no automatic invocation from `microjail` commands.

## Capabilities

### New Capabilities

- `ctf-escape-test`: End-to-end containment regression testing that validates a jailed workload cannot exfiltrate seeded host secrets via filesystem or network vectors within a bounded timeout.

### Modified Capabilities

*(none — no existing spec requirements change)*

## Impact

- **Added source**: reintroduce `ctf/` runner modules as internal repository tooling with a standalone entrypoint.
- **Added tests**: add `tests/escape/` suite and shared helpers required to validate harness control flow and outcomes.
- **Operational behavior**: preserve default JSON report output and introduce a distinct report-persistence error condition.
- **CLI boundary**: existing `microjail` command surface (`init`, `lock`, `run`, `unlock`) remains unchanged.
