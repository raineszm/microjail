<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
<!-- SPECKIT END -->

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
