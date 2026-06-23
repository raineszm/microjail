# Implementation Tasks

## Slice 1: Tracer Bullet - readonly-config
- **Test**: test_readonly_config_verify in tests/unit/test_readonly_config.py
- **Arrange**: Instantiate a `ReadonlyConfig` gate and create a mock `MicroJail` instance.
- **Act**: Call `gate.verify(microjail)`.
- **Assert**: Assert that the return value is `True` and no exception is raised.

- [ ] 1.1 RED: test_readonly_config_verify
- [ ] 1.2 GREEN: Add verify method to Gate and Capability protocols, and implement verify in ReadonlyConfig
- [ ] 1.3 REFACTOR: none

## Slice 2: Tracer Bullet - network-drop
- **Test**: test_network_drop_check_and_verify in tests/unit/test_network_drop.py
- **Arrange**: Instantiate a `NetworkDrop` gate and mock `MicroJail`.
- **Act**: Call `gate.check(microjail)` and `gate.verify(microjail)` under various mock `lxc_instance()` responses.
- **Assert**: Assert that `check()` returns `True` when no NICs are present, `False` when NICs are present, `False` when container is missing, and `verify()` returns `True` unconditionally.

- [ ] 2.1 RED: test_network_drop_check_and_verify
- [ ] 2.2 GREEN: Implement config-only check() and verify() on NetworkDrop
- [ ] 2.3 REFACTOR: none

## Slice 3: Tracer Bullet - endpoint-capability
- **Test**: test_endpoint_capability_check_and_verify in tests/unit/test_endpoint_capability.py
- **Arrange**: Instantiate a `WorkshopEndpointCapability` and mock `MicroJail` and `workshop.tunnel`.
- **Act**: Call `cap.check(microjail)` and `cap.verify(microjail)`.
- **Assert**: Assert that `check()` returns config state (connection present → True, connection absent → False), and `verify()` returns reachability state (reachable → True, unreachable/errors → False).

- [ ] 3.1 RED: test_endpoint_capability_check_and_verify
- [ ] 3.2 GREEN: Implement config-only check() and verify() on WorkshopEndpointCapability
- [ ] 3.3 REFACTOR: none

## Slice 4: Tracer Bullet - pre-launch-verify
- **Test**: test_pre_launch_verify in tests/unit/test_pre_launch_verify.py
- **Arrange**: Create a mock `MicroJail` with various mock gates and capabilities having different `verify()` return values and `fatal` configurations.
- **Act**: Call `microjail.pre_launch_verify()`.
- **Assert**: Assert that gate verify failures raise `GateError`, fatal capability failures raise `CapabilityError` with `non_fatal_failures` populated, and non-fatal capability failures are collected and returned in the result.

- [ ] 4.1 RED: test_pre_launch_verify
- [ ] 4.2 GREEN: Implement pre_launch_verify() on MicroJail
- [ ] 4.3 REFACTOR: none

## Slice 5: Tracer Bullet - CLI Integration & Tests
- **Test**: test_lock_pre_launch_verify_integration in tests/functional/commands/test_lock.py and test_pre_launch_verify_e2e in tests/e2e/test_pre_launch_verify.py
- **Arrange**: Mock `pre_launch_verify()` on `MicroJail` to return mock verification results or raise exceptions. For E2E, define a Lockdown with a failing fatal capability.
- **Act**: Run `lock`, `exec`, and `shell` commands.
- **Assert**: Assert that the commands display warnings to stderr, raise errors, exit with the correct exit codes (68/66), and do not spawn workloads.

- [ ] 5.1 RED: test_lock_pre_launch_verify_integration
- [ ] 5.2 GREEN: Integrate pre_launch_verify() into lock, exec, and shell commands, and implement the e2e test
- [ ] 5.3 REFACTOR: none
