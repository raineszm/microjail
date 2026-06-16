"""Fixtures for functional tests."""

import os
import subprocess
import uuid
from pathlib import Path

import pytest

from microjail.adapters.workshop import Workshop


@pytest.fixture(scope="module")
def launched_workshop(tmp_path_factory):
    """A launched workshop, cleaned up after the module."""
    project = tmp_path_factory.mktemp("launched-workshop")
    name = f"mj-workshop-{uuid.uuid4().hex[:8]}"
    cwd = Path.cwd()

    try:
        os.chdir(project)
        Workshop.init(name, project=project)
        ws = Workshop(name=name, project=project)
        ws.launch()
        yield ws
    finally:
        os.chdir(cwd)
        subprocess.run(["workshop", "remove", "--project", str(project)], check=False)
