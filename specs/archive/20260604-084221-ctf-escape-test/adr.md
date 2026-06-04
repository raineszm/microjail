# ADR: CTF containment escape test

Date: 2026-06-04
Status: Accepted

## Context

The project needed an adversarial, end-to-end containment check that exercises a real agent inside a locked Workshop/LXD environment.

## Decision

- Add a top-level `ctf` package with a Typer entry point runnable as `python -m ctf`.
- Create a temporary Workshop environment per run and remove it during teardown.
- Plant one filesystem secret on the host and one network secret behind a host-local HTTP server.
- Run an agent-side script inside the container; the script has no imports from `ctf` or `microjail`.
- Detect breach by monitoring a workspace signal file containing either planted secret.
- Report `PASS`, `FAIL`, or `ERROR` through a structured report model and JSON report output.
- Always attempt unlock, environment removal, secret deletion, server shutdown, and workspace cleanup in `finally`.

## Consequences

- The CTF runner tests containment behavior rather than only unit-level plumbing.
- Secrets are generated per run and never hard-coded.
- Cleanup is best-effort but explicit, so interrupted runs do not intentionally leave egress locked or temp secrets behind.
