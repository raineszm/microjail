# Research: CTF Thin Wrapper

**Phase 0 output for** `specs/20260604-124513-ctf-thin-wrapper/plan.md`

All unknowns resolved from codebase reading. No external dependencies or tools needed.

## R-001 — Should workshop_client gain a connect_inference(name, workspace) wrapper, or should callers use connect() directly with inline constants?

**Decision**: Use connect() directly. Do not add connect_inference().

**Rationale**: There is exactly one caller pattern. The plug/slot name ('llama-cpp') is a stable literal that matches what generate_workshop_yaml emits. A wrapper in client.py would either hard-code that name (coupling client to config) or import it from config/workshop.py (circular-adjacent coupling). The existing connect() signature is already minimal (4 args). CTF currently calls connect(env_name, 'local-inference:llama', 'system:llama', workspace) inline with no indirection — the project-SDK migration simply changes those string literals to match microjail's convention ('llama-cpp'/'llama-cpp'). Adding a wrapper buys nothing for a single call site.

**Alternatives considered**: connect_inference(name, workspace) wrapper that hard-codes plug_ref='project-llama-cpp:llama-cpp' and slot_ref='system:llama-cpp'. Rejected: couples client.py to config naming constants with no DRY benefit.

---

## R-002 — generate_sdk_yaml port extraction — inference_endpoint format is host:port. How extract port? What if no port? What if inference_endpoint is None?

**Decision**: Use str.rpartition(':') to extract port. If no colon is present (empty right partition), raise ValueError. If inference_endpoint is None, the function must not be called — signature is str, not str | None.

**Rationale**: rpartition(':') correctly handles IPv6-style addresses (e.g. '[::1]:8080') because it splits on the last colon. CTF's generate_inference_sdk_yaml already receives an int port extracted upstream by urlparse; the new microjail version receives the host:port string and must re-extract. Code: host, sep, port_str = endpoint.rpartition(':'); if not sep: raise ValueError(f"inference_endpoint {endpoint!r} contains no port"); port = int(port_str). The sdk.yaml plug endpoint is 'localhost:{port}' (container-side address, not the host-side endpoint). If inference_endpoint is None the caller (init/_write_config_files) must not invoke generate_sdk_yaml — gated by 'if config.inference_endpoint is not None'.

**Alternatives considered**: Split on ':' (first occurrence) — fails on IPv6. Default to 8080 on missing colon — silently wrong. Accept str | None and return empty string — caller loses port info. All rejected.

---

## R-003 — --inference-url parsing for init: what validation is needed and how is inference_endpoint stored?

**Decision**: Replicate CTF's urlparse pattern exactly. Store as 'host:port' string (no scheme, no path). Validation: scheme in {'http','https'}, parsed.hostname truthy, port defaults to 80/443 by scheme if absent.

**Rationale**: CTF already has the canonical pattern (ctf/main.py lines 155-165): parsed = urlparse(inference_url); scheme check; inference_host = parsed.hostname; inference_port = parsed.port or (443 if https else 80). Init stores the result as inference_endpoint = f'{inference_host}:{inference_port}' in EnvironmentConfig and then in state.json. No additional validation is needed: urlparse handles malformed URLs gracefully, the scheme+hostname check rejects bare hostnames and non-HTTP schemes, and the port default covers the common case of omitting :80. Path and query components are intentionally dropped — Workshop expects a bare TCP address.

**Alternatives considered**: Regex validation of URL — redundant with urlparse. Storing full URL including scheme — Workshop connect does not need scheme. Requiring explicit port — breaks common http://host:8080 without port omission. All rejected.

---

## R-004 — Should sdk.yaml be written in _write_config_files (before launch) or after?

**Decision**: Yes — write sdk.yaml inside _write_config_files, before launch.

**Rationale**: Workshop reads project SDK directories during 'workshop launch' when it processes the 'project-<sdk_name>' entry in workshop.yaml. If sdk.yaml does not exist at launch time, Workshop will fail or ignore the SDK entirely. CTF confirms this timing: in ctf/main.py it writes sdk_dir/sdk.yaml (lines 214-216) before calling workshop_client.launch() (line 219). _write_config_files already writes the workshop.yaml; it is the correct cohesion point for all Workshop-required files. The directory to create is '.workshop/<sdk_name>/sdk.yaml' alongside the existing '.workshop/<name>.yaml'.

**Alternatives considered**: Write sdk.yaml in a separate step after _write_config_files but before launch — functionally identical but splits related file writes. Write after launch — wrong; Workshop has already processed the project SDK reference. Both rejected.

---

## R-005 — EnvironmentConfig is frozen=True. Adding inference_endpoint with default None — field() or bare = None? Where in field order?

**Decision**: Bare '= None' appended as the last field. No field() wrapper needed.

**Rationale**: Python dataclass rule: fields with defaults must follow all fields without defaults. EnvironmentConfig currently has four fields all without defaults (name, base_image, inference, agent — note that 'X | None' type annotation does NOT imply a default; the field is still required). Appending 'inference_endpoint: str | None = None' as the fifth field satisfies the ordering rule. field(default=None) is syntactically equivalent for a frozen dataclass when no other field metadata (repr, compare, hash, init suppression) is needed. Existing call sites (tests, init.py) that construct EnvironmentConfig(name, base_image, inference, agent) continue to work unchanged because inference_endpoint is optional.

**Alternatives considered**: Insert after 'inference' field — violates ordering (bare fields follow). Use field(default=None) — functionally identical, adds noise. Make all four existing fields keyword-only with KW_ONLY sentinel to allow inserting anywhere — excessive restructuring for one new field. All rejected.

---

## R-006 — Which tests in test_config_workshop.py break after project-SDK migration, and what are the new expected values?

**Decision**: Four tests break and require updating. One test passes but should be tightened. One test is unaffected.

**Rationale**: After migration, generate_workshop_yaml emits 'project-llama-cpp' (a reference entry with no inline plugs) instead of an inline 'llama-cpp' SDK with plugs block. The system slot endpoint comes from config.inference_endpoint instead of the hardcoded 'localhost:8080'. Detailed breakdown:

1. test_tunnel_keys_present_when_inference_set (line 65): asserts 'plugs' in yaml_str. BREAKS — plugs moves to sdk.yaml, not in workshop.yaml. Fix: remove 'plugs' from the required set; assert only 'tunnel' and 'slots' in yaml_str (or add 'project-llama-cpp' check). New: for required in ('tunnel', 'slots'): assert required in yaml_str.

2. test_inference_sdk_endpoint (line 117): asserts system_sdk['slots']['llama-cpp']['endpoint'] == 'localhost:8080'. BREAKS — endpoint is now config.inference_endpoint, not hardcoded. Fix: update _full_config() to pass inference_endpoint='localhost:8080', then the assertion value stays 'localhost:8080'. OR keep _full_config() without inference_endpoint and assert the endpoint equals the value passed (None case — but None would mean no endpoint emitted, so _full_config() MUST include inference_endpoint='localhost:8080').

3. test_inference_sdk_plugs (line 124): next(s for s in doc['sdks'] if s['name'] == 'llama-cpp'). BREAKS with StopIteration — no SDK named 'llama-cpp' exists anymore; it is 'project-llama-cpp' with no plugs key. Fix: assert next(s for s in doc['sdks'] if s['name'] == 'project-llama-cpp') exists and has no 'plugs' key (plugs are in sdk.yaml now). The test purpose shifts to verifying the project reference is emitted, not inline plugs.

4. test_sdk_ordering (line 138): asserts sdk_names == ['opencode', 'skills', 'llama-cpp', 'system']. BREAKS — third entry is now 'project-llama-cpp'. Fix: assert sdk_names == ['opencode', 'skills', 'project-llama-cpp', 'system'].

5. test_inference_sdk_slots (line 131): asserts system_sdk['slots']['llama-cpp']['interface'] == 'tunnel'. UNAFFECTED — system SDK and its slot name/interface do not change.

6. test_inference_sdk_absent_when_no_inference (line 145): asserts 'llama-cpp' not in sdk_names. STILL PASSES technically (neither 'llama-cpp' nor 'project-llama-cpp' appears when inference=None), but should be tightened to also assert 'project-llama-cpp' not in sdk_names to accurately describe post-migration behavior.

**Alternatives considered**: Keep hardcoded 'localhost:8080' in generate_workshop_yaml as fallback when inference_endpoint is None — would make test_inference_sdk_endpoint pass unchanged but is semantically wrong (init without --inference-url should not emit an endpoint at all). Rejected.

---

## R-007 — CTF connect call after refactor (correction to R-001)

**Decision**: Both `microjail init` (FR-014) and `ctf/main.py` call `workshop_client.connect()` using shared constants `INFERENCE_PLUG_REF = "local-inference:llama"` and `INFERENCE_SLOT_REF = "system:llama"` exported from `microjail.config.workshop`. CTF replaces its inline hardcoded string literals with these imports; it does NOT drop the connect invocation, because CTF manages its own temp workspace (not through `microjail init`). The “drop” in FR-010 means CTF drops the hardcoded duplicates, not the operation.

**Rationale**: Workshop does NOT auto-connect project-SDK plugs to slots (confirmed by spec clarification session). CTF bypasses `microjail init` and calls `workshop_client.launch()` directly, so the connect step added to init does not benefit CTF's temp-workspace flow. The shared constants ensure the plug/slot naming is defined once in microjail and imported by both callers.

**Alternatives considered**: A `workshop_client.connect_inference(name, workspace)` wrapper was rejected (R-001) because it couples the client module to config naming. Constants in `microjail.config.workshop` keep the coupling at the config layer.

---
