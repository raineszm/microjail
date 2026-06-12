## Tracer Bullet

- **Test**: `tests/unit/test_warden.py::test_warden_supervises_successful_exit`
- **Capability**: `warden-monitoring` / `Warden handles normal workload exit`
- **Green**: Warden runs a mock process that exits with code 0, checks policy invariants (which pass), does not raise any exceptions, and returns 0.

## Test Plan

### Slice 1: Warden Lifecycle & Normal Exit

| Scenario | Test | Arrange | Act | Assert |
|----------|------|---------|-----|--------|
| Warden checks active gates and capabilities on interval | `test_warden_polls_on_interval` | Instantiate `Warden` with a mock process, mock `MicroJail` config with active gates/caps, and `interval=0.01` | Call `warden.supervise()` while the mock process runs for a short duration | Verify `gate.check` and `cap.check` are called multiple times during execution |
| Workload exits successfully | `test_warden_supervises_successful_exit` | Instantiate `Warden` with a mock process that exits with code 0 and passing gates/caps | Call `warden.supervise()` | Verify return code is 0 and no exceptions are raised |
| Workload exits with non-zero code | `test_warden_supervises_non_zero_exit` | Instantiate `Warden` with a mock process that exits with code 1 and passing gates/caps | Call `warden.supervise()` | Verify return code is 1 and no exceptions are raised |

### Slice 2: Gate Violation & Termination

| Scenario | Test | Arrange | Act | Assert |
|----------|------|---------|-----|--------|
| Warden terminates workload when a Gate violation occurs | `test_warden_terminates_on_gate_violation` | Instantiate `Warden` with a running mock process and a Gate whose check returns `False` on the second poll | Call `warden.supervise()` | Verify `GatePolicyViolation` is raised, mock process is terminated/killed, and `process.terminate()` is called |

### Slice 3: Capability Violation (Warning vs Fatal)

| Scenario | Test | Arrange | Act | Assert |
|----------|------|---------|-----|--------|
| Warden warns on non-fatal capability violation | `test_warden_warns_on_non_fatal_capability_violation` | Instantiate `Warden` with a running mock process, a Capability whose check returns `False`, and default `fatal=False` configuration | Call `warden.supervise()`, capturing stderr output | Verify a warning is printed to stderr, process is not terminated, and run completes normally |
| Warden terminates workload on fatal capability violation | `test_warden_terminates_on_fatal_capability_violation` | Instantiate `Warden` with a running mock process, a Capability whose check returns `False`, and `fatal=True` | Call `warden.supervise()` | Verify `CapabilityPolicyViolation` is raised and the process is terminated/killed |

### Slice 4: CLI Integration

| Scenario | Test | Arrange | Act | Assert |
|----------|------|---------|-----|--------|
| Warden supervision integrated in run CLI command | `test_run_uses_warden_supervision` | Mock `Warden.supervise` and `MicroJail.popen` in `tests/functional/commands/test_run.py` | Invoke `microjail run` CLI command | Verify `popen` is called, `Warden` is instantiated and `supervise()` is called |
| Warden terminates workload when a Gate violation occurs | `test_run_exits_with_84_on_gate_violation` | Mock `Warden.supervise` to raise `GatePolicyViolation` | Invoke `microjail run` CLI command | Verify exit code is 84 |
| Warden terminates workload on fatal capability violation | `test_run_exits_with_82_on_fatal_capability_violation` | Mock `Warden.supervise` to raise `CapabilityPolicyViolation` | Invoke `microjail run` CLI command | Verify exit code is 82 |
