"""CLI commands for Capability management."""

from enum import Enum, auto
from typing import TYPE_CHECKING

import typer

from microjail.caps.endpoint import WorkshopEndpointCapability

if TYPE_CHECKING:
    from pathlib import Path

    from microjail.adapters.workshop import WorkshopInfo


class EditAction(Enum):
    """Action determined by Workshop state preflight."""

    ALLOW = auto()  # Save declaration change, no warning
    ALLOW_WITH_WARNING = auto()  # Save declaration change, warn
    DENY = auto()  # Fail before saving


def validate_no_duplicate_names(caps: list) -> str | None:
    """Return error message if any capability names repeat, else None."""
    seen: set[str] = set()
    for cap in caps:
        if cap.name in seen:
            return f"duplicate capability name '{cap.name}' in config"
        seen.add(cap.name)
    return None


def preflight_workshop_state(
    info: WorkshopInfo | None,
    is_locked: bool = False,
    apply: bool = False,
) -> tuple[EditAction, str | None]:
    """Check Workshop state and return the action + optional message.

    Parameters
    ----------
    info:
        Workshop info, or None if the Workshop is not launched.
    is_locked:
        True if at least one Gate is currently active (Lockdown appears applied).
        Only meaningful when ``info`` is not None and ``info.status == "ready"``.
    apply:
        True if ``--apply`` was passed (stricter state rules apply).

    Returns
    -------
    (action, message):
        - ALLOW: save and proceed (message is None).
        - ALLOW_WITH_WARNING: save and emit warning message.
        - DENY: fail before saving with error message.
    """
    if info is None:
        if apply:
            return (
                EditAction.DENY,
                "Cannot apply cap changes without a running Workshop. "
                "Omit --apply for declaration-only setup, or launch the Workshop first",
            )
        return EditAction.ALLOW, None

    if info.status == "pending":
        return (
            EditAction.DENY,
            "Workshop is pending; cannot edit capability declarations",
        )

    if info.status in ("stopped", "off"):
        if apply:
            # Allow declaration update, but no start/refresh/connect
            return EditAction.ALLOW, None
        return (
            EditAction.ALLOW_WITH_WARNING,
            "Workshop is not running; declaration saved but not applied. "
            "Use 'microjail lock' to apply the updated Lockdown",
        )

    if info.status == "ready":
        if is_locked:
            return (
                EditAction.DENY,
                "Capability declarations cannot be edited while the Lockdown is applied. "
                "Run 'microjail unlock' first",
            )
        if apply:
            return EditAction.ALLOW, None
        return (
            EditAction.ALLOW_WITH_WARNING,
            "Declaration saved but live Workshop state was not changed. "
            "Use 'microjail lock' to apply the updated Lockdown",
        )

    # Unknown status
    return (
        EditAction.DENY,
        f"Unknown Workshop status '{info.status}'; cannot edit safely",
    )


cap_app = typer.Typer(
    name="cap",
    help="Manage Capability declarations.",
    no_args_is_help=True,
)

add_app = typer.Typer(
    name="add",
    help="Add a Capability declaration.",
    no_args_is_help=True,
)

cap_app.add_typer(add_app)


@add_app.command("endpoint")
def add_endpoint(
    ctx: typer.Context,
    name: str,
    host_endpoint: str,
    container_endpoint: str | None = typer.Option(
        None,
        "--container-endpoint",
        help="Container-side endpoint address",
    ),
    fatal: bool = typer.Option(
        False,
        "--fatal",
        help="Terminate workload on runtime Capability violation",
    ),
    replace: bool = typer.Option(
        False,
        "--replace",
        help="Replace existing endpoint with same name",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Apply the resulting Lockdown to runtime state",
    ),
) -> None:
    """Add an Endpoint Capability declaration.

    NAME is the capability name.

    HOST_ENDPOINT is the host-side address in HOST:PORT format.
    """
    from microjail import policy
    from microjail.caps.endpoint import (
        validate_endpoint_address,
        validate_endpoint_name,
    )
    from microjail.microjail import ConfigNotFoundError, MicroJail

    project: Path = ctx.obj
    try:
        microjail = MicroJail.load(project)
    except ConfigNotFoundError as exc:
        typer.echo(
            f"No microjail config found for project {exc.project_path}. "
            "Run 'microjail init' to create a microjail for this project.",
            err=True,
        )
        raise typer.Exit(policy.GENERIC_ERROR) from exc

    # Validate entire Lockdown before mutating
    dup_error = validate_no_duplicate_names(microjail.lockdown.caps)
    if dup_error:
        typer.echo(f"error: {dup_error}", err=True)
        raise typer.Exit(policy.GENERIC_ERROR)

    # Validate inputs before mutating
    name_error = validate_endpoint_name(name)
    if name_error:
        typer.echo(f"error: {name_error}", err=True)
        raise typer.Exit(policy.GENERIC_ERROR)

    host_error = validate_endpoint_address(host_endpoint)
    if host_error:
        typer.echo(f"error: {host_error}", err=True)
        raise typer.Exit(policy.GENERIC_ERROR)

    if container_endpoint is not None:
        container_error = validate_endpoint_address(container_endpoint)
        if container_error:
            typer.echo(f"error: {container_error}", err=True)
            raise typer.Exit(policy.GENERIC_ERROR)

    # Preflight Workshop state
    try:
        info = microjail.workshop_info()
    except Exception as exc:
        typer.echo(
            f"error: cannot determine Workshop state: {exc}",
            err=True,
        )
        raise typer.Exit(policy.GENERIC_ERROR) from exc

    is_locked = any(gate.check(microjail) for gate in microjail.lockdown.gates)

    action, msg = preflight_workshop_state(info, is_locked=is_locked, apply=apply)

    if action is EditAction.DENY:
        assert msg is not None
        typer.echo(f"error: {msg}", err=True)
        raise typer.Exit(policy.GENERIC_ERROR)

    if action is EditAction.ALLOW_WITH_WARNING:
        assert msg is not None
        typer.echo(f"warning: {msg}", err=True)

    # Check for existing capability with same name
    existing = next(
        (c for c in microjail.lockdown.caps if c.name == name),
        None,
    )

    if existing is not None:
        if not isinstance(existing, WorkshopEndpointCapability):
            typer.echo(
                f"error: capability '{name}' is not an Endpoint capability.",
                err=True,
            )
            raise typer.Exit(policy.GENERIC_ERROR)

        if (
            existing.host_endpoint == host_endpoint
            and existing.container_endpoint == container_endpoint
            and existing.fatal == fatal
        ):
            # Same-value add is idempotent
            typer.echo(f"endpoint capability unchanged: {name} -> {host_endpoint}")
            return

        if not replace:
            typer.echo(
                f"error: endpoint capability '{name}' already exists with different values. "
                "Use --replace to overwrite.",
                err=True,
            )
            raise typer.Exit(policy.GENERIC_ERROR)

        # Revoke old endpoint before saving if --apply and ready+unlocked
        # (off/stopped only writes declarations, no disconnect needed)
        if apply and info is not None and info.status == "ready" and not is_locked:
            existing.revoke(microjail)

        # Replace: remove existing before adding new
        microjail.lockdown.caps.remove(existing)

    microjail.lockdown.caps.append(
        WorkshopEndpointCapability(
            name=name,
            host_endpoint=host_endpoint,
            container_endpoint=container_endpoint,
            fatal=fatal,
        )
    )
    microjail.save()

    # Handle --apply after save
    if apply:
        if info is None:
            # Shouldn't reach here (DENY would have blocked), but safety check
            typer.echo("error: cannot apply; Workshop is not launched", err=True)
            raise typer.Exit(policy.GENERIC_ERROR)

        if info.status == "ready" and not is_locked:
            # Apply full Lockdown through the policy application path
            from microjail.microjail import ApplicationIntent, ApplicationStatus

            result = microjail.ensure(ApplicationIntent.LOCK)
            if result.status is not ApplicationStatus.SUCCESS:
                typer.echo(
                    "warning: Lockdown application incomplete after cap edit", err=True
                )

        elif info.status in ("stopped", "off"):
            # Update Workshop declaration files without starting/refreshing
            cap = microjail.lockdown.caps[-1]
            assert isinstance(cap, WorkshopEndpointCapability), "just added endpoint"
            t = microjail.workshop.tunnel
            t.add_plug(name, cap.resolved_endpoint)
            t.add_slot(name, cap.host_endpoint)

    typer.echo(f"endpoint capability added: {name} -> {host_endpoint}")


remove_app = typer.Typer(
    name="remove",
    help="Remove a Capability declaration.",
    no_args_is_help=True,
)

cap_app.add_typer(remove_app)


@remove_app.command("endpoint")
def remove_endpoint(
    ctx: typer.Context,
    name: str,
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Apply the resulting Lockdown to runtime state",
    ),
) -> None:
    """Remove an Endpoint Capability declaration.

    NAME is the capability name to remove.
    """
    from microjail import policy
    from microjail.microjail import ConfigNotFoundError, MicroJail

    project: Path = ctx.obj
    try:
        microjail = MicroJail.load(project)
    except ConfigNotFoundError as exc:
        typer.echo(
            f"No microjail config found for project {exc.project_path}. "
            "Run 'microjail init' to create a microjail for this project.",
            err=True,
        )
        raise typer.Exit(policy.GENERIC_ERROR) from exc

    # Validate entire Lockdown before mutating
    dup_error = validate_no_duplicate_names(microjail.lockdown.caps)
    if dup_error:
        typer.echo(f"error: {dup_error}", err=True)
        raise typer.Exit(policy.GENERIC_ERROR)

    # Preflight Workshop state
    try:
        info = microjail.workshop_info()
    except Exception as exc:
        typer.echo(
            f"error: cannot determine Workshop state: {exc}",
            err=True,
        )
        raise typer.Exit(policy.GENERIC_ERROR) from exc

    is_locked = any(gate.check(microjail) for gate in microjail.lockdown.gates)

    action, msg = preflight_workshop_state(info, is_locked=is_locked, apply=apply)

    if action is EditAction.DENY:
        assert msg is not None
        typer.echo(f"error: {msg}", err=True)
        raise typer.Exit(policy.GENERIC_ERROR)

    if action is EditAction.ALLOW_WITH_WARNING:
        assert msg is not None
        typer.echo(f"warning: {msg}", err=True)

    existing = next(
        (c for c in microjail.lockdown.caps if c.name == name),
        None,
    )

    if existing is None:
        typer.echo(
            f"error: endpoint capability '{name}' not found.",
            err=True,
        )
        raise typer.Exit(policy.GENERIC_ERROR)

    if not isinstance(existing, WorkshopEndpointCapability):
        typer.echo(
            f"error: capability '{name}' is not an Endpoint capability.",
            err=True,
        )
        raise typer.Exit(policy.GENERIC_ERROR)

    # Revoke existing endpoint before saving if --apply and ready+unlocked
    # (off/stopped only writes declarations, no disconnect needed)
    if apply and info is not None and info.status == "ready" and not is_locked:
        existing.revoke(microjail)
    microjail.lockdown.caps.remove(existing)
    microjail.save()

    # Handle --apply after save
    if apply:
        if info is None:
            typer.echo("error: cannot apply; Workshop is not launched", err=True)
            raise typer.Exit(policy.GENERIC_ERROR)

        if info.status == "ready" and not is_locked:
            from microjail.microjail import ApplicationIntent, ApplicationStatus

            result = microjail.ensure(ApplicationIntent.LOCK)
            if result.status is not ApplicationStatus.SUCCESS:
                typer.echo(
                    "warning: Lockdown application incomplete after cap remove",
                    err=True,
                )

        elif info.status in ("stopped", "off"):
            t = microjail.workshop.tunnel
            t.remove_plug(name)
            t.remove_slot(name, remove_sdk=False)

    typer.echo(f"endpoint capability removed: {name}")
