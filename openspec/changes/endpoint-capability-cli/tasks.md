# Implementation Tasks

## Slice 1: Tracer Bullet - Add Endpoint Capability declaration
- **Test**: `test_cap_add_endpoint_writes_config` in `tests/functional/commands/test_cap.py`
- **Arrange**: Create a temporary Microjail project with `.microjail/config.yaml` containing a Workshop named `test-jail`, empty `lockdown.caps`, and default Gates or no Gates. Use `CliRunner` against `microjail.cli.app`. Monkeypatch `Workshop.info` to return `None` so the Workshop is known not launched and declaration-only editing is permitted.
- **Act**: Invoke `app` with `--project <tmp_path> cap add endpoint inference localhost:8080`.
- **Assert**: Exit code is `0`; `.microjail/config.yaml` reloads as `MicroJail`; `lockdown.caps` contains one `WorkshopEndpointCapability` with `name="inference"`, `host_endpoint="localhost:8080"`, `container_endpoint is None`, and `fatal is False`; output includes `endpoint capability added: inference -> localhost:8080`.

- [ ] 1.1 RED: `test_cap_add_endpoint_writes_config`
- [ ] 1.2 GREEN: Add `cap` Typer group, `add endpoint` command, config mutation, canonical save, and success output for declaration-only add
- [ ] 1.3 REFACTOR: Extract shared command config-loading/save helpers only if the tracer bullet duplicates existing command patterns

## Slice 2: [Pending] - Endpoint add options and idempotency
<!-- Test details and tasks will be planned after Slice 1 is complete -->
- [ ] 2.1 RED: pending
- [ ] 2.2 GREEN: pending
- [ ] 2.3 REFACTOR: pending

## Slice 3: [Pending] - Endpoint replacement semantics
<!-- Test details and tasks will be planned after Slice 1 is complete -->
- [ ] 3.1 RED: pending
- [ ] 3.2 GREEN: pending
- [ ] 3.3 REFACTOR: pending

## Slice 4: [Pending] - Endpoint remove command
<!-- Test details and tasks will be planned after Slice 1 is complete -->
- [ ] 4.1 RED: pending
- [ ] 4.2 GREEN: pending
- [ ] 4.3 REFACTOR: pending

## Slice 5: [Pending] - Config validation
<!-- Test details and tasks will be planned after Slice 1 is complete -->
- [ ] 5.1 RED: pending
- [ ] 5.2 GREEN: pending
- [ ] 5.3 REFACTOR: pending

## Slice 6: [Pending] - Workshop state preflight and warnings
<!-- Test details and tasks will be planned after Slice 1 is complete -->
- [ ] 6.1 RED: pending
- [ ] 6.2 GREEN: pending
- [ ] 6.3 REFACTOR: pending

## Slice 7: [Pending] - Apply behavior by Workshop state
<!-- Test details and tasks will be planned after Slice 1 is complete -->
- [ ] 7.1 RED: pending
- [ ] 7.2 GREEN: pending
- [ ] 7.3 REFACTOR: pending

## Slice 8: [Pending] - Endpoint declaration reconciliation during Lockdown application
<!-- Test details and tasks will be planned after Slice 1 is complete -->
- [ ] 8.1 RED: pending
- [ ] 8.2 GREEN: pending
- [ ] 8.3 REFACTOR: pending

## Slice 9: [Pending] - Reconciliation failure semantics
<!-- Test details and tasks will be planned after Slice 1 is complete -->
- [ ] 9.1 RED: pending
- [ ] 9.2 GREEN: pending
- [ ] 9.3 REFACTOR: pending

## Slice 10: [Pending] - User-facing docs and schema examples
<!-- Test details and tasks will be planned after Slice 1 is complete -->
- [ ] 10.1 RED: pending
- [ ] 10.2 GREEN: pending
- [ ] 10.3 REFACTOR: pending
