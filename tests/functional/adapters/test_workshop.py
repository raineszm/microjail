from microjail.adapters import workshop
from tests.marks import requires_workshop

pytestmark = [
    requires_workshop(),
]


def test_workshop_init_minimal_args(tmp_workshop):
    workshop.init(tmp_workshop.name)
