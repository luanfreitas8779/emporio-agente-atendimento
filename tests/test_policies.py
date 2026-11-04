import pytest

from src.policies import SECTIONS, get_policies


def test_saturday_opens_from_9_to_13():
    assert "Sábado: 09:00 às 13:00" in get_policies("horarios")


def test_store_closes_on_sundays_and_holidays():
    assert "Domingo e feriados: fechado" in get_policies("horarios")


def test_monday_to_friday_opens_from_9_to_18():
    assert "Segunda a sexta-feira: 09:00 às 18:00" in get_policies("horarios")


def test_gives_the_store_address():
    assert "Rua 14 de Maio, 3200 — Centro" in get_policies("sobre_a_loja")


def test_general_phone_and_whatsapp_are_distinct_numbers():
    text = get_policies("sobre_a_loja")

    assert "Telefone: (67) 3341-4444" in text
    assert "WhatsApp: (67) 3321-4500" in text


def test_contact_email_is_written_without_accent():
    assert "contato@emporiodamusica.com.br" in get_policies("sobre_a_loja")


def test_store_does_not_sell_accessories():
    text = get_policies("sobre_a_loja")

    assert "exclusivamente com instrumentos musicais" in text
    assert "cordas, palhetas, cabos, cases, pedais ou amplificadores" in text


def test_shipping_in_campo_grande_below_500_reais_has_a_35_flat_fee():
    assert "abaixo de R$ 500,00 pagam taxa fixa de R$ 35,00" in get_policies("entregas")


def test_free_shipping_above_500_reais():
    assert "Frete grátis para pedidos acima de R$ 500,00" in get_policies("entregas")


def test_delivery_in_campo_grande_takes_1_to_3_business_days():
    assert "1 a 3 dias úteis" in get_policies("entregas")


def test_wind_instrument_mouthpiece_is_not_eligible_for_exchange():
    assert "Boquilhas de instrumentos de sopro" in get_policies("trocas_e_devolucoes")


def test_regret_lasts_7_days_after_receipt_only_for_online_purchases():
    text = get_policies("trocas_e_devolucoes")

    assert "7 dias corridos após o recebimento" in text
    assert "compras online" in text


def test_defect_exchange_lasts_30_days_after_purchase():
    assert "30 dias corridos após a compra" in get_policies("trocas_e_devolucoes")


def test_ended_promotion_cannot_be_promised():
    assert "Uma promoção encerrada não pode ser prometida" in get_policies("promocoes")


def test_pix_discount_does_not_apply_to_a_promotional_price():
    assert "desconto de PIX não se aplica a preços promocionais" in get_policies("promocoes")


def test_section_outside_the_list_is_rejected():
    with pytest.raises(ValueError, match="fofocas"):
        get_policies("fofocas")


def test_pix_has_a_5_percent_discount_on_the_list_price():
    assert "PIX: pagamento à vista, com 5% de desconto sobre o preço de tabela" in get_policies("pagamentos")


def test_minimum_installment_from_4x_to_6x_is_80_reais_per_the_specific_section():
    assert "De 4x a 6x: parcela mínima de R$ 80,00" in get_policies("pagamentos")


def test_minimum_installment_from_7x_to_12x_is_100_reais():
    assert "De 7x a 12x: parcela mínima de R$ 100,00" in get_policies("pagamentos")


def test_minimum_installment_up_to_3x_is_50_reais():
    assert "De 1x a 3x: parcela mínima de R$ 50,00" in get_policies("pagamentos")


def test_349_90_in_6x_does_not_meet_the_minimum_installment_and_the_maximum_is_4x():
    text = get_policies("pagamentos", amount=349.90, installments=6)

    assert "6x não atende" in text
    assert "máximo de 4x" in text


def test_700_reais_in_7x_meets_the_100_reais_minimum_installment():
    text = get_policies("pagamentos", amount=700, installments=7)

    assert "7x atende" in text
    assert "máximo de 7x de R$ 100,00" in text


def test_complaint_gets_a_reply_within_24_business_hours():
    assert "24 horas úteis" in get_policies("atendimento")


def test_service_does_not_recommend_partner_stores():
    assert "sem indicar lojas" in get_policies("atendimento")


def test_legal_warranty_is_90_days_from_receipt():
    assert "90 dias" in get_policies("garantia")
    assert "recebimento" in get_policies("garantia")


def test_defect_exchange_and_legal_warranty_are_separate_rules():
    assert "regra distinta da garantia legal" in get_policies("garantia")


def test_customer_can_ask_for_data_deletion():
    text = get_policies("privacidade")

    assert "LGPD" in text
    assert "exclusão dos dados" in text


def test_every_specification_section_has_content():
    for section in SECTIONS:
        assert get_policies(section).strip()


@pytest.mark.regression
def test_more_than_12_installments_are_not_offered():
    text = get_policies("pagamentos", amount=5000, installments=13)

    assert "até 12x" in text
    assert "13x" in text
    assert "atende à parcela mínima" not in text


@pytest.mark.parametrize("amount, installments", [(0, 3), (-10, 3), (100, 0), (100, -2)])
@pytest.mark.regression
def test_rejects_non_positive_amount_or_installments(amount, installments):
    with pytest.raises(ValueError):
        get_policies("pagamentos", amount=amount, installments=installments)
