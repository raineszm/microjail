import pytest

from microjail.adapters import workshop
from tests.marks import requires_workshop

pytestmark = [
    requires_workshop(),
]


@pytest.fixture
def initialized_workshop(tmp_workshop):
    workshop.init(tmp_workshop.name)
    return tmp_workshop


@pytest.fixture
def launched_workshop(initialized_workshop):
    workshop.launch(initialized_workshop.name, project=initialized_workshop.path)
    return initialized_workshop


def test_init_minimal_args(tmp_workshop):
    workshop.init(tmp_workshop.name)


def test_ready_after_launch(launched_workshop):
    info = workshop.info(launched_workshop.name, project=launched_workshop.path)
    assert info is not None
    assert info.status == "ready"


def test_info_returns_none_if_not_launched(initialized_workshop):
    info = workshop.info(initialized_workshop.name, project=initialized_workshop.path)
    assert info is None


def test_get_container_returns_none_if_not_launched(initialized_workshop):
    container = workshop.get_container(
        initialized_workshop.name, project=initialized_workshop.path
    )
    assert container is None


def test_lxd_project_returns_existing_project():
    project = workshop.lxd_project()
    assert project is not None
    assert project.startswith("workshop.")


def test_get_container_returns_container_if_launched(launched_workshop):
    container = workshop.get_container(
        launched_workshop.name, project=launched_workshop.path
    )
    assert container is not None
