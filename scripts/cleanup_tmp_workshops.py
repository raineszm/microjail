#!/usr/bin/env python3

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator


@dataclass
class Workshop:
    project_dir: Path
    name: str


def tmp_workshops() -> Generator[Workshop]:
    result = subprocess.run(
        ["workshop", "list", "--global", "--no-headers"],
        capture_output=True,
        text=True,
        check=True,
    )

    if not result.stdout.strip():
        print("No workshops found.")
        return

    for line in result.stdout.splitlines():
        if not line.strip():
            continue

        parts = line.split()
        if len(parts) >= 2:
            project_dir = Path(parts[0])
            name = parts[1]

            if str(project_dir).startswith("/tmp"):
                yield Workshop(project_dir=project_dir, name=name)


def remove_workshop(workshop: Workshop):
    if not workshop.project_dir.exists():
        print(
            f"Project directory {workshop.project_dir} does not exist, creating for deletion..."
        )
        workshop.project_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"Removing workshop '{workshop.name}' from project '{workshop.project_dir}'..."
    )
    cmd = ["workshop", "remove", "--project", workshop.project_dir, workshop.name]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to remove {workshop.name}: {e}")


def main():
    print("Fetching global workshop list...")
    for workshop in tmp_workshops():
        remove_workshop(workshop)


if __name__ == "__main__":
    main()
