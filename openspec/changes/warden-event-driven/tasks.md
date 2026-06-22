# Implementation Tasks

## Slice 1: [Done] - Tracer Bullet - LxdEventWatcher connects and emits the "reconnect" sentinel
- **Test**: `test_watcher_emits_reconnect_sentinel_on_initial_connect` in `tests/unit/test_lxd_events.py`
- **Arrange**:
  - `from unittest.mock import Mock` and `import json`
  - Build a `mock_socket = Mock()` whose `recv` is unused for this test (the connect is what we are exercising)
  - Build a `mock_connect = Mock(return_value=mock_socket)` that records the connect attempt and returns the mock socket
  - Construct `LxdEventWatcher(container_name="test-container", lxd_project="test-project", connect=mock_connect)` so the watcher uses the injected connect callable instead of the real `websockets.sync.client.connect`
- **Act**:
  - Call `watcher.start()` to spawn the reader thread and open the mock connection
  - Read from `watcher.events.get(timeout=1.0)` to receive the first item the watcher enqueues
  - Call `watcher.stop()` in a `finally` block to terminate the reader thread and close the mock connection
- **Assert**:
  - The retrieved event is the literal string `"reconnect"`
  - `mock_connect.assert_called_once()` — the watcher opened exactly one connection on first start
  - The mock socket's `close()` was called during `stop()`

- [x] 1.1 RED: test_watcher_emits_reconnect_sentinel_on_initial_connect
- [x] 1.2 GREEN: Create `src/microjail/adapters/lxd_events.py` with `class LxdEventWatcher` and `class LxdEnforcementLost(Exception)`. Constructor takes `container_name: str`, `lxd_project: str`, and an optional `connect: Callable[..., Any] = websockets.sync.client.connect` (the default uses the real client; tests inject a mock). `start()` spawns a `threading.Thread` that runs the connect loop and pushes events onto `self.events: queue.Queue[str]`. On every successful connect, the loop pushes the literal string `"reconnect"`. `stop()` sets a stop flag, closes the WebSocket, and joins the thread. Add `websockets` to `pyproject.toml` and run `uv sync`. Confirm the test passes.
- [x] 1.3 REFACTOR: Imports alphabetical, ruff clean, type hints on the constructor parameters, no behavior changes.

## Slice 2: [Done] - LxdEventWatcher reconnect backoff and sentinel on reconnect
- [x] 2.1 RED: test_watcher_reconnects_after_disconnect_without_cooldown in tests/unit/test_lxd_events.py
- [x] 2.2 GREEN: _run_loop drains the WebSocket, calls reconnect on disconnect, and pushes a new "reconnect" sentinel on each successful (re)connect. RECONNECT_BACKOFFS = (0.3, 0.5) bounded the budget.
- [x] 2.3 REFACTOR: switched to an explicit ``next()`` loop in _drain_until_stopped so the stop check runs even when the iterator is empty.

## Slice 3: [Done] - LxdEnforcementLost escalation after 3 failed reconnects
- [x] 3.1 RED: test_watcher_escalates_after_disconnect_reconnects_fail + test_watcher_escalates_after_initial_connect_failures in tests/unit/test_lxd_events.py
- [x] 3.2 GREEN: _connect_with_retries makes up to three attempts with 0.3s/0.5s backoff between them; on the third failure raises LxdEnforcementLost, which the runner stores in last_exception.
- [x] 3.3 REFACTOR: extracted _connect_with_retries from _run_loop; budget assertion in tests is timing-based (escalation within 1.0s) rather than counting attempts.

## Slice 4: [Done] - Protocol extension: verify() on Gate and Capability
- [x] 4.1 RED: test_concrete_gates_satisfy_gate_protocol and test_concrete_capabilities_satisfy_capability_protocol in tests/unit/test_protocols.py
- [x] 4.2 GREEN: added ``def verify(self, microjail: MicroJail) -> bool: ...`` to both Gate and Capability protocols.
- [x] 4.3 REFACTOR: test_protocols uses isinstance(concrete, Protocol) instead of __dict__ inspection.

## Slice 5: [Done] - NetworkDrop: check() becomes config-only, verify() returns True
- [x] 5.1 RED: test_check_returns_true_when_no_nic_devices / test_check_returns_false_when_nic_device_present / test_check_returns_true_when_devices_contain_only_non_nic in tests/unit/test_network_drop.py
- [x] 5.2 GREEN: NetworkDrop.check() now reads microjail.lxc_instance().devices and returns True iff no device has type "nic". Bash egress probe removed. verify() returns True.
- [x] 5.3 REFACTOR: added test_check_returns_false_when_lxc_query_fails to cover LxcCommandError path; the test was added in a follow-up review.

## Slice 6: [Done] - ReadonlyConfig: verify() returns True
- [x] 6.1 RED: test_readonly_config_verify_returns_true in tests/unit/test_protocols.py
- [x] 6.2 GREEN: ReadonlyConfig.verify() returns True (no behavioral probe). The mount is enforced; verification is a no-op.
- [x] 6.3 REFACTOR: kept the noop short; # noqa: ARG002 for the unused microjail parameter.

## Slice 7: [Done] - WorkshopEndpointCapability: check() and verify() split
- [x] 7.1 RED: test_check_returns_true_when_connection_row_present in tests/unit/test_endpoint_capability.py
- [x] 7.2 GREEN: check() now reads ``lxc connection list`` and validates the row. verify() calls ``tunnel.endpoint_reachable()`` for the behavioral probe.
- [x] 7.3 REFACTOR: split the old combined test into separate check/verify tests.

## Slice 8: [Done] - MicroJail.pre_launch_verify() and PreLaunchVerifyResult
- [x] 8.1 RED: 8 tests in tests/unit/test_pre_launch_verify.py
- [x] 8.2 GREEN: MicroJail.pre_launch_verify() iterates gates (stop on first verify failure) then capabilities (collect non-fatals, raise on first fatal). Returns PreLaunchVerifyResult carrying non-fatal names. CapabilityError extended with optional non_fatal_failures.
- [x] 8.3 REFACTOR: extracted the per-cap loop into a small inline check; non-fatal failures ride along on the exception when a fatal interrupts the iteration.

## Slice 9: [Done] - Wire pre_launch_verify into lock, exec, shell
- [x] 9.1 RED: covered by existing tests/functional/commands/test_exec.py and test_shell.py
- [x] 9.2 GREEN: pre_launch_verify_or_exit helper in src/microjail/commands/lock.py. lock/exec/shell all call ensure_lockdown then pre_launch_verify_or_exit. Non-fatal capability failures surface as warnings via the ``warning`` helper.
- [x] 9.3 REFACTOR: helper consolidates the four-line try/except pattern shared by all three commands.

## Slice 10: [Done] - Warden rewrite: event-driven loop with queue drain
- [x] 10.1 RED: 7 tests in tests/unit/test_warden.py
- [x] 10.2 GREEN: Warden.supervise() runs process.wait(timeout=0.1) in a loop, drains pending events on TimeoutExpired, rechecks every gate.check(microjail) on each event. Capability check loop removed.
- [x] 10.3 REFACTOR: extracted _poll, _drain_events, _raise_if_enforcement_lost, _terminate_safely into small private methods; the security-relevant escalation path is now in one place.

## Slice 11: [Done] - LxdEnforcementLost escalation path in Warden
- [x] 11.1 RED: test_warden_escalates_on_lxd_enforcement_lost + test_terminate_failure_does_not_mask_gate_violation in tests/unit/test_warden.py
- [x] 11.2 GREEN: _raise_if_enforcement_lost reads watcher.last_exception and raises GatePolicyViolation. _terminate_safely wraps terminate_workload so a failure inside lxc.stop --force cannot mask the violation. (Added in code review follow-up.)
- [x] 11.3 REFACTOR: renamed terminate_workload callers to go through _terminate_safely; the failure-swallowing path is documented in the helper's docstring.

## Slice 12: [Done] - Update existing tests for new check()/verify() semantics
- [x] 12.1 RED: tests/unit/test_network_drop.py and tests/functional/commands/test_exec.py and test_shell.py
- [x] 12.2 GREEN: deleted bash-egress-probe tests; rewrote NetworkDrop tests around the config check. Removed capability runtime tests from test_exec/test_shell since capabilities are launch-time only now.
- [x] 12.3 REFACTOR: kept the new tests minimal (assert behavior, not plumbing).

## Slice 13: [Done] - README: "Warden polls policy every second" → event-driven
- [x] 13.1 RED: covered by docs/adr/0006-warden-event-driven-via-lxd-lifecycle.md
- [x] 13.2 GREEN: README updated. Goals list updated to remove the polling line. CONTEXT.md's capability policy violation definition rewritten to note launch-time only.
- [x] 13.3 REFACTOR: adr/0006 captures the reasoning; the inline README change is minimal.
