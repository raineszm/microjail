## 1. Workshop Adapter Helpers

- [x] 1.1 Add `connections(name, project)` to `workshop.py` — runs `workshop connections <name> --project <path>`, parses columnar output by position, returns list of active tunnel rows as `(plug, slot)` string pairs (format: `<workshop>/<sdk>:<name>`)
- [x] 1.2 Add `connect(name, project, plug_sdk, plug, slot_sdk, slot)` to `workshop.py` — wraps `workshop connect <name>/<plug_sdk>:<plug> <name>/<slot_sdk>:<slot>`
- [x] 1.3 Add `disconnect(name, project, plug_sdk, plug, slot_sdk, slot)` to `workshop.py` — wraps `workshop disconnect`; treats "not connected" as a no-op
- [x] 1.4 Add `refresh(name, project)` to `workshop.py` — wraps `workshop refresh <name> --project <path>`
- [x] 1.5 Add `endpoint_reachable(microjail, host, port)` helper — probes `host:port` from inside the container using the same bash TCP probe as `NetworkDrop`

## 2. Workshop File Modification

- [x] 2.1 Add `read_workshop_yaml(name, project)` to `workshop.py` — reads and parses `.workshop/<name>.yaml`
- [x] 2.2 Add `write_workshop_yaml(name, project, data)` to `workshop.py` — writes atomically via tempfile + rename
- [x] 2.3 Add `read_microjail_sdk(project)` — reads and parses `.workshop/microjail/sdk.yaml`; returns empty structure if absent
- [x] 2.4 Add `write_microjail_sdk(project, data)` — writes `.workshop/microjail/sdk.yaml` atomically; creates `.workshop/microjail/` directory if absent
- [x] 2.5 Add `add_tunnel_plug(project, plug_name, endpoint)` — reads sdk.yaml, adds plug entry keyed `plug_name`, writes back; no-op if already present
- [x] 2.6 Add `remove_tunnel_plug(project, plug_name)` — reads sdk.yaml, removes plug entry keyed `plug_name`, writes back; no-op if absent; returns whether any plugs remain
- [x] 2.7 Add `add_tunnel_slot(name, project, slot_name, endpoint)` — reads workshop YAML, adds slot under `system` SDK, adds `project-microjail` to sdks list if absent, writes back
- [x] 2.8 Add `remove_tunnel_slot(name, project, slot_name, remove_sdk)` — reads workshop YAML, removes slot from `system` SDK, removes `project-microjail` from sdks list when `remove_sdk=True`, writes back; no-op if absent

## 3. WorkshopEndpointCapability Implementation

- [x] 3.1 Create `src/microjail/caps/endpoint.py` — define `WorkshopEndpointCapability(msgspec.Struct)` with fields `name: str`, `endpoint: str`, `type: str = "endpoint-proxy"`
- [x] 3.2 Implement `check(microjail)` — returns `True` iff the tunnel row `<workshop>/microjail:<name>` → `<workshop>/system:<name>` appears in `workshop connections` output AND the endpoint is reachable via TCP from inside the container; MUST NOT raise
- [x] 3.3 Implement `provide(microjail)` — skip if `check()` is already `True`; otherwise: write plug to sdk.yaml, add slot + `project-microjail` to workshop YAML, call `refresh`, call `connect`
- [x] 3.4 Implement `revoke(microjail)` — in order: call `disconnect` (no-op if not connected); remove plug from sdk.yaml; remove slot from workshop YAML; if no plugs remain also remove `project-microjail` from sdks list; call `refresh`; treat absent state as no-op throughout
- [x] 3.5 Export `WorkshopEndpointCapability` from `src/microjail/caps/__init__.py`

## 4. Config Deserialization

- [x] 4.1 Import `WorkshopEndpointCapability` in `microjail.py`
- [x] 4.2 Add `Capability` branch to `dec_hook` — dispatch on `type` field; map `"endpoint-proxy"` → `msgspec.convert(obj, type=WorkshopEndpointCapability)`

## 5. Unit Tests

- [x] 5.1 Create `tests/unit/test_endpoint_capability.py` — test `check()` returns `False` when connection row absent in `workshop connections` output; `True` when both row and reachability hold
- [x] 5.2 Test `check()` returns `False` when connection row is present but endpoint is unreachable
- [x] 5.3 Test `provide()` is idempotent when `check()` already returns `True`
- [x] 5.4 Test `revoke()` is idempotent when capability was never provided
- [x] 5.5 Test config round-trip: YAML with `type: endpoint-proxy` deserializes to `WorkshopEndpointCapability` with correct `name` and `endpoint`

## 6. Functional Tests

- [x] 6.1 Create `tests/functional/caps/test_endpoint_capability.py` — test `provide()` calls adapter sequence in order: write sdk.yaml → update workshop YAML → `refresh` → `connect`
- [x] 6.2 Test `revoke()` calls adapter sequence in order: `disconnect` → remove plug from sdk.yaml → remove slot from workshop YAML → `refresh`
- [x] 6.3 Test `revoke()` removes `project-microjail` from sdks list when it is the last plug; preserves it when other plugs remain
- [x] 6.4 Test `check()` parses `workshop connections` columnar output correctly — matches by column position, ignores NOTES column
- [x] 6.5 Test `provide()` does not duplicate `project-microjail` entry when called for a second endpoint capability
