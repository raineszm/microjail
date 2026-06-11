# 0004 Default teardown preserves project definitions

When a microjail workload completes, users need a safe way to destroy the heavy infrastructure and purge any sensitive outputs without accidentally destroying the microjail configuration they just set up.

## Considered Options

- **`destroy` wipes the entire project folder by default** — Classic teardown behavior. Ensures nothing is left behind, but forces the user to run `microjail init` and reconfigure everything from scratch if they just wanted to reset their environment and run the workload again.
- **`destroy` targets only the infrastructure and an explicit `purge_path`** — Preserves the project definition (`.microjail/`, `.workshop/`) but deletes the container, snapshots, and a dedicated data directory. Requires a separate flag (`--all`) for total obliteration.

## Decision

We chose to target only the infrastructure and an explicit `purge_path` by default.

To ensure sensitive data isn't leaked into the broader project folder, we default the `purge_path` to `data` and automatically create this directory on the host during `microjail init`.

## Consequences

- **Workload Reset vs. Project Teardown:** The `destroy` command acts primarily as a "safe reset", making it trivial to spin up the exact same environment again.
- **Security by convention:** By automatically provisioning the `data/` directory, we guide users toward placing sensitive workload outputs in a location we reliably know how to purge.
- **Complexity in total teardown:** Users who truly want to remove the project folder must use `microjail destroy --all`, introducing slight friction to an inherently destructive action.
