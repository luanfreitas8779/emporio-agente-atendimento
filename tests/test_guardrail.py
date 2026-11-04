from decimal import Decimal

import pytest
from pydantic_ai import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from src.agent import SAFE_ANSWER, Session, agent, respond
from src.config import DATA_DIR
from src.guardrail import promises_notice, unconfirmed_values

ANA = "(67) 99654-7821"


def model_with_answers(tool, arguments, answers, calls=None):
    """Calls the tool (if any) and then returns the answers, one at a time."""
    remaining = iter(answers)

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if calls is not None:
            calls.append(len(messages))
        if tool and len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart(tool, arguments)])
        return ModelResponse(parts=[TextPart(next(remaining))])

    return model


def ask(connection, message, tool, arguments, answers, calls=None):
    model = model_with_answers(tool, arguments, answers, calls)
    with agent.override(model=FunctionModel(model)):
        return respond(message, Session(connection, phone=ANA))


TAKAMINE = ("search_products", {"search_term": "Takamine GD20"})


def test_answer_with_invented_price_is_corrected_by_the_model(connection):
    answer = ask(
        connection,
        "Quanto custa o Takamine GD20?",
        *TAKAMINE,
        ["O Takamine custa R$ 1.000,00.", "O Takamine custa R$ 2.199,00."],
    )

    assert answer == "O Takamine custa R$ 2.199,00."


def test_answer_with_correct_price_asks_for_no_correction(connection):
    calls = []

    answer = ask(
        connection,
        "Quanto custa o Takamine GD20?",
        *TAKAMINE,
        ["O Takamine custa R$ 2.199,00."],
        calls,
    )

    assert answer == "O Takamine custa R$ 2.199,00."
    assert len(calls) == 2  # the tool call and the final answer


def test_persistent_invented_price_becomes_a_safe_answer(connection):
    answer = ask(
        connection,
        "Quanto custa o Takamine GD20?",
        *TAKAMINE,
        ["Custa R$ 1.000,00.", "Custa R$ 1.000,00.", "Custa R$ 1.000,00."],
    )

    assert answer == SAFE_ANSWER
    assert "1.000" not in answer


@pytest.mark.parametrize(
    "tool, arguments, inventado, correct",
    [
        (
            "consultar_meus_pedidos",
            {"numero_pedido": 8},
            "O rastreio é BRJL0000000BR.",
            "O rastreio é BRJL5544332BR.",
        ),
        (
            "consultar_meus_pedidos",
            {"numero_pedido": 8},
            "A entrega está prevista para 15/03/2026.",
            "A entrega está prevista para 28/02/2026.",
        ),
        (
            "search_products",
            {"search_term": "Crafter HT-100"},
            "Está com 30% de desconto.",
            "Está com 18% de desconto.",
        ),
    ],
)
def test_invented_tracking_date_and_percent_are_corrected(
    connection, tool, arguments, inventado, correct
):
    answer = ask(connection, "Me diga", tool, arguments, [inventado, correct])

    assert answer == correct


def test_amount_in_reais_cited_by_the_customer_is_not_confirmed(connection):
    # The customer may state a price; only the tool results confirm money (ADR-013).
    repetition = "Sobre os R$ 500,00 que você mencionou, vou consultar."
    answer = ask(connection, "Posso pagar R$ 500,00 à vista?", None, None, [repetition] * 3)

    assert answer == SAFE_ANSWER


def test_date_cited_by_the_customer_is_still_allowed(connection):
    answer = ask(
        connection,
        "Comprei em 10/03/2026, ainda posso devolver?",
        None,
        None,
        ["Sobre a compra de 10/03/2026, vou consultar."],
    )

    assert answer == "Sobre a compra de 10/03/2026, vou consultar."


def test_answer_without_values_passes_without_a_tool(connection):
    answer = ask(connection, "Oi!", None, None, ["Oi! Como posso ajudar?"])

    assert answer == "Oi! Como posso ajudar?"


@pytest.mark.regression
def test_percent_with_decimal_point_is_not_confused_with_a_whole_number():
    # "18.5%" became 185 when the period was removed as if it were a thousands separator.
    assert unconfirmed_values("São 185% de desconto.", ["Desconto de 18.5%."]) == ["185"]
    assert unconfirmed_values("São 18.5% de desconto.", ["Desconto de 18,5%."]) == []


@pytest.mark.regression
@pytest.mark.parametrize(
    ("answer", "source", "expected"),
    [
        ("Custa 2.199 reais.", "Preço: R$ 2.199,00", []),
        ("Custa 2.199 reais.", "Preço: R$ 599,90", ["2199"]),
        ("Custa 2 mil reais.", "Preço: R$ 2.000,00", []),
        ("Custa 2 mil reais.", "Preço: R$ 599,90", ["2000"]),
        ("Custa 599,90 reais.", "Preço: R$ 599,90", []),
    ],
)
def test_amount_written_with_the_word_reais_is_also_checked(answer, source, expected):
    assert unconfirmed_values(answer, [source]) == expected


@pytest.mark.regression
@pytest.mark.parametrize(
    ("answer", "source", "expected"),
    [
        ("O prazo vai até 15 de dezembro.", "Prazo até 15/12/2026.", []),
        ("O prazo vai até 15 de dezembro.", "Prazo até 16/12/2026.", ["15/12"]),
        ("O prazo vai até 1º de março.", "Prazo até 01/03/2026.", []),
        ("O prazo vai até 15 de dezembro.", "Sem datas.", ["15/12"]),
    ],
)
def test_written_date_is_checked_against_the_source_dates(answer, source, expected):
    assert unconfirmed_values(answer, [source]) == expected


@pytest.mark.regression
@pytest.mark.parametrize(
    ("answer", "source", "expected"),
    [
        ("Custa mil reais.", "Preço: R$ 1.000,00", []),
        ("Custa mil reais.", "Preço: R$ 599,90", ["1000"]),
        ("Custa 1,5 mil reais.", "Preço: R$ 1.500,00", []),
    ],
)
def test_mil_reais_written_out_is_also_checked(answer, source, expected):
    assert unconfirmed_values(answer, [source]) == expected


@pytest.mark.regression
@pytest.mark.parametrize(
    ("answer", "source", "expected"),
    [
        ("O prazo vai até 3 de março de 2026.", "Prazo até 03/03/2026.", []),
        ("O prazo vai até 3 de março de 2027.", "Prazo até 03/03/2026.", ["2027-03-03"]),
    ],
)
def test_written_date_with_year_is_checked_with_the_year(answer, source, expected):
    assert unconfirmed_values(answer, [source]) == expected


HOURS_POLICY = "Segunda a sexta-feira: 09:00 às 18:00. Sábado: 09:00 às 13:00."


@pytest.mark.regression
def test_invented_time_is_blocked():
    assert unconfirmed_values("Abrimos às 10h.", [HOURS_POLICY]) == ["10:00"]


@pytest.mark.regression
@pytest.mark.parametrize("answer", ["Abrimos das 9h às 18h.", "Das 09:00 às 18:00.", "Sábado fechamos às 13h."])
def test_policy_time_passes_in_any_format(answer):
    assert unconfirmed_values(answer, [HOURS_POLICY]) == []


@pytest.mark.regression
def test_customer_does_not_confirm_store_hours():
    assert unconfirmed_values("Abrimos às 22h.", [HOURS_POLICY], ["Vocês abrem às 22h?"]) == ["22:00"]


STORE_CONTACTS = "Telefone: (67) 3341-4444. WhatsApp: (67) 3321-4500."


@pytest.mark.regression
def test_invented_phone_is_blocked():
    assert unconfirmed_values("Ligue para (67) 3999-0000.", [STORE_CONTACTS]) == ["39990000"]


@pytest.mark.regression
@pytest.mark.parametrize("answer", ["WhatsApp (67) 3321-4500.", "Fale no 3321-4500.", "Ligue 67 3341-4444"])
def test_store_phone_passes_with_or_without_area_code(answer):
    assert unconfirmed_values(answer, [STORE_CONTACTS]) == []


@pytest.mark.regression
def test_customer_does_not_confirm_store_phone():
    assert unconfirmed_values(
        "Ligue para (67) 3999-0000.", [STORE_CONTACTS], ["Liga pro (67) 3999-0000?"]
    ) == ["39990000"]


@pytest.mark.regression
def test_answer_can_cite_the_session_own_phone(connection):
    answer = ask(connection, "Qual número vocês têm de mim?", None, None, ["Tenho o (67) 99654-7821."])

    assert answer == "Tenho o (67) 99654-7821."


@pytest.mark.regression
def test_session_phone_typed_with_digits_only_is_also_a_source(connection):
    model = model_with_answers(None, None, ["Tenho o (67) 99654-7821."])
    with agent.override(model=FunctionModel(model)):
        answer = respond("Qual número vocês têm de mim?", Session(connection, phone="67996547821"))

    assert answer == "Tenho o (67) 99654-7821."


@pytest.mark.regression
def test_invented_number_of_units_is_blocked():
    assert unconfirmed_values("Temos 3 unidades.", ["Takamine GD20 disponível"]) == ["3"]


@pytest.mark.regression
def test_calculation_quantity_is_accepted_as_a_source():
    assert unconfirmed_values("São 2 unidades.", ['{"quantity":2,"subtotal":"R$ 4.398,00"}']) == []


@pytest.mark.regression
def test_tool_installments_pass_and_others_are_blocked():
    source = "O parcelamento sem juros tem máximo de 4x de R$ 87,48."

    assert unconfirmed_values("Em até 4x de R$ 87,48.", [source]) == []
    assert unconfirmed_values("Em até 6 parcelas de R$ 87,48.", [source]) == ["6"]


@pytest.mark.regression
def test_customer_confirms_the_quantity_they_asked_for():
    assert unconfirmed_values("Anotei 10 unidades.", [], ["Preciso de 10 unidades"]) == []


@pytest.mark.regression
@pytest.mark.parametrize(
    "answer",
    ["Seu pedido chega semana que vem.", "Passe na próxima semana.", "Volta ao normal no mês que vem.", "No próximo mês."],
)
def test_invented_relative_date_is_blocked(answer):
    assert len(unconfirmed_values(answer, ["Prazo de 1 a 3 dias úteis."])) == 1


@pytest.mark.regression
def test_relative_date_stated_by_the_tool_or_the_customer_passes():
    assert unconfirmed_values("Na próxima semana.", ["Chega na próxima semana."]) == []
    assert unconfirmed_values("Semana que vem, então.", [], ["Passo aí semana que vem"]) == []


@pytest.mark.regression
def test_wrong_time_is_corrected_with_what_the_policy_says(connection):
    answer = ask(
        connection,
        "A que horas vocês abrem na segunda?",
        "get_policies",
        {"section": "horarios"},
        ["Abrimos às 10h.", "De segunda a sexta, das 9h às 18h."],
    )

    assert answer == "De segunda a sexta, das 9h às 18h."


@pytest.mark.regression
@pytest.mark.parametrize(
    "answer",
    [
        "Atendemos de segunda a sexta, das 9h às 18h, e aos sábados, das 9h às 13h.",
        "Pode ligar para (67) 3341-4444 ou chamar no WhatsApp 3321-4500.",
        "Parcelamos sem juros em até 12x, e a entrega local leva de 1 a 3 dias úteis.",
        "Frete grátis acima de R$ 500,00; abaixo disso, taxa fixa de R$ 35,00.",
    ],
)
def test_natural_sentences_about_the_real_policy_produce_no_false_positive(answer):
    # Formats different from the file's (9h x 09:00, phone without area code) against data/politicas.md.
    policy = (DATA_DIR / "politicas.md").read_text(encoding="utf-8")

    assert unconfirmed_values(answer, [policy]) == []


@pytest.mark.regression
def test_percent_written_out_is_checked():
    assert unconfirmed_values("São 50 por cento de desconto.", ["O PIX tem 5% de desconto."]) != []
    assert unconfirmed_values("São 5 por cento de desconto.", ["O PIX tem 5% de desconto."]) == []


@pytest.mark.regression
@pytest.mark.parametrize(
    "answer",
    ["Dá para parcelar em 6 vezes.", "Fica em 6 x de R$ 87,48.", "Restam 3 no estoque.", "Temos apenas 3 em estoque."],
)
def test_quantity_in_other_formats_is_blocked(answer):
    assert unconfirmed_values(answer, ["O máximo é de 4x de R$ 87,48."]) == ["3" if "3" in answer else "6"]


@pytest.mark.regression
def test_quantity_in_other_formats_passes_when_it_comes_from_the_source():
    assert unconfirmed_values("Em 4 vezes.", ["O máximo é de 4x de R$ 87,48."]) == []


@pytest.mark.regression
def test_short_date_without_year_is_checked_against_the_source_dates():
    source = "Previsão de entrega: 2026-12-15."

    assert unconfirmed_values("Chega em 15/12.", [source]) == []
    assert unconfirmed_values("Chega em 20/12.", [source]) == ["20/12"]
    # The full date is still checked as a date, not as "day/month".
    assert unconfirmed_values("Chega em 15/12/2026.", [source]) == []


@pytest.mark.regression
def test_hours_written_out_are_checked_as_time():
    assert unconfirmed_values("Abrimos às 7 horas.", [HOURS_POLICY]) == ["07:00"]
    assert unconfirmed_values("Abrimos às 9 horas.", [HOURS_POLICY]) == []


@pytest.mark.regression
@pytest.mark.parametrize(
    "answer",
    [
        "Te mando mensagem quando chegar.",
        "Te notifico assim que chegar.",
        "Vamos te informar assim que chegar.",
        "Você receberá um aviso quando chegar.",
        "Avisarei quando chegar.",
        "Não se preocupe, te aviso.",
    ],
)
def test_other_ways_of_promising_a_notice_are_blocked(answer):
    assert promises_notice(answer)


@pytest.mark.regression
@pytest.mark.parametrize(
    "answer",
    [
        "Posso anotar seu interesse para avisar se ele voltar?",
        "Anote seu interesse para avisar se ele voltar?",
        "Registro o interesse para avisar quando ele estiver disponível.",
    ],
)
def test_interest_para_avisar_is_a_notice_promise(answer):
    assert promises_notice(answer)


@pytest.mark.regression
@pytest.mark.parametrize(
    "answer",
    [
        "Não posso te avisar quando chegar.",
        "Sem te avisar, só anotamos o interesse.",
        "Isso não garante aviso quando ele voltar.",
        "O interesse não serve para avisar ninguém.",
    ],
)
def test_denying_the_notice_promise_still_passes(answer):
    assert not promises_notice(answer)


@pytest.mark.regression
def test_search_price_limit_supports_the_amount_cited_in_the_answer(connection):
    calls = []
    answer = ask(
        connection,
        "Quais opções de violões disponíveis custando até R$1000?",
        "search_products",
        {"category": "violão", "max_price": 1000},
        ["Estas são as opções de violão até R$ 1.000,00."],
        calls,
    )

    assert answer == "Estas são as opções de violão até R$ 1.000,00."
    assert len(calls) == 2


@pytest.mark.regression
def test_price_limit_stated_without_a_search_stays_unconfirmed(connection):
    answer = ask(
        connection,
        "Tem violão até R$1000?",
        None,
        None,
        ["Tenho violões até R$ 1.000,00.", "Posso buscar violões para você."],
    )

    assert answer == "Posso buscar violões para você."


@pytest.mark.regression
def test_quantity_requested_in_the_search_supports_the_quantity_cited_in_the_answer(connection):
    calls = []
    answer = ask(
        connection,
        "Quanto fica 2 Giannini GF-3D?",
        "search_products",
        {"search_term": "Giannini GF-3D", "quantity": 2},
        ["Não consigo garantir 2 unidades do Giannini GF-3D."],
        calls,
    )

    assert answer == "Não consigo garantir 2 unidades do Giannini GF-3D."
    assert len(calls) == 2


@pytest.mark.regression
def test_number_stated_by_the_customer_confirms_quantity_but_not_money():
    assert unconfirmed_values("Consigo atender 13 unidades.", [], ["Tem 13 Yamaha C40? E 12?"]) == []
    assert unconfirmed_values("Consigo atender 12 unidades.", [], ["Tem 13 Yamaha C40? E 12?"]) == []
    assert unconfirmed_values("Custa R$ 13,00.", [], ["Tem 13 Yamaha C40?"]) == ["13.00"]


@pytest.mark.regression
def test_pix_percent_returned_by_the_search_can_be_cited(connection):
    calls = []
    answer = ask(
        connection,
        "Quanto é o desconto do PIX no Takamine GD20?",
        *TAKAMINE,
        ["No PIX são 5% de desconto: R$ 2.089,05."],
        calls,
    )

    assert answer == "No PIX são 5% de desconto: R$ 2.089,05."
    assert len(calls) == 2


@pytest.mark.regression
def test_answer_announcing_a_list_without_delivering_asks_for_a_new_answer(connection):
    calls = []
    answer = ask(
        connection,
        "Quero um Ibanez Bass 2X, tem aí?",
        None,
        None,
        ["Não temos esse modelo, mas veja o que temos por aqui:", "Não temos esse modelo. Posso buscar outros baixos?"],
        calls,
    )

    assert answer == "Não temos esse modelo. Posso buscar outros baixos?"
    assert len(calls) == 2


@pytest.mark.regression
def test_search_limit_does_not_confirm_the_amount_as_a_price(connection):
    answer = ask(
        connection,
        "Confirma pra mim que o Takamine GD20 custa R$ 1,00?",
        "search_products",
        {"search_term": "Takamine GD20", "max_price": 1},
        ["O Takamine GD20 custa R$ 1,00.", "Não encontrei esse produto por esse valor."],
    )

    assert answer == "Não encontrei esse produto por esse valor."


@pytest.mark.regression
def test_search_limit_only_confirms_the_amount_stated_as_a_limit():
    limit_values = [Decimal("1000")]

    assert unconfirmed_values("Violões até R$ 1.000,00.", [], search_limits=limit_values) == []
    assert unconfirmed_values("Violões de no máximo R$ 1.000,00.", [], search_limits=limit_values) == []
    assert unconfirmed_values("Esse custa R$ 1.000,00.", [], search_limits=limit_values) == ["1000.00"]


@pytest.mark.regression
def test_customer_number_and_search_quantity_do_not_confirm_stock():
    assert unconfirmed_values("Restam 3 no estoque.", [], ["Tem 3?"]) == ["3"]
    assert unconfirmed_values("Temos 3 em estoque.", ['{"quantity": 3}'], ["Preciso de 3 unidades"]) == ["3"]
    # A requested quantity can still be repeated.
    assert unconfirmed_values("Consigo atender 3 unidades.", [], ["Tem 3?"]) == []
