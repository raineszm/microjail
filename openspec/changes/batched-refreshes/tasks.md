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

- [ ] 1.1 RED: `test_tunnel_batch_defers_connect_and_refreshes_once`
- [ ] 1.2 GREEN: Implement `TunnelBatch` with `_dirty: bool`, `_deferred_connects: list[tuple]`, `_deferred_disconnects: list[tuple]`, `mark_dirty()`, `defer_connect()`, `flush()` that refreshes if dirty then replays both lists.
- [ ] 1.3 REFACTOR: Add `flush()` guard against double-call; clear lists after replay.

## Slice 2: [Pending] - Workshop.batch() context manager

<!-- Context manager on Workshop that creates a TunnelBatch, enters it, flushes on normal exit, skips refresh on exception. -->

- [ ] 2.1 RED: pending
- [ ] 2.2 GREEN: pending
- [ ] 2.3 REFACTOR: pending

## Slice 3: [Pending] - Wire batch parameter into provide() and revoke()

<!-- Add `batch: TunnelBatch | None = None` parameter to WorkshopEndpointCapability.provide(). When batch is None, behavior is today's: write, refresh, connect. When batch is provided: write immediately, call batch.mark_dirty() + batch.defer_connect(). For revoke: disconnect immediately, remove plug/slot immediately, call batch.mark_dirty(). -->

- [ ] 3.1 RED: pending
- [ ] 3.2 GREEN: pending
- [ ] 3.3 REFACTOR: pending

## Slice 4: [Pending] - Wire batch into MicroJail.ensure() and release()

<!-- Wrap the capability provide loop in ensure() with `with self.workshop.batch() as batch:` and pass `batch=batch` to _ensure_capability. Same for the revoke loop in release(). -->

- [ ] 4.1 RED: pending
- [ ] 4.2 GREEN: pending
- [ ] 4.3 REFACTOR: pending

## Slice 5: [Pending] - Integration test: two capabilities produce one refresh

<!-- Mock refresh, run ensure() with two real WorkshopEndpointCapability instances, assert refresh called once. -->

- [ ] 5.1 RED: pending
- [ ] 5.2 GREEN: pending
- [ ] 5.3 REFACTOR: pending

## Slice 6: [Pending] - Empty batch skips refresh

<!-- Verify that ensure() with zero endpoint capabilities skips refresh entirely. -->

- [ ] 6.1 RED: pending
- [ ] 6.2 GREEN: pending
- [ ] 6.3 REFACTOR: pending

## Slice 7: [Pending] - Standalone provide/revoke unchanged

<!-- Verify that provide() and revoke() without a batch parameter still write to disk, refresh, and connect/disconnect as before (no behavioral regression). -->

- [ ] 7.1 RED: pending
- [ ] 7.2 GREEN: pending
- [ ] 7.3 REFACTOR: pending
