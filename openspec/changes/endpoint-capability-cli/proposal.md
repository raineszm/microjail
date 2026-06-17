## Why

Users currently must edit `.microjail/config.yaml` by hand to add common Endpoint capabilities, and stale Workshop tunnel declarations can survive manual config edits until runtime behavior diverges from the reviewed Lockdown. Microjail needs a safe CLI path for Endpoint capability declarations while preserving the distinction between declaration edits and runtime Lockdown application.

## What Changes

- Add `microjail cap add endpoint NAME HOST_ENDPOINT` for adding Endpoint Capability declarations.
- Add `microjail cap remove endpoint NAME` for removing Endpoint Capability declarations.
- Support `--container-endpoint`, `--fatal`, `--replace`, and `--apply` on endpoint adds.
- Support `--apply` on endpoint removes.
- Validate Capability names globally within a Lockdown and validate Endpoint name/address syntax before runtime mutation.
- Reconcile Microjail-owned Workshop endpoint declarations during Lockdown application so current Endpoint Capability declarations remain the source of truth for `lock`, `run`, and `shell`.
- Fix user-facing Endpoint capability docs/examples to use the actual `host_endpoint` field.
- Add an ADR documenting why the CLI edits declarations by default and uses explicit, state-sensitive `--apply` for runtime changes.

## Capabilities

### New Capabilities

- `endpoint-capability-cli`: User-facing CLI commands for adding, replacing, removing, validating, and optionally applying Endpoint Capability declarations.

### Modified Capabilities

- `endpoint-capability`: Lockdown application reconciles Microjail-owned Workshop endpoint declarations against current Endpoint Capability declarations before providing declared endpoints.
- `user-facing-test-coverage`: Add coverage for Endpoint Capability CLI declaration editing, validation, state-sensitive `--apply`, and stale declaration reconciliation.

## Impact

- `src/microjail/cli.py`: Add the `cap` command group.
- `src/microjail/commands/`: Add command handlers for `cap add endpoint` and `cap remove endpoint`.
- `src/microjail/microjail.py`: Add explicit Lockdown validation and endpoint declaration reconciliation during application.
- `src/microjail/caps/endpoint.py` and `src/microjail/adapters/workshop.py`: Expose reusable endpoint validation/reconciliation helpers as needed.
- `README.md`: Document the CLI-first Endpoint capability workflow and fix the manual YAML example.
- `docs/adr/0005-endpoint-capability-cli-declaration-application.md`: Records the declaration/application split and state matrix.
- Tests: Add unit/functional coverage for CLI behavior, validation, and reconciliation; add user-facing coverage where practical.
