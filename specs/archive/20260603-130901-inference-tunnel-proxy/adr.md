# ADR: Inference tunnel proxy

Date: 2026-06-03
Status: Accepted

## Context

The original inference path depended on Unix-domain-socket bind mounts. That did not match Workshop's tunnel model and made the gate name/mechanism misleading.

## Decision

- Route inference through Workshop's `tunnel` interface instead of a UDS bind mount.
- Generate a `system` SDK slot and project SDK plug for inference when inference is configured.
- Keep `EnvironmentState.socket_url` and agent config as HTTP URLs; Workshop makes the endpoint reachable.
- Replace the inference gate's UDS checks with a TCP connection attempt to the configured host/port.
- Rename the gate/module from `inference_socket` to `inference_tunnel` and the result name from `inference-socket` to `inference-tunnel`.
- During lock/unlock, enumerate all LXD NIC devices for route mutation; do not remove non-NIC tunnel devices.

## Consequences

- Inference remains available while normal container egress is locked down.
- Gate checks prove reachability rather than file presence.
- The tunnel device survives lock because egress control only mutates NIC devices.
- Future inference providers can reuse the plug/slot pattern without adding UDS code paths.
