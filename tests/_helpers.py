"""Shared test helpers — importable by all test layers."""

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path  # noqa: TC003

from microjail.adapters import workshop

LAUNCH_TIMEOUT = 30
LAUNCH_RETRIES = 2
LAUNCH_BACKOFF = 15


@dataclass(frozen=True)
class SharedWorkshop:
    name: str
    path: Path


def launch_with_retries(name: str, project: Path) -> None:
    """Launch a workshop, retrying if it times out.

    Sometimes workshop just stalls on launch. Probably from us standing it
    up and tearing it down repeatedly in tests.
    """
    for attempt in range(LAUNCH_RETRIES + 1):
        try:
            workshop.launch(name, project=project, timeout=LAUNCH_TIMEOUT)
            return
        except subprocess.TimeoutExpired:
            if attempt == LAUNCH_RETRIES:
                raise
            time.sleep(LAUNCH_BACKOFF)
