from datetime import date

import pytest

from src.config import reference_date
from src.returns import assess_return


def test_online_purchase_three_days_after_delivery_is_within_the_regret_deadline(connection):
    # Order 7 (customer 14): estimated delivery on 17/02/2026, 7-day deadline until 24/02/2026.
    verdict = assess_return(
        connection, customer_id=14, number=7, reason="arrependimento", channel="online",
        today=date(2026, 2, 20),
    )

    assert verdict.result == "dentro_do_prazo"
    assert [(r.name, r.result, r.deadline) for r in verdict.rules] == [
        ("arrependimento", "dentro_do_prazo", "24/02/2026")
    ]


def test_order_7_with_the_default_date_is_past_the_regret_deadline(connection, monkeypatch):
    monkeypatch.delenv("DATA_DE_REFERENCIA", raising=False)

    verdict = assess_return(
        connection, customer_id=14, number=7, reason="arrependimento", channel="online",
        today=reference_date(),
    )

    assert verdict.result == "fora_do_prazo"
    assert verdict.rules[0].deadline == "24/02/2026"


def test_in_person_purchase_does_not_use_the_online_regret_rule(connection):
    # Within 7 days of delivery, but the purchase was made in the store (DQ-24).
    verdict = assess_return(
        connection, customer_id=14, number=7, reason="arrependimento", channel="presencial",
        today=date(2026, 2, 20),
    )

    assert verdict.result == "nao_se_aplica"
    assert verdict.rules == []
    assert any("compras online" in warning for warning in verdict.notices)


def test_regret_without_channel_asks_for_the_purchase_channel(connection):
    verdict = assess_return(
        connection, customer_id=14, number=7, reason="arrependimento", channel=None,
        today=date(2026, 2, 20),
    )

    assert verdict.result == "faltam_dados"
    assert verdict.missing == ["canal_de_compra"]
    assert verdict.rules == []


def test_order_7_with_a_defect_is_past_30_days_and_within_the_legal_warranty(connection):
    # Purchase on 03/02/2026 (30 days until 05/03) and estimated delivery on 17/02/2026 (90 days until 18/05).
    verdict = assess_return(
        connection, customer_id=14, number=7, reason="defeito", channel=None,
        today=date(2026, 3, 25),
    )

    assert verdict.result == "dentro_do_prazo"
    assert [(r.name, r.result, r.deadline) for r in verdict.rules] == [
        ("troca_por_defeito", "fora_do_prazo", "05/03/2026"),
        ("garantia_legal", "dentro_do_prazo", "18/05/2026"),
    ]


def test_another_customers_order_is_not_assessed(connection):
    # Order 7 belongs to customer 14.
    verdict = assess_return(
        connection, customer_id=2, number=7, reason="defeito", channel=None, today=date(2026, 3, 25),
    )

    assert verdict.result == "pedido_nao_encontrado"
    assert verdict.rules == []


@pytest.mark.parametrize(
    "customer, number, warning",
    [
        (8, 13, "ainda não foi enviado"),
        (6, 9, "ainda não foi enviado"),
        (15, 17, "foi cancelado"),
    ],
)
def test_order_without_delivery_has_nothing_to_return(connection, customer, number, warning):
    verdict = assess_return(
        connection, customer_id=customer, number=number, reason="defeito", channel=None,
        today=date(2026, 3, 25),
    )

    assert verdict.result == "nao_se_aplica"
    assert verdict.rules == []
    assert any(warning in a for a in verdict.notices)


def test_preference_exchange_lasts_7_days_from_receipt(connection):
    within = assess_return(
        connection, customer_id=14, number=7, reason="preferencia", channel=None, today=date(2026, 2, 24),
    )
    outside = assess_return(
        connection, customer_id=14, number=7, reason="preferencia", channel=None, today=date(2026, 2, 25),
    )

    assert [(r.name, r.deadline) for r in within.rules] == [("troca_por_preferencia", "24/02/2026")]
    assert (within.result, outside.result) == ("dentro_do_prazo", "fora_do_prazo")


def test_verdict_states_that_receipt_is_approximate_and_depends_on_the_product_analysis(connection):
    verdict = assess_return(
        connection, customer_id=14, number=7, reason="arrependimento", channel="online",
        today=date(2026, 2, 20),
    )

    assert verdict.approximate_date is True
    assert verdict.receipt_date == "17/02/2026"
    assert any("entrega estimada" in a for a in verdict.notices)
    assert any("análise do produto" in a for a in verdict.notices)
    assert verdict.reference_date == "20/02/2026"


@pytest.mark.parametrize("channel", [None, "presencial", "online"])
@pytest.mark.regression
def test_another_customers_order_comes_back_as_not_found_for_regret_with_any_channel(
    connection, channel
):
    # Order 7 belongs to customer 14, and order 999 does not exist.
    for number in (7, 999):
        verdict = assess_return(
            connection, customer_id=2, number=number, reason="arrependimento", channel=channel,
            today=date(2026, 2, 20),
        )

        assert verdict.result == "pedido_nao_encontrado"
        assert verdict.missing == []


def test_shipped_order_with_future_estimated_delivery_warns_the_deadline_counts_from_receipt(connection):
    # Order 8 (customer 2): shipped, estimated delivery on 28/02/2026.
    verdict = assess_return(
        connection, customer_id=2, number=8, reason="arrependimento", channel="online",
        today=date(2026, 2, 20),
    )

    assert verdict.result == "dentro_do_prazo"
    assert any("ainda não chegou" in warning for warning in verdict.notices)


def test_order_whose_estimated_delivery_has_passed_gets_no_on_the_way_notice(connection):
    verdict = assess_return(
        connection, customer_id=2, number=8, reason="arrependimento", channel="online",
        today=date(2026, 3, 25),
    )

    assert verdict.result == "fora_do_prazo"
    assert not any("ainda não chegou" in warning for warning in verdict.notices)
