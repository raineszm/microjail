## Why

We need a reliable way to fully clean up a project's resources after we are done with it. Currently, cleaning up a microjail requires manually deleting the underlying infrastructure (workshops, snapshots, caches) and then separately removing the local project directory. A unified `destroy` command will streamline this lifecycle and prevent resource leaks.

## What Changes

- Add a new `destroy` CLI command to `microjail`.
- The command will strictly sequence cleanup: it must first successfully delete the underlying workshop environment before proceeding to local filesystem deletion.
- The infrastructure cleanup will also explicitly remove any associated snapshots or caches tied to the microjail.
- After infrastructure is destroyed, the command will recursively remove the local project directory.
- Support an optional configuration or flag to restrict the local filesystem cleanup to a specific subdirectory of the project folder, rather than deleting the entire project folder.

## Capabilities

### New Capabilities
- `destroy-command`: Covers the end-to-end lifecycle cleanup of a microjail project, including workshop/snapshot/cache teardown and local filesystem deletion.

### Modified Capabilities
None.

## Impact

- **CLI Interface**: A new `destroy` command will be exposed to users.
- **Workshop Integration**: New interactions will be added to explicitly target and delete workshops, snapshots, and caches.
- **Filesystem Utilities**: Safe, scoped recursive directory deletion logic will be introduced to handle the local cleanup phase and the optional subdirectory-only deletion.
