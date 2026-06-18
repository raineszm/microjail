# Implementation Tasks

## Slice 1: Tracer Bullet - LxdEventWatcher connects and emits the "reconnect" sentinel
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

- [ ] 1.1 RED: test_watcher_emits_reconnect_sentinel_on_initial_connect
- [ ] 1.2 GREEN: Create `src/microjail/adapters/lxd_events.py` with `class LxdEventWatcher` and `class LxdEnforcementLost(Exception)`. Constructor takes `container_name: str`, `lxd_project: str`, and an optional `connect: Callable[..., Any] = websockets.sync.client.connect` (the default uses the real client; tests inject a mock). `start()` spawns a `threading.Thread` that runs the connect loop and pushes events onto `self.events: queue.Queue[str]`. On every successful connect, the loop pushes the literal string `"reconnect"`. `stop()` sets a stop flag, closes the WebSocket, and joins the thread. Add `websockets` to `pyproject.toml` and run `uv sync`. Confirm the test passes.
- [ ] 1.3 REFACTOR: Imports alphabetical, ruff clean, type hints on the constructor parameters, no behavior changes.

## Slice 2: [Pending] - LxdEventWatcher reconnect backoff and sentinel on reconnect
<!-- Test details and tasks will be planned after Slice 1 is complete -->
- [ ] 2.1 RED: pending
- [ ] 2.2 GREEN: pending
- [ ] 2.3 REFACTOR: pending

## Slice 3: [Pending] - LxdEnforcementLost escalation after 3 failed reconnects
<!-- Test details and tasks will be planned after Slice 2 is complete -->
- [ ] 3.1 RED: pending
- [ ] 3.2 GREEN: pending
- [ ] 3.3 REFACTOR: pending

## Slice 4: [Pending] - Protocol extension: verify() on Gate and Capability
<!-- Test details and tasks will be planned after Slice 3 is complete -->
- [ ] 4.1 RED: pending
- [ ] 4.2 GREEN: pending
- [ ] 4.3 REFACTOR: pending

## Slice 5: [Pending] - NetworkDrop: check() becomes config-only, verify() returns True
<!-- Test details and tasks will be planned after Slice 4 is complete -->
- [ ] 5.1 RED: pending
- [ ] 5.2 GREEN: pending
- [ ] 5.3 REFACTOR: pending

## Slice 6: [Pending] - ReadonlyConfig: verify() returns True
<!-- Test details and tasks will be planned after Slice 5 is complete -->
- [ ] 6.1 RED: pending
- [ ] 6.2 GREEN: pending
- [ ] 6.3 REFACTOR: pending

## Slice 7: [Pending] - WorkshopEndpointCapability: check() and verify() split
<!-- Test details and tasks will be planned after Slice 6 is complete -->
- [ ] 7.1 RED: pending
- [ ] 7.2 GREEN: pending
- [ ] 7.3 REFACTOR: pending

## Slice 8: [Pending] - MicroJail.pre_launch_verify() and PreLaunchVerifyResult
<!-- Test details and tasks will be planned after Slice 7 is complete -->
- [ ] 8.1 RED: pending
- [ ] 8.2 GREEN: pending
- [ ] 8.3 REFACTOR: pending

## Slice 9: [Pending] - Wire pre_launch_verify into lock, exec, shell
<!-- Test details and tasks will be planned after Slice 8 is complete -->
- [ ] 9.1 RED: pending
- [ ] 9.2 GREEN: pending
- [ ] 9.3 REFACTOR: pending

## Slice 10: [Pending] - Warden rewrite: event-driven loop with queue drain
<!-- Test details and tasks will be planned after Slice 9 is complete -->
- [ ] 10.1 RED: pending
- [ ] 10.2 GREEN: pending
- [ ] 10.3 REFACTOR: pending

## Slice 11: [Pending] - LxdEnforcementLost escalation path in Warden
<!-- Test details and tasks will be planned after Slice 10 is complete -->
- [ ] 11.1 RED: pending
- [ ] 11.2 GREEN: pending
- [ ] 11.3 REFACTOR: pending

## Slice 12: [Pending] - Update existing tests for new check()/verify() semantics
<!-- Test details and tasks will be planned after Slice 11 is complete -->
- [ ] 12.1 RED: pending
- [ ] 12.2 GREEN: pending
- [ ] 12.3 REFACTOR: pending

## Slice 13: [Pending] - README: "Warden polls policy every second" → event-driven
<!-- Test details and tasks will be planned after Slice 12 is complete -->
- [ ] 13.1 RED: pending
- [ ] 13.2 GREEN: pending
- [ ] 13.3 REFACTOR: pending
