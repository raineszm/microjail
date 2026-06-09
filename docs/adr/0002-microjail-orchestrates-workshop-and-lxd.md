# Microjail orchestrates Workshop and LXD

Microjail does not implement sandboxing or proxying primitives itself. Workshop and LXD provide the underlying mechanisms; Microjail configures, composes, monitors, and releases them so users do not have to manually assemble error-prone secure environments.

## Considered Options

- Treat Microjail as the sandbox/proxy implementation — gives Microjail maximum control, but duplicates mechanisms already provided by Workshop and LXD.
- Treat Microjail as orchestration over Workshop and LXD — keeps the actual sandbox/proxy functionality in existing substrates while making the secure workflow easier and less error-prone.
- Make Workshop optional as one backend among several — more flexible, but contradicts the current code and design, which anchor execution to a Workshop project/container.

## Consequences

Future sandboxing or proxy features should first be expressed through Workshop or direct LXD configuration. Direct LXD access is allowed when Workshop does not surface the required control, as long as the operation targets the Workshop-backed environment. Microjail should add new primitives only if they cannot be represented by Workshop or LXD.
