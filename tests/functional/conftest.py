"""Fixtures for functional tests."""

import os
import subprocess
import uuid
from pathlib import Path

import pytest

from microjail.adapters import workshop
from tests._helpers import SharedWorkshop


@pytest.fixture(scope="module")
def launched_workshop(tmp_path_factory):
    """A launched workshop, cleaned up after the module."""
    project = tmp_path_factory.mktemp("launched-workshop")
    name = f"mj-workshop-{uuid.uuid4().hex[:8]}"
    cwd = Path.cwd()

    try:
        os.chdir(project)
        workshop.init(name, project=project)
        workshop.launch(name, project=project)
        yield SharedWorkshop(name=name, path=project)
    finally:
        os.chdir(cwd)
        subprocess.run(["workshop", "remove", "--project", str(project)], check=False)
