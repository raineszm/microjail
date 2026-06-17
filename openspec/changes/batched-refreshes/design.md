## Context

Currently, `WorkshopEndpointCapability.provide()` and `revoke()` each:
1. Read the relevant YAML file (microjail SDK or workshop definition).
2. Mutate a plug or slot entry.
3. Write the YAML file back to disk.
4. Call `microjail.workshop.refresh()` — a round-trip to the Workshop daemon that re-evaluates all SDK and definition YAML.

When `MicroJail.ensure()` iterates over N endpoint capabilities, this produces N `workshop refresh` calls. Each call takes ~100–500ms, so 5 capabilities already add noticeable latency. The Workshop daemon's refresh is an atomic snapshot: it reads all YAML files and rebuilds its internal state. Issuing it once after all mutations are committed to disk is semantically equivalent to calling it after each mutation.

The same pattern applies to `MicroJail.release()`, which iterates over capabilities in reverse and calls `revoke()` on each.

## Goals / Non-Goals

**Goals:**
- Reduce N `workshop refresh` calls to at most 1 during `MicroJail.ensure()` and `release()`.
- Introduce a batch abstraction that decouples YAML mutation from the refresh step.
- Preserve the existing per-capability API: `provide()` and `revoke()` still work standalone (outside a batch) without change.
- Keep `workshop connect` / `disconnect` per-capability — only the refresh is batched.
- Maintain stateless safety: no broad cached lock state.

**Non-Goals:**
- Not caching `workshop connections` output or other daemon state across capabilities.
- Not changing the `WorkshopEndpointCapability.check()` or `_reconcile_endpoint_declarations()` semantics.
- Not batching connections/disconnections — each tunnel still needs its own connect/disconnect call.

## Decisions

### Decision 1: Context manager for batching (`Workshop.batch()`)

A context manager keeps the batch lifetime scoped and ensures flush/cleanup even on exceptions. The alternative — a persistent object the caller must remember to `flush()` — risks forgotten refreshes after an early return or exception.

**Chosen**: `with microjail.workshop.batch() as batch:` — the context manager creates a `TunnelBatch` handle. On normal exit it calls `refresh()` once if any operations were staged, then replays deferred connects or disconnects. On exception it skips refresh entirely — the writes already hit disk but the daemon never picked them up, so no observable side effects.

### Decision 2: Immediate YAML writes, deferred refresh+connect

Under the staging approach (original design), `add_plug()`/`add_slot()` would accumulate mutations in memory and flush them on batch exit. This avoids intermediate dirty state on disk, but requires rewriting the tunnel mutation methods to support a staging path — and more critically, `connect()` MUST run after `refresh()` because `workshop connect` references plug/slot objects that only exist in the daemon after refresh. If connect is called inside `provide()` (before batch flush), it races the deferred refresh and fails.

```ascii
  Staging approach (broken ordering):
    provide(A): stage add_plug ─┐
                stage add_slot  ├── flush? No, later
                connect() ──────┘── FAILS — no refresh yet

  Immediate-write approach:
    provide(A): write plug/slot to YAML ── immediate
                skip refresh (deferred)
                skip connect (deferred)
    batch exit: refresh() once
                connect(A)
                connect(B)
```

**Chosen**: Existing tunnel methods (`add_plug`, `add_slot`, `remove_plug`, `remove_slot`) continue writing to YAML immediately — zero changes to their I/O pattern. `provide()` and `revoke()` accept an optional `batch` parameter. When a batch is present:
- `provide()` writes plug/slot to YAML immediately, then calls `batch.mark_dirty()` + `batch.defer_connect(...)` instead of refresh + connect.
- `revoke()` disconnects immediately, removes plug/slot from YAML immediately, then calls `batch.mark_dirty()` instead of refresh.

When no batch is present, behavior is identical to today — immediate write, refresh, connect.

### Decision 3: Stale plug removal (`_reconcile_endpoint_declarations`) stays outside the batch

`_reconcile_endpoint_declarations()` removes plugs for capabilities that no longer exist. It runs *before* the capability provide loop so stale declarations are gone before new ones are written. It already writes to YAML immediately (no refresh). Since it runs before the batch context opens, its writes are on disk before any batch operations begin. No change needed.

**Chosen**: `_reconcile_endpoint_declarations()` unchanged. Batch wraps only the per-capability provide/revoke loop.

### Decision 4: Deferred connects collected as parameter tuples, not lambdas

The batch needs to replay tunnel connect/disconnect calls after refresh. Two approaches:
- **Lambdas**: `batch.defer(lambda: t.connect(...))` — captures `t` (a TunnelInterface) and `self.name`. Python closure semantics could cause subtle bugs if the lambda is constructed in a loop that mutates captured variables.
- **Parameter tuples**: `batch.defer_connect(plug_sdk="microjail", plug=name, slot_sdk="system", slot=name)` — collects named arguments, replays via `workshop.tunnel.connect(...)` on flush.

**Chosen**: Parameter tuples. The batch stores `_deferred_connects: list[tuple[str, str, str, str]]` and replays each with a fresh `TunnelInterface` on flush. No closure capture, no surprises.

## Risks / Trade-offs

- **Orphan YAML entries on partial failure**: If `ensure()` fails partway through (e.g., cap C has bad config), caps A and B's plugs/slots are already written to YAML. The daemon never refreshed, so it doesn't know about them. On retry, the same writes happen again (idempotent) and the batch refresh picks everything up. For LOCK mode (no rollback), orphans persist on disk between retries but are harmless. For RUN mode, `_rollback()` calls `revoke()` on already-provided caps, which removes the orphans — albeit with N separate refreshes (since rollback doesn't use the batch).

- **Rollback issues N refreshes**: The `_rollback()` path in `ensure()` calls `cap.revoke()` without a batch, so each revoke issues its own refresh. This means failure path still does N refreshes — identical to today. The batch only optimizes the success path.

- **`check()` reads live daemon state between unflushed writes**: `provide()` calls `check()` first. Inside a batch, check reads the daemon's *current* state (from the last refresh). Since the batch hasn't flushed yet, the daemon doesn't know about any previous provides in the same batch. `check()` correctly returns False for not-yet-provided caps and True for already-provided (from a prior ensure). No correctness issue.

- **Disconnect ordering for revoke**: `revoke()` calls `t.disconnect()` immediately (before batch flush). This is safe because disconnect references a live tunnel that already exists in the daemon from a prior provide+refresh. The plug/slot removal from YAML also happens immediately. Refresh is deferred — the daemon won't notice the removals until batch flush, but since the tunnel is already disconnected, there's no race.
