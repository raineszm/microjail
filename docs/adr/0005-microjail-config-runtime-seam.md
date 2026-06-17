# Open a seam between MicroJail config and runtime MicroJail

`MicroJail` and the nested `Workshop` were both `msgspec.Struct` types whose
field set served two roles: they defined the shape of the on-disk YAML
configuration, and they carried the runtime methods that executed against the
workshop. The executor — a runtime dependency used to run `workshop`, `lxc`,
and other subprocesses — was stored as a regular field on the same Struct, so
serializing a `MicroJail` to YAML meant blanking the executor first and
restoring it after. `MicroJail.load(path, executor=...)` decoded the YAML into
a `MicroJail` and then mutated the freshly-decoded workshop to inject the
executor. The same shape of hack existed inside `Workshop`. The result was a
class that was simultaneously a passive data record and an active facade, with
the active part leaking into the passive part's encoding.

## Considered Options

- **Leave the Struct-doubles-as-runtime design in place** — the code works,
  the executor hack is small, and tests do not require a change. The seam
  between config and runtime stays closed, and any new runtime dependency has
  to be either serialized or scrubbed in `enc_hook` / `save`.
- **Introduce DTOs at both levels (`MicroJailConfig` and `WorkshopConfig`),
  keep `MicroJail` and `Workshop` as runtime classes, place the executor on
  the runtime `Workshop` only, and put the conversion on the runtime class
  (`to_config` / `from_config`)** — closes the seam completely, removes the
  executor-blanking dance in `save()`, removes the dead `hasattr(obj, "run")`
  branch in `enc_hook`, and keeps call sites unchanged because the runtime
  classes have the same field shape as the previous Structs.
- **Introduce the DTO only at the `MicroJail` level and leave the executor
  hack inside `Workshop`** — smaller diff, but the same anti-pattern lives
  on inside the nested type and the seam is only half-open.

## Decision

Adopt the second option. The `MicroJail` Struct is replaced by a regular
`@dataclass` `MicroJail` runtime class (no longer a `msgspec.Struct`) and a
new `MicroJailConfig(msgspec.Struct, omit_defaults=True)` DTO. The runtime
class holds the same fields as the DTO plus operational methods
(`ensure`, `release`, `save`, `load`, `destroy`, `exec_`, `popen`, `shell`,
`lxc_instance`, `add_device`, `remove_device`, etc.). `to_config()` produces
the DTO form; `from_config(config, executor)` constructs the runtime and
injects the executor into the inner workshop. The `Workshop` class gets the
same treatment: a `@dataclass` runtime class with `to_config` / `from_config`,
and a new `WorkshopConfig(msgspec.Struct)` DTO that holds only `name` and
`project`. The pre-existing `WorkshopConfig` (the structure of `workshop.yaml`,
managed by the `workshop` CLI) is renamed to `WorkshopYamlConfig` to free the
name for the new DTO.

The executor is held on the runtime `Workshop` only; the runtime `MicroJail`
has no executor field of its own. `MicroJail.load(path, executor=None)`
constructs the inner `Workshop` with the injected executor. The
executor-blanking dance in the old `save()` and the dead `hasattr(obj, "run")
and hasattr(obj, "popen")` branch in `enc_hook` are deleted. `MicroJailConfig`
uses `omit_defaults=True` so the YAML no longer carries `purge_path: data`
when the value is the default; existing files still load (the default kicks
in). Backward compatibility of checked-in config files is explicitly not a
concern for this refactor.

## Consequences

Call sites in CLI commands and tests do not change: `MicroJail(workshop,
lockdown, purge_path="data")`, `MicroJail.load(path, executor=...)`,
`MicroJail.init(name, project, sdks, base, executor=...)`, and field access
(`microjail.workshop`, `microjail.lockdown`, `microjail.purge_path`,
`microjail.name`, `microjail.project_path`, etc.) all keep the same shape. The
`save()` method no longer mutates `self.workshop.executor` during encoding.
The `enc_hook` no longer needs to know about the executor at all. New
runtime dependencies (if any are added later) can be plumbed through
`from_config` instead of fighting the Struct encoding. The DTO and the
runtime class are now distinct types: the DTO is a `msgspec.Struct` that
serializes to YAML; the runtime is a `@dataclass` that holds references to
the workshop, lockdown, and purge path, plus operational methods. Equality
between two `MicroJail` instances is structural via the dataclass `__eq__`,
which compares the workshop's `name`, `project`, and `executor` — so a
round-trip through `save`/`load` is only equal to the original if the
original's executor was `None` (the common case). When a non-`None` executor
is set, the executor is correctly dropped on save and the loaded instance
gets a fresh `None` executor; this is the intended behavior because the
executor is a runtime dependency, not configuration.
