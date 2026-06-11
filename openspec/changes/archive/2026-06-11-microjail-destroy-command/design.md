## Context

When a microjail project completes its workload, the underlying LXC/Workshop infrastructure and sensitive local files remain until manually removed. To improve security and ease of use, we are introducing a `destroy` command. By default, this command will tear down the remote environment and purge specifically designated sensitive data, preserving the project definitions so it can be easily run again. A full teardown option will also be provided.

## Goals / Non-Goals

**Goals:**
- Provide a single `microjail destroy` CLI command.
- Ensure the underlying Workshop is fully removed along with any tied snapshots or caches.
- Handle intermediate Workshop states gracefully ("Pending" and "Off") prior to removal.
- Purge sensitive workload outputs by default (the `purge_path`), preserving the project definitions.
- Provide a `--all` flag to completely nuke the entire project directory, protected by interactive confirmation.
- Allow bypassing confirmation via a `--yes-i-really-mean-it` flag.
- Allow the `purge_path` to be configurable in the microjail config, defaulting to `data`.
- Automatically create the `data/` directory during `microjail init`.

**Non-Goals:**
- Destroying the shared LXD project (`workshop.{uid}`) used by other microjails.
- Providing recovery or undelete functionality.
- Implementing a raw LXC fallback to forcefully delete containers if the `workshop` CLI fails to remove them.

## Decisions

1. **Configuration & Initialization**:
   - Add `purge_path: str = "data"` to the `MicroJail` msgspec Struct.
   - Update `microjail init` to automatically create the `project_path / purge_path` directory.

2. **CLI Implementation**:
   - Command signature: `def destroy(ctx: typer.Context, all: bool = typer.Option(False, "--all"), force: bool = typer.Option(False, "--yes-i-really-mean-it"))`.
   - If `--all` is passed without `--yes-i-really-mean-it`, use `typer.confirm()` to ask the user.

3. **Infrastructure Cleanup Sequence**:
   - **State Resolution**:
     - Check `workshop.info().status`.
     - If `Pending`, implement a polling wait loop (with timeout) until it resolves to a stable state.
     - If `Off`, execute `workshop start` before attempting removal (as `workshop remove` requires the container to not be "Off").
   - **Workshop Removal**: Call `workshop.remove(name, project)`.
   - **Snapshot Cleanup**: Delete tied LXC storage volumes/snapshots via the `lxc` adapter.

4. **Filesystem Cleanup Sequence**:
   - **Pre-check**: Verify that the workshop is completely removed (`not workshop.exists(...)`).
   - **Execution**: If `--all` is confirmed, remove the entire `project` directory. If not, only remove `project / purge_path`.

## Risks / Trade-offs

- **Risk: Polling Timeout**: If a "Pending" workshop never resolves, the command will time out and fail. This is acceptable.
- **Risk: Deleting the Wrong Directory**: Mitigated by checking for `.microjail/config.yaml` and the explicit `--yes-i-really-mean-it` flag.
