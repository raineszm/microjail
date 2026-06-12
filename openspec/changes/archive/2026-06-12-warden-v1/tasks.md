## Slice 1: Warden Lifecycle & Normal Exit

- [x] 1.1 RED: `test_warden_supervises_successful_exit`, `test_warden_supervises_non_zero_exit` and `test_warden_polls_on_interval`
- [x] 1.2 GREEN: Implement `Warden` class skeleton, properties, and base `supervise` polling loop in `src/microjail/warden.py`
- [x] 1.3 REFACTOR: none

## Slice 2: Gate Violation & Termination

- [x] 2.1 RED: `test_warden_terminates_on_gate_violation`
- [x] 2.2 GREEN: Implement gate violation checks in Warden loop and terminate process on gate check failure
- [x] 2.3 REFACTOR: none

## Slice 3: Capability Violation (Warning vs Fatal)

- [x] 3.1 RED: `test_warden_warns_on_non_fatal_capability_violation` and `test_warden_terminates_on_fatal_capability_violation`
- [x] 3.2 GREEN: Implement capability violation checks, warning on non-fatal violations and terminating process on fatal capability violations
- [x] 3.3 REFACTOR: none

## Slice 4: CLI Integration

- [x] 4.1 RED: `test_run_uses_warden_supervision`, `test_run_exits_with_84_on_gate_violation`, and `test_run_exits_with_82_on_fatal_capability_violation`
- [x] 4.2 GREEN: Update `run` command to launch workload with `popen` and supervise execution under `Warden`
- [x] 4.3 REFACTOR: none
