"""Implementation of the ``microjail init`` command.

Orchestration order (FR-011):
1. Validate ``name`` format.
2. Pre-flight checks: prerequisites, workspace writability, existing env, existing files.
3. Write ``<workspace>/.workshop/<name>.yaml`` (Workshop definition).
4. Write ``<workspace>/opencode.jsonc`` (if ``--agent opencode``).
5. Run ``workshop launch <name>`` subprocess call.
6. Verify via ``workshop info <name>``.
7. Write ``.microjail/state.json``.
8. Print success summary.

The generated config files are written before any Workshop call so they can be
inspected and reused on retry. ``.microjail/state.json`` is written only after
launch/verification succeeds so it remains a reliable record of an existing
environment.
"""

import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, cast

import typer

from microjail.config.models import AgentHarness, EnvironmentConfig, InferenceBackend
from microjail.config.opencode import generate_opencode_config
from microjail.config.workshop import generate_workshop_yaml
from microjail.state import EnvironmentState
from microjail.workshop import client

_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9-]*$")
_MAX_NAME_LEN = 63
_SOCKET_URL = "http://127.0.0.1:8080/v1"
_BASE_IMAGE = "ubuntu@26.04"


def _err(msg: str, code: int = 1) -> None:
    typer.echo(f"Error: {msg}", err=True)
    raise typer.Exit(code)


def _validate_inputs(
    name: str,
    inference: str | None,
    agent: str | None,
) -> None:
    """Raise typer.Exit(1) if any input is invalid."""
    if not _NAME_RE.match(name) or len(name) > _MAX_NAME_LEN:
        _err(
            f"Invalid environment name '{name}'. Names must start with a letter, "
            "contain only letters, digits, and hyphens, and be at most 63 characters.",
            code=1,
        )
    if inference is not None and inference != "llama-cpp":
        _err(
            f"Invalid value for '--inference': '{inference}' is not one of 'llama-cpp'.",
            code=1,
        )
    if agent is not None and agent != "opencode":
        _err(
            f"Invalid value for '--agent': '{agent}' is not one of 'opencode'.",
            code=1,
        )


def _preflight(
    name: str,
    workspace: Path,
    agent: str | None,
    *,
    force: bool,
) -> bool:
    """Run pre-flight checks; raise typer.Exit(2) on failure.

    Returns ``True`` if the environment already exists (relevant when
    ``force=True`` so the caller can choose ``refresh`` over ``launch``).
    """
    try:
        client.check_prerequisites()
    except RuntimeError as exc:
        _err(str(exc), code=2)

    if not os.access(workspace, os.W_OK):
        _err(
            f"Workspace directory '{workspace}' is not writable. "
            "Ensure you have write permission before running microjail init.",
            code=2,
        )

    already_exists = client.environment_exists(name, workspace)
    if not force and already_exists:
        _err(
            f"Environment '{name}' already exists. Use --force to reinitialise.",
            code=2,
        )

    if not force:
        workshop_def_path = workspace / ".workshop" / f"{name}.yaml"
        if workshop_def_path.exists():
            _err(
                f".workshop/{name}.yaml already exists. Use --force to overwrite.",
                code=2,
            )
        if agent == "opencode" and (workspace / "opencode.jsonc").exists():
            _err(
                "opencode.jsonc already exists in this directory. Use --force to overwrite.",
                code=2,
            )

    return already_exists


def _write_config_files(
    name: str,
    workspace: Path,
    config: EnvironmentConfig,
    agent: str | None,
    socket_url: str | None,
) -> None:
    """Write .workshop/<name>.yaml and opencode.jsonc; raise typer.Exit(3) on I/O error."""
    workshop_def_path = workspace / ".workshop" / f"{name}.yaml"
    try:
        workshop_def_path.parent.mkdir(parents=True, exist_ok=True)
        workshop_def_path.write_text(generate_workshop_yaml(config))
    except OSError as exc:
        _err(f"Cannot write to current directory: {exc}", code=3)

    if agent == "opencode":
        try:
            (workspace / "opencode.jsonc").write_text(
                generate_opencode_config(socket_url)
            )
        except OSError as exc:
            _err(f"Cannot write to current directory: {exc}", code=3)


def _launch_and_verify(name: str, workspace: Path, *, already_exists: bool) -> None:
    """Launch or refresh the workshop environment, then verify it exists."""
    try:
        if already_exists:
            client.refresh(name, workspace)
        else:
            client.launch(name, workspace)
    except RuntimeError as exc:
        _err(str(exc), code=3)

    try:
        client.verify_exists(name, workspace)
    except RuntimeError as exc:
        _err(str(exc), code=3)


def init(
    name: Annotated[str, typer.Argument(help="Workshop environment name.")],
    inference: Annotated[
        InferenceBackend | None,
        typer.Option("--inference", help="Configure a local inference backend."),
    ] = None,
    agent: Annotated[
        AgentHarness | None,
        typer.Option("--agent", help="Configure an AI agent harness."),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Overwrite existing definition and opencode.jsonc.",
        ),
    ] = False,
) -> None:
    r"""Create a Workshop environment and write configuration files for a jailed workload session.

    NAME is the environment name; it must start with a letter and contain only
    letters, digits, and hyphens (max 63 characters).

    \b
    Examples:
      microjail init myproject
      microjail init myproject --inference llama-cpp --agent opencode
    """
    _validate_inputs(name, inference, agent)

    workspace = Path.cwd()
    already_exists = _preflight(name, workspace, agent, force=force)

    socket_url: str | None = _SOCKET_URL if inference == "llama-cpp" else None
    config = EnvironmentConfig(
        name=name,
        base_image=_BASE_IMAGE,
        inference=cast("InferenceBackend | None", inference),
        agent=cast("AgentHarness | None", agent),
    )

    _write_config_files(name, workspace, config, agent, socket_url)

    _launch_and_verify(name, workspace, already_exists=already_exists)

    state = EnvironmentState(
        name=name,
        base_image=_BASE_IMAGE,
        inference=inference,
        agent=agent,
        socket_url=socket_url,
        created_at=datetime.now(tz=UTC),
    )
    try:
        state.to_json(workspace)
    except OSError as exc:
        _err(f"Cannot write state to current directory: {exc}", code=3)

    workshop_def_path = workspace / ".workshop" / f"{name}.yaml"
    state_path = workspace / ".microjail" / "state.json"
    typer.echo(f"Environment '{name}' created.\n")
    typer.echo(f"  definition      -> {workshop_def_path}")
    if agent == "opencode":
        typer.echo(f"  opencode.jsonc  -> {workspace / 'opencode.jsonc'}")
    typer.echo(f"  state           -> {state_path}")
