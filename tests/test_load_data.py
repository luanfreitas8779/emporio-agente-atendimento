import pytest

from src.catalog import search_products
from src.database import connect
from src.load_data import (
    LoadError,
    database_loaded,
    load_catalog,
    load_customers,
    load_all_data,
    load_orders,
)
from src.orders import get_orders, identify_customer
from tests.conftest import DATA_DIR


def write_catalog(folder, product):
    (folder / "categories.csv").write_text(
        "category_id,name,description\n1,Guitarras,Elétricas\n", encoding="utf-8"
    )
    (folder / "products.csv").write_text(
        "product_id,price_brl,name,category_id,description,stock_quantity,status,specs,created_at\n"
        f"{product}\n",
        encoding="utf-8",
    )


def test_reloading_recreates_the_catalog_without_duplicating_products(connection):
    load_catalog(connection, DATA_DIR)

    assert len(search_products(connection, search_term="Takamine GD20")) == 1


@pytest.mark.regression
def test_stops_the_load_when_the_product_points_to_a_nonexistent_category(tmp_path):
    write_catalog(tmp_path, '10,100,Guitarra Teste,99,Descricao,1,active,{},2024-01-01')
    connection = connect(tmp_path / "teste.db")

    with pytest.raises(LoadError, match="product 10"):
        load_catalog(connection, tmp_path)

    connection.close()


@pytest.mark.regression
def test_stops_the_load_when_the_price_is_invalid(tmp_path):
    write_catalog(tmp_path, '10,abc,Guitarra Teste,1,Descricao,1,active,{},2024-01-01')
    connection = connect(tmp_path / "teste.db")

    with pytest.raises(LoadError, match="product 10"):
        load_catalog(connection, tmp_path)

    connection.close()


@pytest.mark.regression
def test_stops_the_load_when_the_promotion_points_to_a_nonexistent_product(tmp_path):
    write_catalog(tmp_path, '10,100,Guitarra Teste,1,Descricao,1,active,{},2024-01-01')
    (tmp_path / "promotions.csv").write_text(
        "promotion_id,product_id,discount_percent,description,is_active\n"
        "1,99,10,Oferta,1\n",
        encoding="utf-8",
    )
    connection = connect(tmp_path / "teste.db")

    with pytest.raises(LoadError, match="promotion 1"):
        load_catalog(connection, tmp_path)

    connection.close()


def test_reloading_all_data_does_not_duplicate_orders(connection):
    load_all_data(connection, DATA_DIR)

    assert len(get_orders(connection, customer_id=3)) == 2


def write_orders(folder, customer, order, item):
    (folder / "customers.csv").write_text(
        f"customer_id,name,phone,email,city\n{customer}\n", encoding="utf-8"
    )
    (folder / "orders.csv").write_text(
        "order_id,customer_id,order_date,status,total_brl,payment_method,"
        f"tracking_code,estimated_delivery,notes\n{order}\n",
        encoding="utf-8",
    )
    (folder / "order_items.csv").write_text(
        f"order_id,quantity,product_id\n{item}\n", encoding="utf-8"
    )


def load_orders_from(folder, customer, order, item):
    write_orders(folder, customer, order, item)
    connection = connect(folder / "teste.db")
    load_catalog(connection, DATA_DIR)
    load_customers(connection, folder)
    try:
        load_orders(connection, folder)
    finally:
        connection.close()


CUSTOMER = "1,Cliente Teste,(67) 90000-0001,teste@exemplo.com,Campo Grande"


@pytest.mark.regression
def test_stops_the_load_when_the_order_points_to_a_nonexistent_customer(tmp_path):
    with pytest.raises(LoadError, match="order 1"):
        load_orders_from(
            tmp_path, CUSTOMER, "1,99,2026-01-01,delivered,100,pix,,,", "1,1,93"
        )


@pytest.mark.regression
def test_stops_the_load_when_the_item_points_to_a_nonexistent_product(tmp_path):
    with pytest.raises(LoadError, match="order item 1"):
        load_orders_from(
            tmp_path, CUSTOMER, "1,1,2026-01-01,delivered,100,pix,,,", "1,1,99999"
        )


@pytest.mark.regression
def test_stops_the_load_when_the_item_points_to_a_nonexistent_order(tmp_path):
    with pytest.raises(LoadError, match="order item 7"):
        load_orders_from(
            tmp_path, CUSTOMER, "1,1,2026-01-01,delivered,100,pix,,,", "7,1,93"
        )


@pytest.mark.regression
def test_stops_the_load_when_the_order_total_is_invalid(tmp_path):
    with pytest.raises(LoadError, match="order 1"):
        load_orders_from(
            tmp_path, CUSTOMER, "1,1,2026-01-01,delivered,abc,pix,,,", "1,1,93"
        )


def load_products_from(folder, products):
    write_catalog(folder, products)
    (folder / "promotions.csv").write_text(
        "promotion_id,product_id,discount_percent,description,is_active\n", encoding="utf-8"
    )
    connection = connect(folder / "teste.db")
    try:
        load_catalog(connection, folder)
    finally:
        connection.close()


@pytest.mark.regression
def test_stops_the_load_when_the_product_status_is_invalid(tmp_path):
    with pytest.raises(LoadError, match="product 10"):
        load_products_from(
            tmp_path, "10,100,Guitarra Teste,1,Descricao,1,vendida,{},2024-01-01"
        )


@pytest.mark.regression
def test_stops_the_load_when_the_product_id_is_duplicated(tmp_path):
    row = "10,100,Guitarra Teste,1,Descricao,1,active,{},2024-01-01"

    with pytest.raises(LoadError, match="product 10: duplicate id"):
        load_products_from(tmp_path, f"{row}\n{row}")


@pytest.mark.regression
def test_stops_the_load_when_the_price_has_more_than_two_decimals(tmp_path):
    with pytest.raises(LoadError, match="product 10"):
        load_products_from(
            tmp_path, "10,100.005,Guitarra Teste,1,Descricao,1,active,{},2024-01-01"
        )


@pytest.mark.regression
def test_stops_the_load_when_the_stock_is_negative(tmp_path):
    with pytest.raises(LoadError, match="product 10"):
        load_products_from(
            tmp_path, "10,100,Guitarra Teste,1,Descricao,-1,active,{},2024-01-01"
        )


@pytest.mark.regression
def test_load_failure_preserves_the_previous_database(connection, tmp_path):
    row = "10,100,Guitarra Teste,1,Descricao,1,active,{},2024-01-01"
    write_catalog(tmp_path, f"{row}\n{row}")
    (tmp_path / "promotions.csv").write_text(
        "promotion_id,product_id,discount_percent,description,is_active\n", encoding="utf-8"
    )

    with pytest.raises(LoadError):
        load_catalog(connection, tmp_path)

    assert len(search_products(connection, search_term="Takamine GD20")) == 1


def load_customers_from(folder, *customers):
    (folder / "customers.csv").write_text(
        "customer_id,name,phone,email,city\n" + "\n".join(customers) + "\n", encoding="utf-8"
    )
    connection = connect(folder / "teste.db")
    try:
        load_customers(connection, folder)
        return identify_customer(connection, "(67) 90000-0001")
    finally:
        connection.close()


@pytest.mark.regression
def test_stops_the_load_when_the_customer_phone_is_invalid(tmp_path):
    with pytest.raises(LoadError, match="customer 1"):
        load_customers_from(tmp_path, "1,Cliente Teste,12345,t@exemplo.com,Campo Grande")


@pytest.mark.regression
def test_stops_the_load_when_the_customer_name_is_empty(tmp_path):
    with pytest.raises(LoadError, match="customer 1"):
        load_customers_from(tmp_path, "1, ,(67) 90000-0001,t@exemplo.com,Campo Grande")


@pytest.mark.regression
def test_stops_the_load_when_the_customer_id_is_duplicated(tmp_path):
    with pytest.raises(LoadError, match="customer 1: duplicate id"):
        load_customers_from(
            tmp_path,
            "1,Um,(67) 90000-0001,a@exemplo.com,Campo Grande",
            "1,Dois,(67) 90000-0002,b@exemplo.com,Campo Grande",
        )


@pytest.mark.regression
def test_stops_the_load_when_two_customers_have_the_same_phone(tmp_path):
    with pytest.raises(LoadError, match="customer 2: duplicate phone number"):
        load_customers_from(
            tmp_path,
            "1,Um,(67) 90000-0001,a@exemplo.com,Campo Grande",
            "2,Dois,67 90000-0001,b@exemplo.com,Campo Grande",
        )


def test_phone_with_country_code_is_stored_without_the_code(tmp_path):
    customer = load_customers_from(
        tmp_path, "1,Um,+55 (67) 90000-0001,a@exemplo.com,Campo Grande"
    )

    assert customer is not None
    assert customer.name == "Um"


@pytest.mark.parametrize(
    "order",
    [
        "1,1,2026-01-01,perdido,100,pix,,,",
        "1,1,2026-01-01,delivered,100,cheque,,,",
        "1,1,2026-01-01,delivered,-100,pix,,,",
        "1,1,2026-01-01,delivered,100,credit_13x,,,",
        "1,1,2026-01-01,delivered,100.005,pix,,,",
    ],
)
@pytest.mark.regression
def test_stops_the_load_when_the_order_has_invalid_data(tmp_path, order):
    with pytest.raises(LoadError, match="order 1"):
        load_orders_from(tmp_path, CUSTOMER, order, "1,1,93")


@pytest.mark.regression
def test_stops_the_load_when_the_order_id_is_duplicated(tmp_path):
    order = "1,1,2026-01-01,delivered,100,pix,,,"

    with pytest.raises(LoadError, match="order 1: duplicate id"):
        load_orders_from(tmp_path, CUSTOMER, f"{order}\n{order}", "1,1,93")


@pytest.mark.regression
def test_stops_the_load_when_the_item_quantity_is_not_positive(tmp_path):
    with pytest.raises(LoadError, match="order item 1"):
        load_orders_from(
            tmp_path, CUSTOMER, "1,1,2026-01-01,delivered,100,pix,,,", "1,0,93"
        )


@pytest.mark.parametrize("promotion", ["1,10,101,Oferta,1", "1,10,-5,Oferta,1", "1,10,10,Oferta,2"])
@pytest.mark.regression
def test_stops_the_load_when_the_promotion_has_invalid_data(tmp_path, promotion):
    write_catalog(tmp_path, "10,100,Guitarra Teste,1,Descricao,1,active,{},2024-01-01")
    (tmp_path / "promotions.csv").write_text(
        "promotion_id,product_id,discount_percent,description,is_active\n" + promotion + "\n",
        encoding="utf-8",
    )
    connection = connect(tmp_path / "teste.db")

    with pytest.raises(LoadError, match="promotion 1"):
        load_catalog(connection, tmp_path)

    connection.close()


def test_database_with_only_the_memory_is_not_loaded(tmp_path):
    empty = connect(tmp_path / "vazio.db")

    assert not database_loaded(empty)
    empty.close()


def test_database_with_the_data_loaded_is_ready(connection):
    assert database_loaded(connection)


@pytest.mark.regression
def test_database_loaded_before_the_specifications_asks_for_a_new_load(connection):
    connection.executescript("ALTER TABLE products DROP COLUMN specs;")

    assert not database_loaded(connection)
