"""Implementation of the ``microjail init`` command.

Orchestration order (normal path):
1. Validate ``name`` format and ``--inference-url``.
2. Pre-flight checks: workspace writability, existing state file, existing config files.
3. Write ``<workspace>/.workshop/<name>.yaml`` (Workshop definition).
4. Write ``<workspace>/opencode.jsonc`` (if ``--agent opencode``).
5. Write ``.microjail/state.json`` with ``launched=False``.
6. Print success summary.

For ``--force`` on a launched environment (``state.launched=True, locked=False``):
step 3 overwrites local config files, then calls ``workshop refresh``,
``workshop verify_exists``, and (if inference) ``workshop connect`` before
writing ``state.json`` with ``launched=True``.

Container provisioning is deferred to the first ``microjail lock`` or
``microjail run`` invocation via ``ensure_container_ready()``.
"""

import os
import re
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import typer

from microjail.config.models import (
    AgentHarness,
    EnvironmentConfig,
    InferenceBackend,
)
from microjail.config.opencode import generate_opencode_config
from microjail.config.workshop import (
    INFERENCE_PLUG_REF,
    INFERENCE_SLOT_REF,
    generate_sdk_yaml,
    generate_workshop_yaml,
)
from microjail.output import err
from microjail.state import State
from microjail.wrappers import workshop

_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9-]*$")
_MAX_NAME_LEN = 63
_SOCKET_URL = "http://127.0.0.1:8080/v1"
_BASE_IMAGE = "ubuntu@26.04"


def validate_name(value: str) -> str:
    """Typer callback: validate the ``name`` argument format."""
    if not _NAME_RE.match(value) or len(value) > _MAX_NAME_LEN:
        raise typer.BadParameter(
            f"'{value}' is invalid. Names must start with a letter, "
            "contain only letters, digits, and hyphens, and be at most 63 characters."
        )
    return value


def validate_inference_url(value: str | None) -> str | None:
    """Typer callback: validate the ``--inference-url`` option."""
    if value is None:
        return value
    parsed_url = urlparse(value)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
        raise typer.BadParameter(
            f"'{value}' is invalid. Must start with http:// or https:// and contain a host."
        )
    return value


def preflight(
    name: str,
    workspace: Path,
    agent: str | None,
    *,
    force: bool,
) -> None:
    """Run pre-flight checks; raise typer.Exit(2) on failure.

    On the normal (non-force) path: verifies workspace is writable and that
    no local state or config files already exist.

    On the ``--force`` path: verifies workspace is writable and that the
    environment is not currently locked (FR-017).  No Workshop subprocess is
    called here.
    """
    if not os.access(workspace, os.W_OK):
        err(
            f"Workspace directory '{workspace}' is not writable. "
            "Ensure you have write permission before running microjail init.",
            code=2,
        )

    state_path = workspace / ".microjail" / "state.json"

    if force:
        # FR-017: refuse --force on a locked environment to avoid mutating
        # LXD device state that lock_egress established.
        if state_path.exists():
            try:
                existing = State.from_json(workspace)
            except Exception:  # treat unreadable state as unlocked
                existing = None
            if existing is not None and existing.locked:
                err(
                    f"Environment '{name}' is currently locked. "
                    "Run 'microjail unlock' first.",
                    code=2,
                )
    else:
        # Duplicate detection via local state file (FR-005).
        # We do not query Workshop — the container may not exist yet.
        if state_path.exists():
            err(
                f"Environment '{name}' already exists in this directory. "
                "Use --force to reinitialise.",
                code=2,
            )

        workshop_def_path = workspace / ".workshop" / f"{name}.yaml"
        if workshop_def_path.exists():
            err(
                f".workshop/{name}.yaml already exists. Use --force to overwrite.",
                code=2,
            )

        if agent == "opencode" and (workspace / "opencode.jsonc").exists():
            err(
                "opencode.jsonc already exists in this directory. Use --force to overwrite.",
                code=2,
            )


def write_config_files(
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
        if config.inference is not None:
            sdk_yaml_content = generate_sdk_yaml(config)
            sdk_dir = workspace / ".workshop" / "local-inference"
            sdk_dir.mkdir(parents=True, exist_ok=True)
            (sdk_dir / "sdk.yaml").write_text(sdk_yaml_content)
        if agent == "opencode":
            (workspace / "opencode.jsonc").write_text(
                generate_opencode_config(socket_url)
            )
    except OSError as exc:
        err(f"Cannot write to current directory: {exc}", code=3)


def init(
    name: Annotated[
        str, typer.Argument(help="Workshop environment name.", callback=validate_name)
    ],
    inference: Annotated[
        InferenceBackend | None,
        typer.Option("--inference", help="Configure a local inference backend."),
    ] = None,
    agent: Annotated[
        AgentHarness | None,
        typer.Option("--agent", help="Configure an AI agent harness."),
    ] = None,
    inference_url: Annotated[
        str | None,
        typer.Option(
            "--inference-url",
            help="HTTP/HTTPS URL of the inference server (e.g. http://192.168.1.5:8080). "
            "Scheme and path are stripped; host:port stored in EnvironmentConfig.",
            callback=validate_inference_url,
        ),
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
    workspace = Path.cwd()
    preflight(name, workspace, agent, force=force)

    inference_endpoint: str | None = None
    socket_url: str | None = None
    if inference is not None:
        if inference_url is not None:
            parsed_url = urlparse(inference_url)
            inf_port = parsed_url.port or (443 if parsed_url.scheme == "https" else 80)
            inference_endpoint = f"{parsed_url.hostname}:{inf_port}"
        else:
            inference_endpoint = (
                None  # generate_workshop_yaml defaults to localhost:8080
            )
        socket_url = f"http://localhost:{(inference_endpoint or 'localhost:8080').rpartition(':')[2]}/v1"
    config = EnvironmentConfig(
        name=name,
        base_image=_BASE_IMAGE,
        inference=inference,
        agent=agent,
        inference_endpoint=inference_endpoint,
    )

    write_config_files(name, workspace, config, agent, socket_url)

    # Determine whether the container was already launched (relevant for --force).
    newly_launched = False
    if force:
        state_path = workspace / ".microjail" / "state.json"
        existing_launched = False
        if state_path.exists():
            try:
                existing = State.from_json(workspace)
                existing_launched = existing.launched
            except Exception:  # treat unreadable state as unlaunched
                pass
        if existing_launched:
            # Container exists — refresh it with the new config (FR-012).
            try:
                workshop.check_prerequisites()
                workshop.refresh(name, workspace)
                workshop.verify_exists(name, workspace)
            except RuntimeError as exc:
                err(str(exc), code=3)
            if config.inference is not None:
                try:
                    workshop.connect(
                        name, INFERENCE_PLUG_REF, INFERENCE_SLOT_REF, workspace
                    )
                except RuntimeError as exc:
                    err(str(exc), code=3)
            newly_launched = True

    state = State(
        name=name,
        base_image=_BASE_IMAGE,
        inference=inference,
        agent=agent,
        socket_url=socket_url,
        launched=newly_launched,
    )
    try:
        state.dump(workspace)
    except OSError as exc:
        err(f"Cannot write state to current directory: {exc}", code=3)

    workshop_def_path = workspace / ".workshop" / f"{name}.yaml"
    state_path = workspace / ".microjail" / "state.json"
    typer.echo(f"Environment '{name}' created.\n")
    typer.echo(f"  definition      -> {workshop_def_path}")
    if config.inference is not None:
        sdk_yaml_path = workspace / ".workshop" / "local-inference" / "sdk.yaml"
        typer.echo(f"  sdk.yaml        -> {sdk_yaml_path}")
    if agent == "opencode":
        typer.echo(f"  opencode.jsonc  -> {workspace / 'opencode.jsonc'}")
    typer.echo(f"  state           -> {state_path}")
