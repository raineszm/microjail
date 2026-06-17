# Implementation Tasks

## Slice 1: Tracer Bullet - TunnelBatch class with dirty flag + deferred connect/disconnect

- **Test**: `test_tunnel_batch_defers_connect_and_refreshes_once` in `tests/unit/test_workshop_helpers.py`
- **Arrange**:
  - Create a `Workshop` instance with a mocked `refresh` method.
  - Create a `TunnelBatch(workshop)` instance.
  - Call `batch.mark_dirty()` then `batch.defer_connect("microjail", "inf", "system", "inf")`.
- **Act**: Call `batch.flush()`.
- **Assert**:
  - `workshop.refresh()` was called exactly once.
  - `workshop.tunnel.connect()` was called with the deferred arguments.
  - When `mark_dirty()` was NOT called, `workshop.refresh()` was NOT called but deferred connects still execute.

- [x] 1.1 RED: `test_tunnel_batch_defers_connect_and_refreshes_once`
- [x] 1.2 GREEN: Implement `TunnelBatch` with `_dirty: bool`, `_deferred_connects: list[tuple]`, `defer_connect()`, `flush()` that refreshes if dirty then replays deferred connects.
- [x] 1.3 REFACTOR: Add `flush()` guard against double-call; clear lists after replay.

## Slice 2: Workshop.batch() context manager

<!-- Context manager on Workshop that creates a TunnelBatch, enters it, flushes on normal exit, skips refresh on exception. -->

- [x] 2.1 RED: Workshop.batch() context manager tests
- [x] 2.2 GREEN: Implement `@contextmanager batch()` on Workshop with try/except/else pattern
- [x] 2.3 REFACTOR: none

## Slice 3: Wire batch parameter into provide() and revoke()

<!-- Add `batch: TunnelBatch | None = None` parameter to WorkshopEndpointCapability.provide(). When batch is None, behavior is today's: write, refresh, connect. When batch is provided: write immediately, call batch.mark_dirty() + batch.defer_connect(). For revoke: disconnect immediately, remove plug/slot immediately, call batch.mark_dirty(). -->

- [x] 3.1 RED: Existing tests pass with new signature
- [x] 3.2 GREEN: Add batch parameter to provide() and revoke()
- [x] 3.3 REFACTOR: none

## Slice 4: Wire batch into MicroJail.ensure() and release()

<!-- Wrap the capability provide loop in ensure() with `with self.workshop.batch() as batch:` and pass `batch=batch` to _ensure_capability. Same for the revoke loop in release(). -->

- [x] 4.1 RED: Existing tests updated for batch-aware verification
- [x] 4.2 GREEN: Wrap cap loops in ensure() and release() with batch context
- [x] 4.3 REFACTOR: Add `from __future__ import annotations` for deferred type evaluation

## Slice 5: Integration test: two capabilities produce one refresh

<!-- Mock refresh, run ensure() with two real WorkshopEndpointCapability instances, assert refresh called once. -->

- [x] 5.1 RED: `test_ensure_with_two_endpoint_caps_triggers_one_refresh`
- [x] 5.2 GREEN: Implement test with mocked tunnel and refresh, two caps
- [x] 5.3 REFACTOR: none

## Slice 6: Empty batch skips refresh

<!-- Verify that ensure() with zero endpoint capabilities skips refresh entirely. -->

- [x] 6.1 RED: `test_ensure_zero_caps_triggers_no_refresh`
- [x] 6.2 GREEN: Implement test — already works because empty batch never marks dirty
- [x] 6.3 REFACTOR: none

## Slice 7: Standalone provide/revoke unchanged

<!-- Verify that provide() and revoke() without a batch parameter still write to disk, refresh, and connect/disconnect as before (no behavioral regression). -->

- [x] 7.1 RED: Existing test_endpoint_capability.py tests cover this
- [x] 7.2 GREEN: No code change needed — batch=None default preserves existing behavior
- [x] 7.3 REFACTOR: none
