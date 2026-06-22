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
<!-- Test details and tasks will be planned after Slice 1 is complete -->
- [x] 2.1 RED: pending
- [x] 2.2 GREEN: pending
- [x] 2.3 REFACTOR: pending

## Slice 3: [Done] - LxdEnforcementLost escalation after 3 failed reconnects
<!-- Escalation counter is part of the same _run loop; test passes against slice 2 implementation. -->
- [x] 3.1 RED: pending
- [x] 3.2 GREEN: pending
- [x] 3.3 REFACTOR: pending

## Slice 4: [Done] - Protocol extension: verify() on Gate and Capability
- [x] 4.1 RED: pending
- [x] 4.2 GREEN: pending
- [x] 4.3 REFACTOR: pending

## Slice 5: [Done] - NetworkDrop: check() becomes config-only, verify() returns True
- [x] 5.1 RED: pending
- [x] 5.2 GREEN: pending
- [x] 5.3 REFACTOR: pending

## Slice 6: [Done] - ReadonlyConfig: verify() returns True
<!-- Already implemented in slice 4; stub returns True. -->
- [x] 6.1 RED: pending
- [x] 6.2 GREEN: pending
- [x] 6.3 REFACTOR: pending

## Slice 7: [Done] - WorkshopEndpointCapability: check() and verify() split
- [x] 7.1 RED: pending
- [x] 7.2 GREEN: pending
- [x] 7.3 REFACTOR: pending

## Slice 8: [Done] - MicroJail.pre_launch_verify() and PreLaunchVerifyResult
- [x] 8.1 RED: pending
- [x] 8.2 GREEN: pending
- [x] 8.3 REFACTOR: pending

## Slice 9: [Done] - Wire pre_launch_verify into lock, exec, shell
- [x] 9.1 RED: pending
- [x] 9.2 GREEN: pending
- [x] 9.3 REFACTOR: pending

## Slice 10: [Done] - Warden rewrite: event-driven loop with queue drain
- [x] 10.1 RED: pending
- [x] 10.2 GREEN: pending
- [x] 10.3 REFACTOR: pending

## Slice 11: [Done] - LxdEnforcementLost escalation path in Warden
<!-- last_exception on the watcher feeds the Warden's escalation check. -->
- [x] 11.1 RED: pending
- [x] 11.2 GREEN: pending
- [x] 11.3 REFACTOR: pending

## Slice 12: [Done] - Update existing tests for new check()/verify() semantics
<!-- Stale probe-based and capability-runtime tests removed/updated inline. -->
- [x] 12.1 RED: pending
- [x] 12.2 GREEN: pending
- [x] 12.3 REFACTOR: pending

## Slice 13: [Done] - README: "Warden polls policy every second" → event-driven
- [x] 13.1 RED: pending
- [x] 13.2 GREEN: pending
- [x] 13.3 REFACTOR: pending
