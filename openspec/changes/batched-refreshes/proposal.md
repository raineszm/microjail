## Why

Applying or releasing multiple endpoint capability declarations currently triggers one `workshop refresh` per capability. Each refresh round-trips to the Workshop daemon and re-evaluates the entire project SDK and workshop definitions, making multi-capability projects unnecessarily slow. Batching plug/slot YAML mutations and issuing a single refresh when anything changed preserves correctness while reducing per-operation overhead.

## What Changes

- Introduce a `Workshop.batch()` context manager that defers `workshop refresh` and tunnel connect/disconnect while letting existing YAML writes (add_plug/add_slot/remove_plug/remove_slot) execute immediately — no change to their I/O pattern.
- On batch exit, if any operations occurred, issue exactly one `workshop refresh`, then execute all deferred connect calls (provide path) or deferred disconnect calls (revoke path).
- Refactor `WorkshopEndpointCapability.provide()` and `revoke()` to work within a batch when called through `MicroJail.ensure()`/`release()` — but remain safe for standalone use outside a batch (backward-compatible).
- Refactor `MicroJail.ensure()` and `release()` to wrap per-capability provide/revoke loops in a batch so N capabilities produce 1 refresh instead of N.
- Add tests proving that multiple endpoint capabilities trigger exactly one `workshop refresh` during `ensure()` and `release()`.

**Non-goals**: No broad cached lock state. Connects/disconnects are issued per-capability, sequenced after the single batch refresh.

## Capabilities

### New Capabilities
- `refresh-batching`: Batch `workshop refresh` calls across multiple endpoint capability provides and revokes within a single `ensure()` or `release()` operation.

### Modified Capabilities
(None — requirement semantics are unchanged; only the implementation path changes.)

## Impact

- **src/microjail/adapters/workshop.py**: Add `Workshop.batch()` context manager and `TunnelBatch` class holding a dirty flag, deferred connect list, and deferred disconnect list. Flush calls `refresh()` once then replays the deferred lists.
- **src/microjail/caps/endpoint.py**: Update `WorkshopEndpointCapability.provide()` and `revoke()` to accept a batch parameter — when provided, they write to YAML immediately but defer refresh and connect/disconnect to the batch.
- **src/microjail/microjail.py**: Wrap capability loops in `ensure()` and `release()` with a batch context.
- **tests/**: Add functional tests verifying single-refresh behavior for N capabilities; update existing tests that may rely on per-provide refresh counts.
