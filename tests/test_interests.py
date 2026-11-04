import pytest

from src.interests import Result, list_pending, register
from src.load_data import load_all_data
from tests.conftest import DATA_DIR

PHONE = "(67) 99654-7821"
GIANNINI_GF_3D = 96


def test_registers_interest_in_the_giannini_gf_3d(connection):
    result = register(connection, PHONE, GIANNINI_GF_3D)

    assert result == Result.REGISTERED
    assert list_pending(connection, PHONE) == ["Giannini GF-3D Dreadnought Sunburst"]


def test_nonexistent_product_does_not_write_interest(connection):
    result = register(connection, PHONE, 99999)

    assert result == Result.PRODUCT_NOT_FOUND
    assert list_pending(connection, PHONE) == []
    assert connection.execute("SELECT COUNT(*) FROM product_interests").fetchone()[0] == 0


@pytest.mark.parametrize("phone", ["", "12345", "abc"])
def test_invalid_phone_does_not_write_interest(connection, phone):
    result = register(connection, phone, GIANNINI_GF_3D)

    assert result == Result.INVALID_PHONE
    assert connection.execute("SELECT COUNT(*) FROM product_interests").fetchone()[0] == 0


def test_repeating_the_request_does_not_duplicate_the_interest(connection):
    register(connection, PHONE, GIANNINI_GF_3D)

    # Another formatting of the same phone number is the same customer.
    result = register(connection, "67996547821", GIANNINI_GF_3D)

    assert result == Result.ALREADY_REGISTERED
    assert list_pending(connection, PHONE) == ["Giannini GF-3D Dreadnought Sunburst"]


def test_new_data_load_preserves_the_interests(connection):
    register(connection, PHONE, GIANNINI_GF_3D)

    load_all_data(connection, DATA_DIR)

    assert list_pending(connection, PHONE) == ["Giannini GF-3D Dreadnought Sunburst"]
