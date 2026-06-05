"""Shared helpers for integration command tests."""

import subprocess
import time


def await_env_removed(name: str) -> None:
    """Block until LXD has fully deleted the container for *name*.

    ``workshop remove`` exits 0 once Workshop considers the environment gone, but
    the underlying LXD container may still be stopping/deleting asynchronously.
    Without waiting here, the next ``workshop launch`` can race against that
    cleanup and block indefinitely.

    Resolves the workshop LXD project, then polls ``lxc list`` until no
    container whose name contains *name* is present.  Returns immediately once
    the container is gone; after 60 one-second cycles it emits a warning and
    returns so the test suite can still proceed.
    """
    project_result = subprocess.run(
        ["lxc", "project", "list", "--format", "csv"],
        capture_output=True,
        check=False,
    )
    workshop_project = next(
        (
            line.split(",")[0].strip()
            for line in project_result.stdout.decode().splitlines()
            if line.split(",")[0].strip().startswith("workshop.")
        ),
        None,
    )
    if workshop_project is None:
        return

    for _ in range(60):
        list_result = subprocess.run(
            [
                "lxc",
                "--project",
                workshop_project,
                "list",
                "--format",
                "csv",
                "--columns",
                "n",
            ],
            capture_output=True,
            check=False,
        )
        if not any(name in c for c in list_result.stdout.decode().splitlines()):
            return
        time.sleep(1)

    print(
        f"\nWarning: LXD container for '{name}' still present 60 s after remove.",
        flush=True,
    )
