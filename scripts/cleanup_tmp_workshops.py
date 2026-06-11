#!/usr/bin/env python3

import subprocess


def main():
    print("Fetching global workshop list...")
    result = subprocess.run(
        ["workshop", "list", "--global", "--no-headers"],
        capture_output=True,
        text=True,
        check=True,
    )

    lines = result.stdout.strip().split("\n")
    if not result.stdout.strip():
        print("No workshops found.")
        return

    for line in lines:
        if not line.strip():
            continue

        parts = line.split()
        if len(parts) >= 2:
            project_dir = parts[0]
            name = parts[1]

            if project_dir.startswith("/tmp"):
                print(f"Removing workshop '{name}' from project '{project_dir}'...")
                cmd = ["workshop", "remove", "--project", project_dir, name]
                try:
                    subprocess.run(cmd, check=True)
                except subprocess.CalledProcessError as e:
                    print(f"Failed to remove {name}: {e}")


if __name__ == "__main__":
    main()
