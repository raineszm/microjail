## Commit Trailers

Every AI-assisted commit MUST include an `Assisted-By` trailer:

```
Assisted-By: <harness> (<model>; <provider>)
```

Examples:

Assisted-By: omp (claude-sonnet-4-5; anthropic)
Assisted-By: omp (gpt-4o; openai)

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

## Testing

Run tests with `uv run pytest`. The default run skips slow tests (container creation, LXD,
Workshop); pass `--slow` to include them.

- `uv run pytest` — fast unit/functional tests only
- `uv run pytest --slow` — all tests including e2e and container-based tests

Markers `lxd` and `workshop` auto-skip when the required binaries (`lxc`, `workshop`) are
not on `$PATH`.

## Agent skills

### Issue tracker

GitHub — issues live in `raineszm/microjail` GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
