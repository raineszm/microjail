# Implementation Tasks

## Slice 1: Tracer Bullet - Add Endpoint Capability declaration
- **Test**: `test_cap_add_endpoint_writes_config` in `tests/functional/commands/test_cap.py`
- **Arrange**: Create a temporary Microjail project with `.microjail/config.yaml` containing a Workshop named `test-jail`, empty `lockdown.caps`, and default Gates or no Gates. Use `CliRunner` against `microjail.cli.app`. Monkeypatch `Workshop.info` to return `None` so the Workshop is known not launched and declaration-only editing is permitted.
- **Act**: Invoke `app` with `--project <tmp_path> cap add endpoint inference localhost:8080`.
- **Assert**: Exit code is `0`; `.microjail/config.yaml` reloads as `MicroJail`; `lockdown.caps` contains one `WorkshopEndpointCapability` with `name="inference"`, `host_endpoint="localhost:8080"`, `container_endpoint is None`, and `fatal is False`; output includes `endpoint capability added: inference -> localhost:8080`.

- [x] 1.1 RED: `test_cap_add_endpoint_writes_config`
- [x] 1.2 GREEN: Add `cap` Typer group, `add endpoint` command, config mutation, canonical save, and success output for declaration-only add
- [x] 1.3 REFACTOR: Extract shared command config-loading/save helpers only if the tracer bullet duplicates existing command patterns

## Slice 2: Endpoint add options and same-value idempotency
- **Test**: `test_cap_add_endpoint_with_container_endpoint`, `test_cap_add_endpoint_fatal`, and `test_cap_add_endpoint_same_value_idempotent` in `tests/functional/commands/test_cap.py`
- **Arrange**: Same as Slice 1 — temporary project with empty config, Workshop.info monkeypatched to None.
- **Act**: Vary flags (`--container-endpoint`, `--fatal`) or same-name scenarios per sub-test.
- **Assert**: Container endpoint and fatal are persisted; adding same name+host_endpoint succeeds without duplicate; adding same name+different host_endpoint fails without `--replace`.

- [x] 2.1 RED: Write failing tests for options (container-endpoint, fatal) and idempotent same-value add; same-name different-host fails without `--replace`
- [x] 2.2 GREEN: Wire `--container-endpoint`, `--fatal` pass-through; detect existing same-name capability; accept same-value, reject changed without `--replace`
- [x] 2.3 REFACTOR: Extract endpoint-name validation helper if duplicate-detection logic warrants it


## Slice 3: Endpoint replacement semantics and type safety
- **Test**: `test_cap_add_endpoint_replace_values` and `test_cap_add_endpoint_fatal_replace_requires_flag` in `tests/functional/commands/test_cap.py`
- **Arrange**: Same project setup; first add a capability, then attempt add with `--replace`.
- **Act**: For replace-values: add then replace with different host_endpoint. For fatal-change: add with --fatal, then replace without --fatal.
- **Assert**: `--replace` updates endpoint values; changing `--fatal` without `--replace` is rejected.

- [x] 3.1 RED: Write tests for --replace value replacement and --fatal change detection
- [x] 3.2 GREEN: Implement --replace and fatal-change detection in add_endpoint
- [x] 3.3 REFACTOR: Simplify duplicate/replace logic if patterns emerge
## Slice 4: Endpoint remove command
- **Test**: `test_cap_remove_endpoint_writes_config` and `test_cap_remove_endpoint_missing_fails` in `tests/functional/commands/test_cap.py`
- **Arrange**: Temporary project; for remove-existing, add an endpoint capability first; for remove-missing, start with empty caps. Workshop.info monkeypatched to None.
- **Act**: Run `cap remove endpoint <name>`.
- **Assert**: Remove-existing: capability is removed from config, success message printed. Remove-missing: command fails with non-zero exit, config unchanged.

- [x] 4.1 RED: Write tests for removing endpoint and removing missing endpoint
- [x] 4.2 GREEN: Implement `cap remove endpoint <name>` command
- [x] 4.3 REFACTOR: Consolidate command config-loading pattern if duplicated

## Slice 5: Config validation
- **Test**: `test_cap_add_endpoint_rejects_invalid_name`, `test_cap_add_endpoint_rejects_invalid_address`, `test_cap_add_endpoint_rejects_address_without_port`, `test_cap_add_endpoint_rejects_non_numeric_port`, `test_cap_add_endpoint_rejects_out_of_range_port` in `tests/functional/commands/test_cap.py`
- **Arrange**: Temporary project with empty config; Workshop.info monkeypatched to None.
- **Act**: Run `cap add endpoint` with invalid names and endpoint addresses.
- **Assert**: Invalid endpoint names (starting with digit, containing special chars) fail; invalid addresses (URLs, missing port) fail; commands do not save config.

- [x] 5.1 RED: Write tests for endpoint name and address validation
- [x] 5.2 GREEN: Add name and endpoint address validation helpers and wire into add/remove commands
- [x] 5.3 REFACTOR: Consolidate validation into shared module if multiple validators emerge

## Slice 6: Workshop state preflight for declaration-only edits
- **Test**: `test_declaration_only_not_launched_saves`, `test_declaration_only_pending_fails`, `test_declaration_only_stopped_warns`, `test_declaration_only_off_warns`, `test_declaration_only_ready_unlocked_saves_with_warning`, `test_declaration_only_ready_locked_fails`, `test_declaration_only_unknown_state_fails` in `tests/functional/commands/test_cap.py`
- **Arrange**: Temporary project; monkeypatch `Workshop.info` to return different states per sub-test. Use `RecordingGate` to simulate locked state.
- **Act**: Run `cap add endpoint` without `--apply` under each state.
- **Assert**: Not launched → saves without warning. Pending → fails before saving. Off/stopped → saves with warning. Ready+unlocked → saves with warning. Ready+locked → fails before saving. Workshop.info error → fails before saving.

- [x] 6.1 RED: Write tests for state preflight in declaration-only mode across all Workshop states
- [x] 6.2 GREEN: Add `_preflight_workshop_state()` helper and wire into `add_endpoint` and `remove_endpoint`
- [x] 6.3 REFACTOR: Extract state preflight into shared module if cap.py grows too large

## Slice 7: --apply behavior by Workshop state
- **Test**: `test_apply_not_launched_fails`, `test_apply_pending_fails`, `test_apply_stopped_updates_declarations`, `test_apply_ready_locked_fails`, `test_apply_ready_unlocked_saves_and_ensures` in `tests/functional/commands/test_cap.py`
- **Arrange**: Same project setup; monkeypatch `Workshop.info` to simulate states and `Workshop` methods to record calls.
- **Act**: Run `cap add endpoint inference localhost:8080 --apply` under each state.
- **Assert**: Not launched/pending/ready+locked/unknown → fails before saving. Off/stopped → saves config + updates Workshop declarations, does not start/refresh. Ready+unlocked → applies through Lockdown application path.

- [x] 7.1 RED: Write tests for --apply behavior across all Workshop states
- [x] 7.2 GREEN: Implement --apply state-dependent behavior in `add_endpoint` and `remove_endpoint`
- [x] 7.3 REFACTOR: Extract common apply path if shared with lock/exec/shell

## Slice 8: Duplicate capability name validation on load
- **Test**: `test_cap_add_endpoint_rejects_duplicate_names_in_config` in `tests/functional/commands/test_cap.py`
- **Arrange**: Create config with two caps of same name before running command.
- **Act**: Run `cap add endpoint` or `cap remove endpoint`.
- **Assert**: Command fails before saving with error about duplicate names.
- [x] 8.1 RED: Write test for duplicate capability name detection
- [x] 8.2 GREEN: Add duplicate-name check to command validation step
- [x] 8.3 REFACTOR: Move into shared validation module
