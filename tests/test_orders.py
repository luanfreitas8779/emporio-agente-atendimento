from datetime import date

import pytest

from src.orders import get_orders, identify_customer


def test_identifies_the_customer_by_masked_phone(connection):
    customer = identify_customer(connection, "(67) 99654-7821")

    assert customer is not None
    assert customer.id == 2
    assert customer.name == "Ana Carolina Ferreira"


def test_unregistered_phone_identifies_no_one(connection):
    assert identify_customer(connection, "(67) 90000-0000") is None


def test_identifies_the_customer_by_phone_with_digits_only(connection):
    customer = identify_customer(connection, "67996547821")

    assert customer is not None
    assert customer.id == 2


def test_customer_2_looks_up_order_8_with_status_and_tracking(connection):
    (order,) = get_orders(connection, customer_id=2, number=8)

    assert order.number == 8
    assert order.status == "shipped"
    assert order.rastreio == "BRJL5544332BR"
    assert order.estimated_delivery == "28/02/2026"


def test_another_customers_order_is_treated_as_not_found(connection):
    # Order 5 belongs to customer 5.
    assert get_orders(connection, customer_id=2, number=5) == []


def test_without_number_lists_only_the_customers_orders(connection):
    order_list = get_orders(connection, customer_id=3)

    assert [p.number for p in order_list] == [1, 19]


def test_order_shows_items_date_and_payment(connection):
    (order,) = get_orders(connection, customer_id=2, number=8)

    assert order.order_date == "15/02/2026"
    assert order.payment == "débito"
    assert [(i.name, i.quantity) for i in order.items] == [("Kala KA-C Concert Mogno", 1)]


def test_shows_the_recorded_total_even_when_it_differs_from_the_sum_of_items(connection):
    # Order 3: 2 x R$ 1.749,00 add up to R$ 3.498,00, but the recorded total is R$ 3.450,00.
    (order,) = get_orders(connection, customer_id=12, number=3)

    assert order.total == "R$ 3.450,00"
    assert order.payment == "cartão de crédito em 12x"
    assert [(i.name, i.quantity) for i in order.items] == [
        ("Kala KA-ABP-CTG Barítono Cedar", 2)
    ]


def test_identifies_the_customer_by_phone_with_country_code(connection):
    for phone in ("+55 (67) 99654-7821", "5567996547821"):
        customer = identify_customer(connection, phone)

        assert customer is not None
        assert customer.id == 2


def test_incomplete_phone_identifies_no_one(connection):
    assert identify_customer(connection, "99654-7821") is None
    assert identify_customer(connection, "") is None


def test_customer_gives_the_first_name(connection):
    customer = identify_customer(connection, "(67) 99654-7821")

    assert customer.first_name == "Ana"


@pytest.mark.parametrize(
    "customer, number, status_description",
    [
        (3, 1, "entregue"),
        (6, 9, "confirmado"),
        (8, 13, "pendente"),
        (2, 8, "enviado"),
        (15, 17, "cancelado"),
    ],
)
def test_order_includes_the_status_description_translated_in_code(connection, customer, number, status_description):
    (order,) = get_orders(connection, customer_id=customer, number=number)

    assert order.status_description == status_description


@pytest.mark.regression
def test_shipped_order_after_the_estimated_delivery_reports_the_days_of_delay(connection):
    # Order 8: shipped, estimated delivery on 28/02/2026 (DQ-16).
    (order,) = get_orders(connection, customer_id=2, number=8, today=date(2026, 3, 25))

    assert order.delay == "A entrega estimada era 28/02/2026 e o pedido segue como enviado: 25 dias de atraso."


def test_order_within_the_estimate_has_no_delay(connection):
    (order,) = get_orders(connection, customer_id=2, number=8, today=date(2026, 2, 28))

    assert order.delay is None
