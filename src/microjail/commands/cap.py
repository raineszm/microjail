"""CLI commands for Capability management."""

from enum import Enum, auto
from typing import TYPE_CHECKING

import typer

from microjail.caps.endpoint import WorkshopEndpointCapability
from microjail.commands._output import error, success, warning

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
    *,
    is_locked: bool,
    apply: bool,
) -> tuple[EditAction, str | None]:
    """Check Workshop state and return the action + optional message.

    When ``apply`` is True, the caller is asking to update runtime or
    Workshop declaration state as well as the config. We must refuse
    when the Workshop is not launched, is still pending, or is ready
    but the policy is already enforced (locked). Otherwise we proceed
    and let the caller apply the appropriate policy-update strategy.
    """
    if info is None:
        if apply:
            return EditAction.DENY, (
                "cannot apply: Workshop is not launched. "
                "Omit --apply to declare without applying, or launch the "
                "workshop first."
            )
        return EditAction.ALLOW, None

    if info.status == "pending":
        if apply:
            return EditAction.DENY, (
                "cannot apply while Workshop is pending. "
                "Wait for the workshop to reach a stable state."
            )
        return EditAction.DENY, (
            "cannot edit capability declarations while Workshop is pending. "
            "Wait for the workshop to reach a stable state."
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
            return EditAction.DENY, (
                "cannot edit Capability declarations while the Lockdown is "
                "applied. Run 'microjail unlock' before editing capabilities."
            )
        if apply:
            return EditAction.ALLOW, None
        return (
            EditAction.ALLOW_WITH_WARNING,
            "live Workshop state was not changed. Run 'microjail lock' to "
            "apply the updated Lockdown.",
        )

    return EditAction.DENY, f"unknown Workshop state '{info.status}'"


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
        help="Address the workload uses inside the container; defaults to HOST_ENDPOINT",
    ),
    fatal: bool = typer.Option(
        False,
        "--fatal",
        help="Block workload launch if capability verification fails",
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
        error(
            f"No microjail config found for project {exc.project_path}. "
            "Run 'microjail init' to create a microjail for this project."
        )
        raise typer.Exit(policy.GENERIC_ERROR) from exc

    # Validate entire Lockdown before mutating
    dup_error = validate_no_duplicate_names(microjail.lockdown.caps)
    if dup_error:
        error(dup_error)
        raise typer.Exit(policy.GENERIC_ERROR)

    # Validate inputs before mutating
    name_error = validate_endpoint_name(name)
    if name_error:
        error(name_error)
        raise typer.Exit(policy.GENERIC_ERROR)

    host_error = validate_endpoint_address(host_endpoint)
    if host_error:
        error(host_error)
        raise typer.Exit(policy.GENERIC_ERROR)

    if container_endpoint is not None:
        container_error = validate_endpoint_address(container_endpoint)
        if container_error:
            error(container_error)
            raise typer.Exit(policy.GENERIC_ERROR)

    # Preflight Workshop state
    try:
        info = microjail.workshop_info()
    except Exception as exc:
        error(f"cannot determine Workshop state: {exc}")
        raise typer.Exit(policy.GENERIC_ERROR) from exc

    is_locked = any(gate.check(microjail) for gate in microjail.lockdown.gates)

    action, msg = preflight_workshop_state(info, is_locked=is_locked, apply=apply)

    if action is EditAction.DENY:
        assert msg is not None
        error(msg)
        raise typer.Exit(policy.GENERIC_ERROR)

    if action is EditAction.ALLOW_WITH_WARNING:
        assert msg is not None
        warning(msg)

    # Check for existing capability with same name
    existing = next(
        (c for c in microjail.lockdown.caps if c.name == name),
        None,
    )

    if existing is not None:
        if not isinstance(existing, WorkshopEndpointCapability):
            error(f"capability '{name}' is not an Endpoint capability.")
            raise typer.Exit(policy.GENERIC_ERROR)

        if (
            existing.host_endpoint == host_endpoint
            and existing.container_endpoint == container_endpoint
            and existing.fatal == fatal
        ):
            # Same-value add is idempotent
            success(f"endpoint capability unchanged: {name} -> {host_endpoint}")
            return

        if not replace:
            error(
                f"endpoint capability '{name}' already exists with different values. "
                "Use --replace to overwrite."
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
            error("cannot apply; Workshop is not launched")
            raise typer.Exit(policy.GENERIC_ERROR)

        if info.status == "ready" and not is_locked:
            # Apply full Lockdown through the policy application path
            from microjail.microjail import ApplicationIntent, ApplicationStatus

            result = microjail.ensure(ApplicationIntent.LOCK)
            if result.status is not ApplicationStatus.SUCCESS:
                warning("Lockdown application incomplete after cap edit")

        elif info.status in ("stopped", "off"):
            # Update Workshop declaration files without starting/refreshing
            cap = microjail.lockdown.caps[-1]
            assert isinstance(cap, WorkshopEndpointCapability), "just added endpoint"
            t = microjail.workshop.tunnel
            t.add_plug(name, cap.resolved_endpoint)
            t.add_slot(name, cap.host_endpoint)

    success(f"endpoint capability added: {name} -> {host_endpoint}")


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
        error(
            f"No microjail config found for project {exc.project_path}. "
            "Run 'microjail init' to create a microjail for this project."
        )
        raise typer.Exit(policy.GENERIC_ERROR) from exc

    # Validate entire Lockdown before mutating
    dup_error = validate_no_duplicate_names(microjail.lockdown.caps)
    if dup_error:
        error(dup_error)
        raise typer.Exit(policy.GENERIC_ERROR)

    # Preflight Workshop state
    try:
        info = microjail.workshop_info()
    except Exception as exc:
        error(f"cannot determine Workshop state: {exc}")
        raise typer.Exit(policy.GENERIC_ERROR) from exc

    is_locked = any(gate.check(microjail) for gate in microjail.lockdown.gates)

    action, msg = preflight_workshop_state(info, is_locked=is_locked, apply=apply)

    if action is EditAction.DENY:
        assert msg is not None
        error(msg)
        raise typer.Exit(policy.GENERIC_ERROR)

    if action is EditAction.ALLOW_WITH_WARNING:
        assert msg is not None
        warning(msg)

    existing = next(
        (c for c in microjail.lockdown.caps if c.name == name),
        None,
    )

    if existing is None:
        error(f"endpoint capability '{name}' not found.")
        raise typer.Exit(policy.GENERIC_ERROR)

    if not isinstance(existing, WorkshopEndpointCapability):
        error(f"capability '{name}' is not an Endpoint capability.")
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
            error("cannot apply; Workshop is not launched")
            raise typer.Exit(policy.GENERIC_ERROR)

        if info.status == "ready" and not is_locked:
            from microjail.microjail import ApplicationIntent, ApplicationStatus

            result = microjail.ensure(ApplicationIntent.LOCK)
            if result.status is not ApplicationStatus.SUCCESS:
                warning("Lockdown application incomplete after cap remove")

        elif info.status in ("stopped", "off"):
            t = microjail.workshop.tunnel
            t.remove_plug(name)
            t.remove_slot(name, remove_sdk=False)

    success(f"endpoint capability removed: {name}")
