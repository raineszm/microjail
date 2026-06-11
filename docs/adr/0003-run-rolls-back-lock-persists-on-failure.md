# Run rolls back while lock persists on failure

When applying a Lockdown policy, Microjail handles application failures differently based on the user's intent. `microjail run` automatically rolls back any partially applied capabilities or gates if the application fails, whereas `microjail lock` intentionally leaves the environment in a partially configured state.

## Considered Options

- Roll back on failure for all commands — keeps the environment perfectly clean, but makes it extremely difficult to debug why a specific capability or gate failed to apply since the evidence is destroyed.
- Never roll back on failure — simpler implementation, but forces the user to manually clean up broken state after a failed `microjail run` before they can try again.
- Bifurcate behavior by intent — `run` optimizes for clean transient execution by rolling back on failure, while `lock` optimizes for persistent setup and debugging by leaving the partial state intact.

## Consequences

Developers writing new Capabilities or Gates must implement `revoke()`/`release()` logic to support the rollback mechanism. Users debugging a failed policy application must use `microjail lock` to inspect the partial state, as `microjail run` will wipe the environment clean if it encounters an error.
