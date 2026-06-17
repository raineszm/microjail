# Implementation Tasks

## Slice 1: Tracer Bullet - MicroJail.status() method with status dataclass

- **Test**: `test_status_returns_workshop_info_and_lockdown_state` in `tests/unit/test_microjail.py`
- **Arrange**:
  - Create a `MicroJail` with a named workshop and lockdown with a capability and a gate.
  - Mock `workshop.info()` to return `WorkshopInfo(name="test", status="ready")`.
  - Mock `workshop.tunnel.connections()` to return `[("test/microjail:inf", "test/system:inf")]`.
- **Act**: Call `microjail.status()`.
- **Assert**:
  - Result includes `workshop_name == "test"`, `workshop_status == "ready"`.
  - Result includes capability names and gate names from the lockdown.
  - Result includes the connection row.

- [x] 1.1 RED: `test_status_returns_workshop_info_and_lockdown_state`
- [x] 1.2 GREEN: Implement `MicroJail.status()` returning a `MicroJailStatus` dataclass. Call `workshop.info()` and `workshop.tunnel.connections()`, read `self.lockdown` for declared state.
- [x] 1.3 REFACTOR: Add graceful handling for `workshop.info()` returning None and `tunnel.connections()` raising — set workshop_status to "unavailable" and connections to empty.

## Slice 2: microjail status CLI command

<!-- Wire status() into CLI. Handle uninitialized project with "not initialized" message. -->

- [x] 2.1 RED: `test_status_reports_not_initialized` functional test
- [x] 2.2 GREEN: Create `src/microjail/commands/status.py`, wire into cli.py
- [x] 2.3 REFACTOR: none

## Slice 3: MicroJail.validate() method

<!-- Iterate lockdown capabilities and gates, call existing validation methods, collect errors. -->

- [x] 3.1 RED: 4 unit tests for validate (valid config, dup names, bad name, bad address)
- [x] 3.2 GREEN: Add `ValidateError` dataclass + `MicroJail.validate()` with dedup and endpoint validation
- [x] 3.3 REFACTOR: none

## Slice 4: microjail validate CLI command

<!-- Wire validate() into CLI. Handle uninitialized project. Report all errors with hints. -->

- [x] 4.1 RED: `test_validate_reports_not_initialized`, `test_validate_reports_valid`, `test_validate_reports_config_errors`
- [x] 4.2 GREEN: Create `src/microjail/commands/validate.py`, wire into cli.py
- [x] 4.3 REFACTOR: none

## Slice 5: Duplicate capability name detection in validate

<!-- Ensure validate catches duplicate capability names in the lockdown. -->

- [x] 5.1 RED: Covered by `test_validate_detects_duplicate_cap_names`
- [x] 5.2 GREEN: Duplicate detection logic in `MicroJail.validate()` using `seen` set
- [x] 5.3 REFACTOR: none

## Slice 6: Endpoint syntax validation in validate

<!-- Ensure validate calls existing endpoint validation for WorkshopEndpointCapability. -->

- [x] 6.1 RED: Covered by `test_validate_detects_bad_endpoint_name` and `test_validate_detects_bad_endpoint_address`
- [x] 6.2 GREEN: Reuse `validate_endpoint_name()` and `validate_endpoint_address()` from `caps/endpoint.py`
- [x] 6.3 REFACTOR: none
