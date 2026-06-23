## Context

The `Warden` in `src/microjail/warden.py` supervises a workload by polling each gate and capability on a fixed interval (default 1s) and terminating the workload on the first violation. Polling is a poor fit for changes the LXD daemon already broadcasts as lifecycle events (start, stop, device added/removed, config updated). A polling-based Warden also has a real-time gap: a device could be added and removed in a single polling interval and the Warden would never see it.

The `refactor/event-warden-retry` branch exists to replace polling with an event-driven Warden, but it needs a reliable primitive for streaming LXD events for a single container. The codebase has no such primitive today: `src/microjail/adapters/lxc.py` is a thin wrapper over one-shot `lxc` commands (`query`, `network attach`, `device add/remove`, `stop`), and `src/microjail/adapters/workshop.py` does not touch LXD directly. A previous WebSocket-based attempt left a stale `lxd_events.cpython-314.pyc` in `__pycache__` but no source file; that approach is abandoned and out of scope.

This change adds a single new module, `src/microjail/adapters/lxd_monitor.py`, that owns a long-lived `lxc monitor` subprocess and exposes a blocking iterator over its events. The caller iterates with a `for` loop. Threading, queueing, and any kind of background producer are deliberately out of scope: the future Warden (or any other consumer that wants parallelism) can wrap the iterator in a thread + queue if and when it needs to. The library is small, synchronous, and testable without any LXD daemon.

## Goals / Non-Goals

**Goals:**
- Expose LXD lifecycle events for one `(container, project)` pair as a blocking iterator.
- Filter producer-side (inside `__next__`) so the caller only sees events for the configured container and project.
- Be fully unit-testable without a real LXD daemon or a real `lxc` binary.
- Match the existing codebase's style: stdlib-only, `subprocess`/`Popen`-based, no asyncio, no new runtime dependencies.

**Non-Goals:**
- Threading, queueing, or any background producer. The caller owns the iteration thread.
- Interpreting events. The monitor does not translate lifecycle actions into gate/cap violations; it only delivers `LifecycleEvent` objects.
- Replacing the existing `Warden.supervise()` polling loop. The Warden is unchanged in this change.
- Reading non-lifecycle event types (logging, operation, etc.). Only `type: lifecycle` is delivered.
- A public CLI surface. `lxc monitor` runs as a child process; the user never sees it.
- Reconnect / retry on subscription loss. If the subprocess dies, the iterator ends with `StopIteration`; the caller decides what to do.

## Decisions

### Decision 1: Use `lxc monitor` as a child process, not the LXD WebSocket API directly
- **Rationale**: The rest of `microjail` already shells out to the `lxc` client (`src/microjail/adapters/lxc.py` uses `lxc query`, `lxc network attach`, `lxc config device …`). `lxc monitor` is the canonical client and inherits the host's LXD credentials and project scoping for free. Direct WebSocket access would require us to reimplement cert handling, project query parameters, reconnection, and binary framing, and would pull in a runtime dependency (`websockets`) that is not currently in `pyproject.toml`.
- **Sub-decision: Use `--format=json` and parse with `msgspec.json.decode`.** `lxc monitor` defaults to YAML, but YAML from this command is a multi-document stream separated by `---`. `msgspec.yaml.decode` only decodes a single document; the multi-document stream would require us to split on `---` ourselves or reach for `pyyaml.parse_all()`, at which point the msgspec integration is doing very little work. `--format=json` emits one complete JSON object per line, which `msgspec.json.decode` (already used in `lxc.py`) decodes trivially per line. Both formats carry identical data and the same nanosecond-precision RFC3339 timestamp, so JSON costs us nothing in fidelity. The command we spawn is therefore:
  ```
  lxc monitor --project=<project> --type=lifecycle --format=json
  ```
- **Alternatives Considered**:
  - **WebSocket via `websockets.sync.client`**: tried on the (now-orphaned) `lxd_events` module, no source committed. Rejected for the dependency and credential-management reasons above; also because the rest of the codebase uses the `lxc` client and consistency is worth a small overhead per event line.
  - **`lxc monitor` over a streaming REST endpoint**: LXD does not expose lifecycle events via REST; this is a non-option.
  - **`--format=yaml` with `msgspec.yaml.decode`**: rejected because YAML output is multi-document (`---` separated) and `msgspec.yaml.decode` does not parse multi-document streams natively. Identical data to JSON; no upside to justify the parsing complexity.
  - **`--format=pretty`**: rejected — human-readable `key=value` form, not machine-parseable, and truncates timestamps to second precision.

### Decision 2: Blocking iterator (no thread, no queue)
- **Rationale**: The library is a single-purpose primitive — "give me a stream of LXD events for this container". The Python iterator protocol (`__iter__` + `__next__`) is the simplest interface for a blocking stream of values: the caller writes `for event in monitor:` and gets one event per iteration. The iterator blocks on `process.stdout.readline()` in the caller's thread, so there is no producer/consumer synchronization to design. If a future caller needs parallelism, they can wrap the iterator in a thread + queue trivially (`queue.Queue` from `iter()`); the library doesn't have to anticipate that need.
- **Alternatives Considered**:
  - **Thread + `queue.Queue` + `events(timeout)`**: rejected as scope creep. The user explicitly chose to keep the scope tight; threading and queueing belong in the consumer.
  - **Push-based callbacks (`on_event(event)`)**: rejected as harder to test and reason about than a polled iterator, and for a single-purpose library the iterator is the most natural fit.
  - **Generator function (`def events() -> Iterator[LifecycleEvent]`)**: rejected because we need to own the `subprocess.Popen` lifecycle (terminate on `close()`); a class-based iterator makes that explicit and testable.

### Decision 3: Filter on the producer side (inside `__next__`), not at the consumer
- **Rationale**: An LXD host under any load produces many events per second across all instances and all event types. A consumer that has to filter every event itself would do redundant work, and a consumer that forgets to filter would see unrelated events. Filtering inside `__next__` keeps the contract simple: every value the iterator yields is an event for the configured container and project. The filter is a tight loop that reads the next line on a non-match and continues, so non-matching events cost only an extra `readline()` + `parse_event()`.
- **Alternatives Considered**:
  - **Consumer-side filtering**: rejected — pushes the same filter logic to every caller, and a forgetting caller would silently receive unrelated events.
  - **`lxc monitor --type=…` server-side filtering**: where supported (e.g. `--type=lifecycle`), use it; the per-event filter is the safety net for hosts that do not support granular filters.


### Decision 5: `close()` terminates the subprocess; EOF raises `StopIteration`; the monitor is also a context manager
- **Rationale**: `Popen.stdout.readline()` returns `""` on EOF, so the iterator's main loop naturally exits when the subprocess is terminated and its stdout pipe is closed. `close()` calls `process.terminate()`, then `process.wait(timeout=5.0)`, then escalates to `process.kill()` if the timeout elapses. `__next__` raises `StopIteration` on EOF so the surrounding `for` loop exits cleanly. The monitor also implements the context manager protocol — `__enter__` returns `self` and `__exit__` calls `self.close()` — so callers can write `with LxdMonitor(...) as monitor: for event in monitor: ...` and have the subprocess terminated automatically, even on exceptions inside the `with` block. Callers who prefer the explicit `close()` in a `finally` block can still use that style; both work.
- **Alternatives Considered**:
  - **Skip the context manager protocol; require `close()` in a `finally` block**: rejected as a minor convenience loss. The two extra methods are 4 lines and remove a class of "forgot to close" bugs. The context manager is purely additive — callers who don't use `with` are unaffected.
  - **Background thread that calls `close()` on garbage collection**: rejected — `__del__` semantics are unreliable, especially under `gc.collect()`.

### Decision 6: No reconnect, ever, in this change
- **Rationale**: The user explicitly scoped this change to "creating the functionality to monitor lxd events and we'll worry about using it later". Reconnect policy is a consumer decision (the future Warden may want to escalate on EOF rather than retry). The iterator just ends with `StopIteration`; the caller decides what to do.
- **Alternatives Considered**:
  - **In-iterator exponential backoff reconnect**: rejected as scope creep. A different change can add a `LxdMonitorSession` wrapper that re-invokes `LxdMonitor` on EOF, if that turns out to be what the Warden wants.

## Event Schema

`lxc monitor --type=lifecycle --format=json` emits one JSON object per line. Each object has a fixed set of top-level fields; the `metadata` sub-object carries the action, source, and (usually) the resource name and project. The monitor only needs a small subset of these fields to do its job: filter by event type, match the configured container, and match the configured project. We model only what we need; the rest is silently ignored by `msgspec` (it does not reject unknown fields by default).

### Filter-driving fields (required by the schema)

| Field | Type | Source | Used for |
|---|---|---|---|
| `type` | `str` | top-level | Filter — must equal `"lifecycle"`. Defense in depth on top of `--type=lifecycle`. |
| `project` | `str` | top-level | Filter — must equal the configured LXD project. |
| `metadata.action` | `str` | nested | Recorded on the event for the consumer (e.g. `instance-created`, `instance-started`). Not used for filtering. |
| `metadata.source` | `str` | nested | Filter — must end with `/1.0/instances/<container_name>`. |

### Pass-through fields (kept, not used for filtering)

| Field | Type | Source | Notes |
|---|---|---|---|
| `timestamp` | `str` | top-level | RFC3339 with nanosecond precision, e.g. `2026-06-23T12:48:45.785189155-05:00`. Kept as `str`; parsing to `datetime` is deferred to consumers that need ordering or comparison. |
| `location` | `str` | top-level | Always present. `"none"` on a non-clustered LXD; cluster member name otherwise. Always accepted as a string. |
| `metadata.name` | `str \| None` | nested | Usually present on instance events; the container name as a separate field from `source`. Optional because not every lifecycle event carries it. |
| `metadata.project` | `str \| None` | nested | Usually duplicates the top-level `project`. Kept for cross-checking; the top-level field is authoritative for filtering. |
| `metadata.context` | `dict \| None` | nested | Varies by action (e.g. `{"location": "none", "storage-pool": "default", "type": "container"}` on `instance-created`). Untyped dict; consumers that care can inspect it. |
| `metadata.requestor` | `dict \| None` | nested | Present on user-triggered actions (e.g. `instance-started` from `lxc start`). Carries `address`, `protocol`, `username`. Untyped dict. |

### Fields intentionally NOT modeled

- **Top-level fields** other than `type`, `timestamp`, `location`, `project`, `metadata`: there are none on lifecycle events in the LXD versions we tested. If a future LXD adds a new top-level field, msgspec silently ignores it.
- **`metadata.context.*` and `metadata.requestor.*` sub-fields**: not modeled as a `msgspec.Struct` because their shape varies by action and the monitor does not need to inspect them. Kept as `dict` so the data is not lost.
- **Non-lifecycle event types** (logging, operation): not subscribed to (`--type=lifecycle` on the command line) and not modeled. The struct only sees lifecycle-shaped JSON.

### msgspec struct definition

```python
import msgspec


class LifecycleMetadata(msgspec.Struct, frozen=True):
    """Action + resource identification for one LXD lifecycle event."""

    action: str
    source: str
    name: str | None = None
    project: str | None = None
    context: dict | None = None
    requestor: dict | None = None


class LifecycleEvent(msgspec.Struct, frozen=True):
    """One LXD lifecycle event, parsed from one line of `lxc monitor --format=json`."""

    type: str
    timestamp: str
    location: str
    project: str
    metadata: LifecycleMetadata
```

The filter inside `__next__` is a pure function on `LifecycleEvent`:

```python
INSTANCE_PREFIX = "/1.0/instances/"


def matches(event, container_name, lxd_project):
    if event.type != "lifecycle":
        return False
    if event.project != lxd_project:
        return False
    if not event.metadata.source.startswith(INSTANCE_PREFIX):
        return False
    # source is "/1.0/instances/<name>"; split on "/" and take the segment
    # after the prefix.
    return event.metadata.source.split("/")[3] == container_name
```

(`split("/")[3]` is intentional: index 0 is empty for a leading-slash path, index 1 is `1.0`, index 2 is `instances`, index 3 is the name. A naive `endswith(container_name)` would let `evil-name-foo` match container `name`.)

### Decision 4: Inject the subprocess via the `CommandExecutor` protocol from a standalone `executor` module
- **Rationale**: The `CommandExecutor` protocol and `LocalExecutor` default live in their own module, `src/microjail/adapters/executor.py`, alongside `workshop.py` and `lxc.py` in the adapters package. They are not workshop-specific: `MicroJail.load` and `MicroJail.from_config` take an `executor: CommandExecutor`, the workshop adapter uses them, and the new `LxdMonitor` does too. Re-using one protocol across adapters keeps the test-injection pattern consistent. `LxdMonitor.__init__` takes an optional `executor: CommandExecutor` parameter that defaults to `LocalExecutor()`. On `__iter__` the monitor calls `executor.popen(cmd, stdout=PIPE, text=True, bufsize=1)`; the executor passes those kwargs through to `subprocess.Popen`. Tests substitute a fake executor that records the call and returns a fake `Popen` whose `stdout` is an iterable of preset lines.
- **Alternatives Considered**:
  - **Define `CommandExecutor` and `LocalExecutor` inside `workshop.py`**: rejected — `workshop.py` would have to re-export them, and the new monitor would have to import from the wrong module to reuse the same type. A standalone module makes the shared dependency explicit and keeps the adapters package flat.
  - **Let `LxdMonitor` call `subprocess.Popen` directly and have tests monkey-patch**: rejected — monkey-patching hides the dependency and breaks for any non-mock test environment. The explicit injection point makes the seam visible in the constructor.

## Risks / Trade-offs
- **[Risk] Subprocess leaks if the consumer forgets to call `close()`.** → *Mitigation*: the monitor also implements the context manager protocol (see Decision 5), so callers can write `with LxdMonitor(...) as monitor:` and have `close()` invoked automatically. Callers who don't use `with` are documented as responsible for calling `close()` in a `finally` block.
- **[Risk] A consumer that iterates with a long blocking loop starves other coroutines on the same thread.** This is the same risk as any synchronous iteration over a blocking source, and the consumer opted in by not wrapping the iterator in a thread. → *Mitigation*: documented in the spec; the consumer can wrap in a thread + queue trivially.
- **[Risk] Subprocess death on a transient LXD hiccup ends the iterator with `StopIteration`.** This is intentional per Decision 6; the consumer must be ready to handle it. → *Mitigation*: the spec requires `close()` to be idempotent and the iterator to raise `StopIteration` on EOF, so the consumer has a stable, well-defined end state to handle.
- **[Risk] `lxc monitor` JSON line format changes between LXD versions.** Different LXD versions may emit slightly different keys, or wrap metadata differently for older events. → *Mitigation*: `msgspec.Struct` (not `strict=True`) silently ignores extra fields, so new top-level or `metadata.*` keys added by a future LXD do not break parsing. The filter-driving fields (`type`, top-level `project`, `metadata.source`) are all documented as always present on lifecycle events across LXD 5.x.
- **[Risk] `lxc monitor` does not emit synthetic events for resources that already exist when the subprocess starts.** If a workload container is already running when the iterator is created, the first event yielded will be the *next* transition, not a snapshot of the current state. → *Mitigation*: out of scope for this change. The future Warden-integration change is responsible for establishing baseline state (via `lxc list` / `lxc query` before the iterator starts) and treating the first event as a delta from that baseline. Documented here so the integration change does not assume "the iterator tells you the current state."
- **[Risk] The `project` field appears at both the top level and inside `metadata`, and they should be consistent but LXD does not formally promise they are.** In testing they always agreed, but a future LXD or a clustered deployment could in principle emit an event where they disagree. → *Mitigation*: the filter uses the top-level `project` field as authoritative. The `metadata.project` field is kept on the struct for cross-checking by consumers but is not used for filtering. If the two disagree, the monitor does not raise — it filters by the top-level value and lets the consumer inspect the discrepancy if it cares.

## Migration Plan

This change is purely additive: a new module, a new test file, no changes to any existing code, CLI, or spec. Deployment is "merge the branch and ship". Rollback is "revert the merge commit"; no data migration, no schema change, no flag.


- **None for this change.** The interface, the error model, and the testability story are settled by the proposal and the spec. The follow-up Warden-integration change will need to decide:
  - Whether to drain the queue inside the existing `Warden.supervise()` poll, or to replace the poll with a blocking drain and drop the explicit `process.wait(timeout=interval)` step.
  - What exit code to use for subprocess-EOF enforcement loss. The current `warden-monitoring` spec uses 84 for gate violations and 82 for capability violations; an LXD-event-stream loss is closer to "we lost the ability to enforce at all" and may warrant its own code.
  These are decisions for that change, not this one.
