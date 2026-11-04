import pytest

from src.catalog import search_products
from src.database import connect
from src.load_data import load_all_data
from src.restock import RestockError, main, restock
from tests.conftest import DATA_DIR

GIANNINI_GF_3D = 96


def test_restock_makes_the_giannini_gf_3d_available_without_changing_the_source(connection):
    csv_before = (DATA_DIR / "products.csv").read_bytes()
    (before,) = search_products(connection, "Giannini GF-3D")
    assert before.availability == "indisponivel"

    restock(connection, GIANNINI_GF_3D, 5)

    (after,) = search_products(connection, "Giannini GF-3D")
    assert after.availability == "disponivel"
    assert (DATA_DIR / "products.csv").read_bytes() == csv_before


def test_rejects_nonexistent_product(connection):
    with pytest.raises(RestockError, match="does not exist"):
        restock(connection, 99999, 5)


@pytest.mark.parametrize("quantity", [0, -3])
def test_rejects_quantity_below_one(connection, quantity):
    with pytest.raises(RestockError, match="quantity"):
        restock(connection, GIANNINI_GF_3D, quantity)

    (product,) = search_products(connection, "Giannini GF-3D")
    assert product.availability == "indisponivel"


@pytest.mark.parametrize("product", [130, 136])  # new release and discontinued
def test_rejects_product_that_is_not_active(connection, product):
    with pytest.raises(RestockError, match="not active"):
        restock(connection, product, 5)


def test_command_restocks_the_given_database_and_the_load_restores_the_original(tmp_path, capsys):
    db = tmp_path / "comando.db"
    connection = connect(db)
    load_all_data(connection, DATA_DIR)

    exit_code = main(["96", "--quantity", "3", "--db", str(db)])

    assert exit_code == 0
    assert "3" in capsys.readouterr().out
    assert search_products(connection, "Giannini GF-3D")[0].availability == "disponivel"

    load_all_data(connection, DATA_DIR)
    assert search_products(connection, "Giannini GF-3D")[0].availability == "indisponivel"
    connection.close()


def test_command_reports_the_rejection_reason_without_traceback(tmp_path, capsys):
    db = tmp_path / "comando.db"
    connection = connect(db)
    load_all_data(connection, DATA_DIR)
    connection.close()

    exit_code = main(["99999", "--db", str(db)])

    assert exit_code == 1
    assert "does not exist" in capsys.readouterr().err


@pytest.mark.regression
def test_command_does_not_create_the_database_when_it_does_not_exist(tmp_path, capsys):
    db = tmp_path / "ausente.db"

    exit_code = main(["96", "--db", str(db)])

    assert exit_code == 1
    assert "python -m src.load_data" in capsys.readouterr().err
    assert not db.exists()
