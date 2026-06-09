## Context

Microjail's `Lockdown` model has a `Capability` protocol and a `caps: list[Capability]` field on `Lockdown`, but no concrete `Capability` implementation exists yet. The `dec_hook` in `microjail.py` already handles gate type-dispatch; the same pattern needs a parallel branch for capabilities.

Workshop supports tunnel interfaces: a plug declared on one SDK and a slot declared on the `system` SDK can be wired together with `workshop connect`, forwarding a `host:port` from the host into the container at the identical address. Tunnels survive NIC removal (the network-egress gate mechanism), so they are the correct substrate for authorised egress paths.

Workshop configuration lives in the `.workshop/` subdirectory of the project. The workshop definition is `.workshop/<name>.yaml`. In-project SDKs live at `.workshop/<sdk-name>/sdk.yaml` and are referenced in the workshop definition with the `project-` prefix (e.g. `project-microjail`); everywhere else — `workshop connect`, `workshop connections` output, `connections:` entries — the bare SDK name is used.

**Outgoing connections (regular SDK plug → system slot) cannot be declared in the workshop definition's `connections:` block and are not auto-connected.** They must be established explicitly with `workshop connect` after every `workshop refresh`. This means the connection is not durable across refreshes; `check()` → `provide()` in `ensure()` re-establishes it, and the Warden detects a dropped connection as a capability policy violation if it occurs during a run.

The `workshop connections` output format:

```
INTERFACE  PLUG                        SLOT                  NOTES
tunnel     <workshop>/microjail:<name> <workshop>/system:<name>  manual
```

Connection command: `workshop connect <workshop>/microjail:<name> <workshop>/system:<name>`

The endpoint inside the container is the same `host:port` as on the host — no remapping required.

---

## Goals / Non-Goals

**Goals:**
- Implement `WorkshopEndpointCapability` satisfying the `Capability` protocol.
- `check()` verifies the Workshop connection exists and the endpoint is reachable from inside the container.
- `provide()` writes the in-project SDK file, updates the workshop definition, refreshes Workshop, and connects plug to slot.
- `revoke()` disconnects first, then removes declarations, then refreshes.
- Wire `type: endpoint-proxy` deserialization into the `dec_hook`.
- Add the minimal workshop adapter helpers (`connections`, `connect`, `disconnect`, `refresh`, `endpoint_reachable`, workshop YAML read/write).

**Non-Goals:**
- Warden runtime monitoring of endpoint capabilities (separate concern; current monitoring is no-op stub).
- Workshop adoption detection of pre-existing tunnels (the `--adopt` path; `WorkshopEndpointCapability` only manages tunnels it declares).
- Support for tunnel types other than `host:port` endpoint forwarding.
- Capability application failure severity configuration (defaults: application failure is fatal, runtime violation is a warning — no per-capability config added in this change).

---

## Decisions

### 1. Config shape: `type` field as discriminator, `name` as plug/slot identifier

```yaml
caps:
  - type: endpoint-proxy
    name: inference
    endpoint: localhost:8080
```

The `type` field distinguishes capability kinds in the decode hook (parallel to how gates use the `name` field as a discriminator). `name` is user-chosen, becomes the Workshop plug/slot identifier, and is stable across `check`/`provide`/`revoke`. `endpoint` is `host:port`.

**Alternative considered:** use `name` as discriminator (like gates). Rejected: gate names are fixed strings (`network-egress`, `readonly-config`). Capability names are user-chosen identifiers; they cannot double as type tags without conflating identity with kind.

### 2. In-project SDK for plug declarations; workshop definition for system slot

`provide()` writes plug declarations to a dedicated in-project SDK at `.workshop/microjail/sdk.yaml`. The system slot goes in the workshop definition at `.workshop/<name>.yaml`. These are two separate files with different lifetimes.

**`.workshop/microjail/sdk.yaml`** — owned entirely by microjail; accumulates one plug per endpoint capability:

```yaml
name: microjail
plugs:
  inference:
    interface: tunnel
    endpoint: localhost:8080
```

**`.workshop/<name>.yaml`** — modified by microjail to add the `project-microjail` SDK reference (once, shared across all endpoint capabilities) and one system slot per capability:

```yaml
sdks:
  - name: direnv               # pre-existing from init
  - name: project-microjail   # added by first provide(); project- prefix required here only
  - name: system
    slots:
      inference:               # one entry per endpoint capability
        interface: tunnel
        endpoint: localhost:8080
```

After `workshop refresh`, the connection is established with `workshop connect`:

```
workshop connect <workshop>/microjail:inference <workshop>/system:inference
```

Note: the `project-` prefix appears **only** in the workshop definition's `sdks` list. The bare name `microjail` is used in `workshop connect`, `workshop connections` output, and all other Workshop commands.

Multiple endpoint capabilities share the single `project-microjail` entry in the sdks list and accumulate plugs in the shared `sdk.yaml`. `provide()` and `revoke()` modify only the entries keyed by `self.name`.

**Alternative considered:** inline plug declarations on the `microjail` SDK entry in the workshop definition YAML (no separate sdk.yaml). Rejected: plugs declared inline in a workshop definition belong to the workshop, not to a named SDK; an in-project SDK is the correct Workshop abstraction for a collection of plugs owned by microjail.

**Alternative considered:** `connections:` block in the workshop definition to make the connection survive refreshes. Rejected: outgoing connections (regular SDK plug → system slot) cannot be auto-connected via the `connections:` block; this is a confirmed Workshop constraint.

**Alternative considered:** one in-project SDK per endpoint capability. Rejected: creates many SDK directories and complicates cleanup.

### 3. Workshop file modification: read-parse-modify with PyYAML; atomic write

Both `.workshop/microjail/sdk.yaml` and `.workshop/<name>.yaml` are modified with read-parse-modify. Writes go through a tempfile + atomic rename to avoid partial-write corruption. PyYAML is already a dependency.

**Risk:** YAML round-trip may reformat comments or style. Acceptable: microjail owns both files post-init.

### 4. Reachability check: TCP probe via `workshop exec`

`check()` verifies the connection in two steps:
1. Parse `workshop connections <name>` output — confirm a `tunnel` row exists with `PLUG == <workshop>/microjail:<name>` and `SLOT == <workshop>/system:<name>`. The `NOTES` column is ignored; parsing is by column position.
2. Probe TCP reachability from inside the container: `bash -c ": >/dev/tcp/<host>/<port>"` via `workshop exec`, same mechanism as `NetworkDrop`.

Both conditions must hold for `check()` to return `True`. `check()` MUST NOT raise.

**Alternative considered:** check only connection existence, skip reachability probe. Rejected: a connected but unreachable endpoint would allow the workload to launch against a dead service.

### 5. `check()` and `provide()` are idempotent; connection is not durable across refreshes

If `check()` returns `True`, `provide()` skips all operations. `workshop connect` errors if already connected; the check prevents double-connect.

The tunnel connection established by `workshop connect` is a runtime connection, not a definition-level connection. It is dropped by `workshop refresh`. This is expected behaviour: `ensure()` (called by `microjail lock` and `microjail run`) always runs `check()` → `provide()` and will reconnect. A mid-run refresh that drops the connection is detected by the Warden as a capability policy violation.

### 6. `revoke()` order: disconnect before modifying files, refresh last

```
1. workshop disconnect <workshop>/microjail:<name> <workshop>/system:<name>
   (no-op if not connected — workshop disconnect treats absent connection gracefully)
2. Remove plug from .workshop/microjail/sdk.yaml
3. Remove system slot from .workshop/<name>.yaml
4. If no plugs remain in sdk.yaml:
     remove project-microjail from sdks list in .workshop/<name>.yaml
5. workshop refresh <name>
```

Disconnect must come first: refreshing with a `connections:` entry that references a now-absent plug/slot would be ambiguous. Refreshing last syncs Workshop's installed state with the updated definition files.

---

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| `workshop connect` is not idempotent | `check()` before `provide()` prevents double-connect |
| Connection dropped by `workshop refresh` during a run | Warden detects capability policy violation; warning by default, configurable fatal |
| Endpoint not immediately reachable after connect | Reachability probe in `check()` after `provide()` catches this as a capability application failure |
| YAML round-trip reformats workshop files | Acceptable — microjail owns both files; atomic write prevents partial corruption |
| `workshop connections` output format change | Parse defensively by column position; treat parse failure as `check() → False` |
| Multiple endpoint capabilities sharing sdk.yaml | Each `provide()`/`revoke()` modifies only the entry keyed by `self.name`; other plugs are preserved |
