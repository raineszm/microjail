## Why

The upcoming Warden implementation requires supervising and managing the Workload asynchronously. Currently, `workshop.exec_` blocks and only returns a `CompletedProcess`, preventing the Warden from running the Workload asynchronously, monitoring policy compliance, or terminating the Workload dynamically.

## What Changes

- Add `workshop.popen` function in the workshop adapter to execute commands asynchronously inside the Workshop environment, returning a host-side Workload process handle.
- Add `MicroJail.popen` method to expose this asynchronous execution capability at the Microjail instance level.
- Ensure that `popen` raises the same errors (`WorkshopNotFoundError`, `WorkshopNotLaunchedError`) as `exec_` when the target Workshop environment doesn't exist or isn't launched.

## Capabilities

### New Capabilities
- `workshop-popen`: Asynchronous execution inside the Workshop environment returning a Workload process handle.

### Modified Capabilities
<!-- Existing capabilities whose REQUIREMENTS are changing (not just implementation).
     Only list here if spec-level behavior changes. Each needs a delta spec file.
     Use existing spec names from openspec/specs/. Leave empty if no requirement changes. -->

## Impact

- `src/microjail/adapters/workshop.py` (exposing `popen` function)
- `src/microjail/microjail.py` (exposing `MicroJail.popen` method)
- `tests/functional/adapters/test_workshop.py` (new tests verifying popen functionality, background behavior, and exception cases)
