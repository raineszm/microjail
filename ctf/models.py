"""Dataclasses for CTF escape-test run state."""

import dataclasses
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path


@dataclasses.dataclass(frozen=True)
class Secret:
    """A named secret value used in containment tests."""

    name: str
    value: str


@dataclasses.dataclass(frozen=True)
class TestRunConfig:
    """Immutable configuration for a single CTF test run."""

    __test__ = False

    env_name: str
    workspace: Path
    timeout_seconds: int
    inference_host: str
    inference_port: int
    http_port: int
    tmp_secret_path: Path


@dataclasses.dataclass
class TestRun:
    """Mutable state accumulated over the lifetime of a CTF test run."""

    __test__ = False

    config: TestRunConfig
    filesystem_secret: Secret
    network_secret: Secret
    started_at: datetime
    finished_at: datetime | None = None
    outcome: Literal["pass", "fail", "error", "inconclusive"] | None = None
    iterations: int = 0
    found_secret: str | None = None
    found_iteration: int | None = None
