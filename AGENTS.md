## Commit Trailers

Every AI-assisted commit MUST include an `Assisted-By` trailer:

```
Assisted-By: <harness> (<model>; <provider>)
```

Examples:

```
Assisted-By: opencode (claude-sonnet-4-5; anthropic)
Assisted-By: opencode (gpt-4o; openai)
```

The trailer MUST appear in the commit message body, after a blank line separating it from the
summary. If multiple models contributed, include one trailer per model.

## Style Guidance

### Naming Conventions

This is application code, not a library. Avoid underscore-prefixed names (`_foo`, `_bar`) to
signal "private" — that convention exists to protect library consumers from implementation
details that might change. In an application there are no external consumers; every function
is already internal. Use plain descriptive names instead.

- Prefer `terminate_proc(proc)` over `_terminate_proc(proc)`
- Prefer `resolve_project(gate_name)` over `_resolve_project(gate_name)`
- Prefer `load_state_or_exit(workspace)` over `_load_state_or_exit(workspace)` (already correct)

Exception: the leading underscore on `_workshop_project()` and `_container_name()` in
`wrappers/lxd.py` pre-dates this guidance. Leave existing names unchanged during unrelated
refactors; rename only when a function is being touched for another reason.
