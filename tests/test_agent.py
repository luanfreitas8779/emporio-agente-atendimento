import asyncio
from datetime import date

import pytest
from pydantic_ai import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from src import calculations, catalog
from src.agent import SAFE_ANSWER, NO_CUSTOMER_RECORD, Session, agent, respond
from src.database import connect
from src.interests import list_pending, register
from src.load_data import read_csv
from src.memory import ConversationState, load_state, conversation_for_display, save_state
from src.restock import restock
from tests.conftest import DATA_DIR


def model_that_looks_up_the_price(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    if len(messages) == 1:
        return ModelResponse(
            parts=[ToolCallPart("search_products", {"search_term": "Takamine GD20"})]
        )
    result = messages[-1].parts[0].content
    return ModelResponse(parts=[TextPart(f"Encontrei: {result}")])


def test_answers_with_the_price_from_the_catalog(connection):
    with agent.override(model=FunctionModel(model_that_looks_up_the_price)):
        answer = respond("Quanto custa o Takamine GD20?", Session(connection))

    assert "R$ 2.199,00" in answer


@pytest.mark.regression
def test_answers_with_an_async_loop_running(connection):
    async def respond_inside_the_loop():
        return respond("Quanto custa o Takamine GD20?", Session(connection))

    with agent.override(model=FunctionModel(model_that_looks_up_the_price)):
        answer = asyncio.run(respond_inside_the_loop())

    assert "R$ 2.199,00" in answer


def model_that_searches_available_guitars_up_to_1000(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    if len(messages) == 1:
        arguments = {
            "category": "Violões",
            "max_price": 1000,
            "only_available": True,
        }
        return ModelResponse(parts=[ToolCallPart("search_products", arguments)])
    products = messages[-1].parts[0].content
    return ModelResponse(parts=[TextPart(str(len(products)))])


def test_agent_lists_the_12_available_guitars_up_to_1000_reais(connection):
    with agent.override(
        model=FunctionModel(model_that_searches_available_guitars_up_to_1000)
    ):
        answer = respond("Violões disponíveis até R$ 1000?", Session(connection))

    assert answer == "12"


def model_that_lists_the_active_promotions(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    if len(messages) == 1:
        return ModelResponse(parts=[ToolCallPart("search_products", {"only_on_sale": True})])
    products = messages[-1].parts[0].content
    rows = [f"{p.name}: {p.price}, {p.discount_percent}%, {p.final_price}" for p in products]
    return ModelResponse(parts=[TextPart("\n".join(rows))])


def test_agent_lists_the_4_products_on_sale_with_original_price_percent_and_final_price(connection):
    with agent.override(model=FunctionModel(model_that_lists_the_active_promotions)):
        answer = respond("Quais produtos estão em promoção agora?", Session(connection))

    assert len(answer.splitlines()) == 4
    assert "Crafter HT-100 Folk Aço Natural: R$ 2.399,00, 18%, R$ 1.967,18" in answer


def model_that_suggests_alternatives_to_the_unavailable_product(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    results = [
        part.content
        for message in messages
        for part in message.parts
        if part.part_kind == "tool-return"
    ]
    if not results:
        return ModelResponse(
            parts=[ToolCallPart("search_products", {"search_term": "Giannini GF-3D"})]
        )
    if len(results) == 1:
        (giannini,) = results[0]
        assert giannini.availability == "indisponivel"
        arguments = {"category": giannini.category, "only_available": True}
        return ModelResponse(parts=[ToolCallPart("search_products", arguments)])
    names = [product.name for product in results[1]]
    return ModelResponse(parts=[TextPart("; ".join(names))])


def test_agent_finds_available_alternatives_for_an_out_of_stock_product(connection):
    with agent.override(
        model=FunctionModel(model_that_suggests_alternatives_to_the_unavailable_product)
    ):
        answer = respond("Tem o Giannini GF-3D?", Session(connection))

    assert "Yamaha C40 Nylon Natural" in answer
    assert "Giannini GF-3D" not in answer


def model_that_checks_the_opening_hours(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    if len(messages) == 1:
        return ModelResponse(
            parts=[ToolCallPart("get_policies", {"section": "horarios"})]
        )
    return ModelResponse(parts=[TextPart(messages[-1].parts[0].content)])


def test_agent_answers_saturday_hours_from_the_policy(connection):
    with agent.override(model=FunctionModel(model_that_checks_the_opening_hours)):
        answer = respond("Abre sábado?", Session(connection))

    assert "Sábado: 09:00 às 13:00" in answer


def model_that_calculates_the_installments(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    if len(messages) == 1:
        arguments = {"section": "pagamentos", "amount": 349.90, "installments": 6}
        return ModelResponse(parts=[ToolCallPart("get_policies", arguments)])
    return ModelResponse(parts=[TextPart(messages[-1].parts[0].content)])


def test_agent_states_that_349_90_in_6x_does_not_meet_the_minimum_installment(connection):
    with agent.override(model=FunctionModel(model_that_calculates_the_installments)):
        answer = respond("Dá pra pagar R$ 349,90 em 6x?", Session(connection))

    assert "6x não atende" in answer


def model_that_asks_for_a_nonexistent_section(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    if len(messages) == 1:
        return ModelResponse(
            parts=[ToolCallPart("get_policies", {"section": "fofocas"})]
        )
    return ModelResponse(parts=[TextPart("tentou de novo")])


def test_agent_rejects_a_section_outside_the_list_and_the_model_tries_again(connection):
    with agent.override(model=FunctionModel(model_that_asks_for_a_nonexistent_section)):
        answer = respond("Me conta uma fofoca", Session(connection))

    assert answer == "tentou de novo"


def model_that_calls(tool: str, arguments: dict, captured: list):
    """Calls the tool once and stores the result, without depending on its text."""

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart(tool, arguments)])
        captured.append(messages[-1].parts[0])
        return ModelResponse(parts=[TextPart("ok")])

    return model


def call_tool(connection, phone, tool, arguments):
    captured: list = []
    with agent.override(model=FunctionModel(model_that_calls(tool, arguments, captured))):
        respond("Teste", Session(connection, phone=phone))
    return captured[0]


ANA = "(67) 99654-7821"


def test_identified_customer_looks_up_the_status_and_tracking_of_order_8(connection):
    returned = call_tool(connection, ANA, "get_my_orders", {"order_number": 8})

    (order,) = returned.content
    assert order.status == "shipped"
    assert order.rastreio == "BRJL5544332BR"


def test_unregistered_phone_gets_the_explanation_that_there_are_no_orders(connection):
    returned = call_tool(
        connection, "(67) 90000-0000", "get_my_orders", {"order_number": 8}
    )

    assert returned.content == NO_CUSTOMER_RECORD


def test_session_without_phone_also_does_not_look_up_orders(connection):
    returned = call_tool(connection, None, "get_my_orders", {"order_number": 8})

    assert returned.content == NO_CUSTOMER_RECORD


def test_another_customers_order_comes_back_empty_to_the_agent(connection):
    # Order 5 belongs to customer 5.
    returned = call_tool(connection, ANA, "get_my_orders", {"order_number": 5})

    assert returned.content == []


@pytest.mark.regression
def test_message_cannot_change_the_customer_looked_up(connection):
    # Order 4 belongs to customer 1; the session belongs to customer 2.
    returned = call_tool(
        connection, ANA, "get_my_orders", {"order_number": 4, "customer_id": 1}
    )

    # The extra argument is rejected and no order is looked up.
    assert returned.outcome == "retried"
    assert returned.content[0]["type"] == "extra_forbidden"


def model_that_returns_the_instructions(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    return ModelResponse(parts=[TextPart(info.instructions or "")])


def test_registered_customer_is_called_by_name(connection):
    session = Session(connection, phone="(67) 99654-7821")

    with agent.override(model=FunctionModel(model_that_returns_the_instructions)):
        instructions = respond("Oi!", session)

    assert "Ana" in instructions
    assert "Carolina" not in instructions
    assert "Ferreira" not in instructions


def test_instructions_do_not_expose_personal_data_beyond_the_name(connection):
    session = Session(connection, phone=ANA)

    with agent.override(model=FunctionModel(model_that_returns_the_instructions)):
        instructions = respond("Oi!", session)

    # The source of the values is the CSV, not the code under test.
    for customer in read_csv(DATA_DIR / "customers.csv"):
        assert customer["email"] not in instructions
        assert customer["phone"] not in instructions


def test_orders_result_does_not_expose_email_or_city(connection):
    returned = call_tool(connection, ANA, "get_my_orders", {})

    text = repr(returned.content)
    for customer in read_csv(DATA_DIR / "customers.csv"):
        assert customer["email"] not in text
    assert "Campo Grande" not in text


def test_unregistered_phone_gets_no_name_in_the_instructions(connection):
    session = Session(connection, phone="(67) 90000-0000")

    with agent.override(model=FunctionModel(model_that_returns_the_instructions)):
        instructions = respond("Oi!", session)

    assert "sem cadastro" in instructions


def model_that_sends_arguments(tool: str, arguments: dict):
    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        asked_for_correction = any(
            getattr(part, "outcome", None) == "retried" or part.part_kind == "retry-prompt"
            for message in messages
            for part in message.parts
        )
        if asked_for_correction:
            return ModelResponse(parts=[TextPart("argumento recusado")])
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart(tool, arguments)])
        return ModelResponse(parts=[TextPart("argumento aceito")])

    return model


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("get_policies", {"section": "pagamentos", "amount": -5}),
        ("get_policies", {"section": "pagamentos", "amount": 100, "installments": 0}),
        ("search_products", {"max_price": -1}),
        ("get_my_orders", {"order_number": 0}),
    ],
)
@pytest.mark.regression
def test_tools_reject_out_of_range_arguments(connection, tool, arguments):
    session = Session(connection, phone="(67) 99654-7821")

    with agent.override(model=FunctionModel(model_that_sends_arguments(tool, arguments))):
        answer = respond("Teste", session)

    assert answer == "argumento recusado"


@pytest.mark.regression
def test_model_receives_the_translated_status_description_not_the_raw_status(connection):
    returned = call_tool(connection, ANA, "get_my_orders", {"order_number": 8})

    seen_by_model = returned.model_response_str()
    assert "enviado" in seen_by_model
    assert "shipped" not in seen_by_model


def model_that_lists_the_questions_seen(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    questions = [
        part.content
        for message in messages
        for part in message.parts
        if part.part_kind == "user-prompt"
    ]
    return ModelResponse(parts=[TextPart(" | ".join(questions))])


def test_second_message_reaches_the_model_together_with_the_first(connection):
    session = Session(connection, phone=ANA)

    with agent.override(model=FunctionModel(model_that_lists_the_questions_seen)):
        respond("Quero um violão", session)
        answer = respond("E o mais barato?", session)

    assert answer == "Quero um violão | E o mais barato?"


def test_new_session_with_the_same_phone_recovers_the_conversation(connection, tmp_path):
    with agent.override(model=FunctionModel(model_that_lists_the_questions_seen)):
        respond("Quero um violão", Session(connection, phone=ANA))

        # Another connection to the same file is equivalent to restarting the application.
        new_one = connect(tmp_path / "teste.db")
        try:
            answer = respond("Chegou?", Session(new_one, phone="67996547821"))
        finally:
            new_one.close()

    assert answer == "Quero um violão | Chegou?"


def test_different_phone_does_not_receive_another_persons_history(connection):
    with agent.override(model=FunctionModel(model_that_lists_the_questions_seen)):
        respond("Quero um violão", Session(connection, phone=ANA))
        answer = respond("Oi", Session(connection, phone="(67) 90000-0000"))

    assert answer == "Oi"


def test_session_without_valid_phone_does_not_store_the_conversation(connection):
    with agent.override(model=FunctionModel(model_that_lists_the_questions_seen)):
        respond("Quero um violão", Session(connection, phone="123"))
        answer = respond("Oi", Session(connection, phone="123"))

    assert answer == "Oi"


def model_that_checks_the_hours_and_lists_the_questions(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    if messages[-1].parts[0].part_kind == "user-prompt":
        return ModelResponse(
            parts=[ToolCallPart("get_policies", {"section": "horarios"})]
        )
    return model_that_lists_the_questions_seen(messages, info)


@pytest.mark.regression
def test_history_sent_to_the_model_does_not_separate_tool_call_from_result(connection, monkeypatch):
    # A small limit forces the cut in the middle of a turn with a tool.
    monkeypatch.setattr("src.memory.MAX_HISTORY_MESSAGES", 7)
    session = Session(connection, phone=ANA)

    with agent.override(
        model=FunctionModel(model_that_checks_the_hours_and_lists_the_questions)
    ):
        for question in ("P1", "P2", "P3"):
            respond(question, session)
        answer = respond("P4", session)

    # Each turn with a tool has 4 messages: only one whole turn would fit in 7.
    assert answer == "P3 | P4"


def model_that_repeats_a_price_from_a_previous_turn(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    last = messages[-1].parts[0]
    if last.part_kind == "user-prompt" and last.content == "Quanto custa?":
        return ModelResponse(
            parts=[ToolCallPart("search_products", {"search_term": "Takamine GD20"})]
        )
    if last.part_kind == "tool-return":
        return ModelResponse(parts=[TextPart("Custa R$ 2.199,00")])
    return ModelResponse(parts=[TextPart("Continua R$ 2.199,00")])


@pytest.mark.regression
def test_guardrail_does_not_accept_a_value_cited_only_in_a_previous_turn(connection):
    session = Session(connection, phone=ANA)

    with agent.override(model=FunctionModel(model_that_repeats_a_price_from_a_previous_turn)):
        first = respond("Quanto custa?", session)
        second = respond("E agora?", session)

    assert first == "Custa R$ 2.199,00"
    assert second == SAFE_ANSWER


def model_that_invents_a_price_until_the_next_question(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    # The correction requested by the guardrail also arrives as a customer message, so
    # the model insists while the next question has not appeared yet.
    questions = [
        part.content
        for message in messages
        for part in message.parts
        if part.part_kind == "user-prompt"
    ]
    if "Preço do violão?" in questions and "Oi" not in questions:
        return ModelResponse(parts=[TextPart("Custa R$ 9,99")])
    return model_that_lists_the_questions_seen(messages, info)


def test_safe_answer_also_enters_the_history(connection):
    session = Session(connection, phone=ANA)

    with agent.override(model=FunctionModel(model_that_invents_a_price_until_the_next_question)):
        safe = respond("Preço do violão?", session)
        answer = respond("Oi", session)

    assert safe == SAFE_ANSWER
    assert answer == "Preço do violão? | Oi"


@pytest.mark.regression
def test_corrupted_history_is_ignored_and_the_service_continues(connection):
    session = Session(connection, phone=ANA)

    with agent.override(model=FunctionModel(model_that_lists_the_questions_seen)):
        respond("Quero um violão", session)
        connection.execute("UPDATE messages SET content = 'não é json'")
        answer = respond("Oi", session)

    assert answer == "Oi"


def model_that_searches_one_product_and_then_shows_the_instructions(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    last = messages[-1].parts[0]
    if last.part_kind == "user-prompt" and last.content == "Tem o Giannini?":
        return ModelResponse(
            parts=[ToolCallPart("search_products", {"search_term": "Giannini GF-3D"})]
        )
    if last.part_kind == "tool-return":
        return ModelResponse(parts=[TextPart("ok")])
    return ModelResponse(parts=[TextPart(info.instructions or "")])


def test_single_product_found_stays_in_focus_in_the_following_messages(connection):
    session = Session(connection, phone=ANA)

    with agent.override(
        model=FunctionModel(model_that_searches_one_product_and_then_shows_the_instructions)
    ):
        respond("Tem o Giannini?", session)
        instructions = respond("E o preço?", session)

    assert "Produto em foco: Giannini GF-3D" in instructions


def model_that_looks_up_order_8_and_then_shows_the_instructions(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    last = messages[-1].parts[0]
    if last.part_kind == "user-prompt" and last.content == "Cadê meu pedido?":
        return ModelResponse(
            parts=[ToolCallPart("get_my_orders", {"order_number": 8})]
        )
    if last.part_kind == "tool-return":
        return ModelResponse(parts=[TextPart("ok")])
    return ModelResponse(parts=[TextPart(info.instructions or "")])


def test_looked_up_order_stays_under_review_in_the_following_messages(connection):
    session = Session(connection, phone=ANA)

    with agent.override(
        model=FunctionModel(model_that_looks_up_order_8_and_then_shows_the_instructions)
    ):
        respond("Cadê meu pedido?", session)
        instructions = respond("E o rastreio?", session)

    assert "Pedido em análise: 8" in instructions


def test_state_survives_restart_and_does_not_leak_to_another_phone(connection, tmp_path):
    model = FunctionModel(model_that_searches_one_product_and_then_shows_the_instructions)
    with agent.override(model=model):
        respond("Tem o Giannini?", Session(connection, phone=ANA))

        new_one = connect(tmp_path / "teste.db")
        try:
            anas = respond("E o preço?", Session(new_one, phone="67996547821"))
            from_someone_else = respond("E o preço?", Session(new_one, phone="(67) 90000-0000"))
        finally:
            new_one.close()

    assert "Produto em foco: Giannini GF-3D" in anas
    assert "Produto em foco" not in from_someone_else


def model_that_searches_several_products_and_then_shows_the_instructions(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    last = messages[-1].parts[0]
    if last.part_kind == "user-prompt" and last.content == "Quais violões?":
        return ModelResponse(parts=[ToolCallPart("search_products", {"category": "Violões"})])
    if last.part_kind == "tool-return":
        return ModelResponse(parts=[TextPart("ok")])
    return ModelResponse(parts=[TextPart(info.instructions or "")])


def test_search_with_several_results_does_not_set_a_product_in_focus(connection):
    session = Session(connection, phone=ANA)

    with agent.override(
        model=FunctionModel(model_that_searches_several_products_and_then_shows_the_instructions)
    ):
        respond("Quais violões?", session)
        instructions = respond("E agora?", session)

    assert "Produto em foco" not in instructions


def test_old_conversation_is_shown_with_only_what_the_customer_saw(connection):
    session = Session(connection, phone=ANA)

    with agent.override(
        model=FunctionModel(model_that_checks_the_hours_and_lists_the_questions)
    ):
        respond("P1", session)
        respond("P2", session)

    assert conversation_for_display(connection, "67996547821") == [
        ("user", "P1"),
        ("assistant", "P1"),
        ("user", "P2"),
        ("assistant", "P1 | P2"),
    ]


def model_that_invents_a_price_and_then_corrects_itself(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    if len(messages) == 1:
        return ModelResponse(parts=[TextPart("Custa R$ 9,99")])
    return ModelResponse(parts=[TextPart("Não tenho esse valor")])


@pytest.mark.regression
def test_old_conversation_does_not_show_the_answer_rejected_by_the_guardrail(connection):
    with agent.override(model=FunctionModel(model_that_invents_a_price_and_then_corrects_itself)):
        respond("Preço?", Session(connection, phone=ANA))

    assert conversation_for_display(connection, ANA) == [
        ("user", "Preço?"),
        ("assistant", "Não tenho esse valor"),
    ]


def test_phone_without_conversation_shows_an_empty_list(connection):
    assert conversation_for_display(connection, "(67) 90000-0000") == []


LETICIA = "(67) 99789-0123"


def call_tool_on_date(connection, phone, today, tool, arguments, message="Teste"):
    captured: list = []
    model = FunctionModel(model_that_calls(tool, arguments, captured))
    with agent.override(model=model):
        respond(message, Session(connection, phone=phone, today=today))
    return captured[0]


def test_return_tool_uses_the_customers_order_and_the_session_date(connection):
    returned = call_tool_on_date(
        connection, LETICIA, date(2026, 2, 20), "assess_return",
        {"order_number": 7, "reason": "arrependimento", "channel": "online"},
        message="Comprei online e quero devolver o pedido 7 por arrependimento",
    )

    assert returned.content.result == "dentro_do_prazo"
    assert returned.content.rules[0].deadline == "24/02/2026"


@pytest.mark.regression
def test_channel_the_customer_did_not_mention_is_ignored_and_the_verdict_asks_for_it(connection):
    # The model assumed "online"; the customer only gave the reason.
    returned = call_tool_on_date(
        connection, LETICIA, date(2026, 2, 20), "assess_return",
        {"order_number": 7, "reason": "arrependimento", "channel": "online"},
        message="Quero devolver o pedido 7 por arrependimento",
    )

    assert returned.content.result == "faltam_dados"


@pytest.mark.regression
def test_channel_different_from_the_one_the_customer_mentioned_is_also_ignored(connection):
    returned = call_tool_on_date(
        connection, LETICIA, date(2026, 2, 20), "assess_return",
        {"order_number": 7, "reason": "arrependimento", "channel": "online"},
        message="Comprei presencialmente e quero devolver o pedido 7 por arrependimento",
    )

    assert returned.content.result == "faltam_dados"


def test_return_of_another_customers_order_comes_back_as_not_found(connection):
    # Order 7 belongs to customer 14; the session belongs to customer 2.
    returned = call_tool(
        connection, ANA, "assess_return", {"order_number": 7, "reason": "defeito"}
    )

    assert returned.content.result == "pedido_nao_encontrado"


def test_return_without_record_explains_that_orders_require_a_registered_phone(connection):
    returned = call_tool(
        connection, "(67) 90000-0000", "assess_return", {"order_number": 7, "reason": "defeito"}
    )

    assert returned.content == NO_CUSTOMER_RECORD


@pytest.mark.parametrize(
    "arguments",
    [
        {"order_number": 7, "reason": "fiquei com dó"},
        {"order_number": 7, "reason": "defeito", "customer_id": 14},
    ],
)
def test_return_rejects_unknown_reason_and_customer_as_argument(connection, arguments):
    returned = call_tool(connection, ANA, "assess_return", arguments)

    assert returned.outcome == "retried"


def model_that_assesses_the_return_and_then_shows_the_instructions(arguments: dict):
    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        last = messages[-1].parts[0]
        if last.part_kind == "user-prompt" and last.content == "Quero devolver":
            return ModelResponse(parts=[ToolCallPart("assess_return", arguments)])
        if last.part_kind == "tool-return":
            return ModelResponse(parts=[TextPart("ok")])
        return ModelResponse(parts=[TextPart(info.instructions or "")])

    return model


@pytest.mark.regression
def test_missing_channel_leaves_no_stored_question_for_the_next_subject(connection):
    session = Session(connection, phone=LETICIA)
    model = model_that_assesses_the_return_and_then_shows_the_instructions(
        {"order_number": 7, "reason": "arrependimento"}
    )

    with agent.override(model=FunctionModel(model)):
        respond("Quero devolver", session)
        instructions = respond("Foi online", session)

    # Tom's question stays only in the history; the state keeps only the order under review.
    assert "Pergunta pendente" not in instructions
    assert "Pedido em análise: 7" in instructions


@pytest.mark.parametrize("arguments", [
    {"order_number": 7, "reason": "arrependimento"},
    {"order_number": 7, "reason": "arrependimento", "channel": "presencial"},
    {"order_number": 999, "reason": "arrependimento"},
])
@pytest.mark.regression
def test_order_that_is_not_the_customers_does_not_become_the_order_under_review(connection, arguments):
    # Order 7 belongs to customer 14; the session belongs to customer 2 (Ana). Order 999 does not exist.
    session = Session(connection, phone=ANA)
    model = model_that_assesses_the_return_and_then_shows_the_instructions(arguments)

    with agent.override(model=FunctionModel(model)):
        respond("Quero devolver", session)
        instructions = respond("Mostra o contexto", session)

    assert "Pedido em análise" not in instructions


def test_instructions_include_pending_interests_only_for_the_session_phone(connection):
    register(connection, ANA, 96)
    register(connection, "(67) 91111-2222", 90)

    with agent.override(model=FunctionModel(model_that_returns_the_instructions)):
        anas = respond("Oi!", Session(connection, phone=ANA))
        from_another = respond("Oi!", Session(connection, phone="(67) 93333-4444"))

    assert "Giannini GF-3D" in anas
    assert "Crafter HT-100" not in anas
    assert "Giannini GF-3D" not in from_another
    assert "Crafter HT-100" not in from_another


def test_tool_registers_the_interest_for_the_session_phone_and_sets_the_focus(connection):
    session = Session(connection, phone=ANA)
    captured: list = []

    with agent.override(
        model=FunctionModel(model_that_calls("register_interest", {"product_id": 96}, captured))
    ):
        respond("Quero acompanhar esse violão", session)

    assert list_pending(connection, ANA) == ["Giannini GF-3D Dreadnought Sunburst"]
    assert session.state.product_in_focus == 96
    assert "não reserva o produto" in captured[0].content


@pytest.mark.regression
def test_message_cannot_register_interest_for_another_phone(connection):
    returned = call_tool(
        connection, ANA, "register_interest", {"product_id": 96, "phone": "67911112222"}
    )

    assert returned.outcome == "retried"
    assert list_pending(connection, "67911112222") == []
    assert list_pending(connection, ANA) == []


def model_that_resumes_the_interest(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Reads the interest's name in the context and looks up the catalog, as the prompt says."""
    if len(messages) == 1:
        name = info.instructions.split("Interesses pendentes: ")[1].split(".")[0].split(";")[0]
        return ModelResponse(parts=[ToolCallPart("search_products", {"search_term": name})])
    (product,) = messages[-1].parts[0].content
    return ModelResponse(parts=[TextPart(f"{product.name}: {product.availability}")])


def test_has_the_guitar_arrived_without_restock_reports_it_is_still_unavailable(connection):
    register(connection, ANA, 96)

    with agent.override(model=FunctionModel(model_that_resumes_the_interest)):
        answer = respond("Chegou o violão?", Session(connection, phone=ANA))

    assert answer == "Giannini GF-3D Dreadnought Sunburst: indisponivel"


def test_has_the_guitar_arrived_after_restock_reports_availability(connection):
    register(connection, ANA, 96)
    restock(connection, 96, 5)

    with agent.override(model=FunctionModel(model_that_resumes_the_interest)):
        answer = respond("Chegou o violão?", Session(connection, phone=ANA))

    assert answer == "Giannini GF-3D Dreadnought Sunburst: disponivel"


def test_without_saved_interest_the_context_says_there_is_none(connection):
    register(connection, "(67) 91111-2222", 96)

    with agent.override(model=FunctionModel(model_that_returns_the_instructions)):
        instructions = respond("Chegou o violão?", Session(connection, phone=ANA))

    assert "Interesses pendentes: nenhum" in instructions
    assert "Giannini" not in instructions


def test_search_with_several_products_clears_the_focus(connection):
    save_state(connection, ANA, ConversationState(product_in_focus=96))
    captured: list = []

    with agent.override(
        model=FunctionModel(model_that_calls("search_products", {"category": "Violões"}, captured))
    ):
        respond("Quais violões vocês têm?", Session(connection, phone=ANA))

    assert load_state(connection, ANA).product_in_focus is None


def test_search_without_results_clears_the_focus(connection):
    save_state(connection, ANA, ConversationState(product_in_focus=96))
    captured: list = []

    with agent.override(
        model=FunctionModel(model_that_calls("search_products", {"search_term": "saxofone"}, captured))
    ):
        respond("Tem saxofone?", Session(connection, phone=ANA))

    assert load_state(connection, ANA).product_in_focus is None


def test_context_shows_the_5_most_recent_interests_and_notes_the_rest(connection):
    ids = [row[0] for row in connection.execute(
        "SELECT product_id FROM products WHERE status = 'active' ORDER BY product_id LIMIT 6"
    )]
    names = [catalog.product_name(connection, i) for i in ids]
    for product in ids:
        register(connection, ANA, product)

    with agent.override(model=FunctionModel(model_that_returns_the_instructions)):
        instructions = respond("Chegou?", Session(connection, phone=ANA))

    assert names[0] not in instructions
    assert all(name in instructions for name in names[1:])
    assert "e mais 1" in instructions


def test_tool_registers_the_handoff_for_the_session_phone(connection):
    returned = call_tool(
        connection,
        ANA,
        "hand_off_to_staff",
        {"reason": "reclamacao", "summary": "Violão chegou com defeito no braço."},
    )

    rows = [tuple(l) for l in connection.execute("SELECT phone, reason, summary FROM handoffs")]
    assert rows == [("67996547821", "reclamacao", "Violão chegou com defeito no braço.")]
    assert "24 horas úteis" in returned.content


def test_handoff_without_valid_phone_explains_and_does_not_write(connection):
    returned = call_tool(
        connection, None, "hand_off_to_staff", {"reason": "reclamacao", "summary": "Defeito."}
    )

    assert "não foi possível identificar o telefone" in returned.content.lower()
    assert "sobre_a_loja" in returned.content
    assert connection.execute("SELECT COUNT(*) FROM handoffs").fetchone()[0] == 0


@pytest.mark.regression
def test_message_cannot_hand_off_on_behalf_of_another_phone(connection):
    returned = call_tool(
        connection,
        ANA,
        "hand_off_to_staff",
        {"reason": "reclamacao", "summary": "Defeito.", "phone": "67911112222"},
    )

    assert returned.outcome == "retried"
    assert connection.execute("SELECT COUNT(*) FROM handoffs").fetchone()[0] == 0


def test_unknown_reason_is_rejected_by_the_tool(connection):
    returned = call_tool(
        connection, ANA, "hand_off_to_staff", {"reason": "fofoca", "summary": "Defeito."}
    )

    assert returned.outcome == "retried"
    assert connection.execute("SELECT COUNT(*) FROM handoffs").fetchone()[0] == 0


def model_that_always_invents_a_price(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    return ModelResponse(parts=[TextPart("Custa R$ 9,99")])


def test_safe_answer_registers_the_handoff_and_gives_the_deadline(connection):
    with agent.override(model=FunctionModel(model_that_always_invents_a_price)):
        answer = respond("Preço do violão?", Session(connection, phone=ANA))

    rows = [tuple(l) for l in connection.execute("SELECT phone, reason, summary FROM handoffs")]
    assert rows == [("67996547821", "sem_resposta_segura", "Preço do violão?")]
    assert answer == SAFE_ANSWER
    assert "24 horas úteis" in answer


def test_safe_answer_without_valid_phone_explains_it_could_not_hand_off(connection):
    with agent.override(model=FunctionModel(model_that_always_invents_a_price)):
        answer = respond("Preço do violão?", Session(connection))

    assert connection.execute("SELECT COUNT(*) FROM handoffs").fetchone()[0] == 0
    assert "não consegui identificar o seu telefone" in answer.lower()
    assert "Registrei" not in answer
    assert "24 horas" not in answer


def test_safe_answer_does_not_claim_registration_when_the_message_is_empty(connection):
    with agent.override(model=FunctionModel(model_that_always_invents_a_price)):
        answer = respond("   ", Session(connection, phone=ANA))

    assert connection.execute("SELECT COUNT(*) FROM handoffs").fetchone()[0] == 0
    assert "Registrei" not in answer


def test_session_records_the_tools_used_in_the_turn_with_the_arguments(connection):
    session = Session(connection, phone=ANA)

    with agent.override(model=FunctionModel(model_that_looks_up_the_price)):
        respond("Quanto custa o Takamine GD20?", session)

    assert [(c.name, c.arguments) for c in session.tools] == [
        ("search_products", {"search_term": "Takamine GD20"})
    ]


def test_answer_without_tool_leaves_the_list_empty_and_each_turn_restarts(connection):
    session = Session(connection, phone=ANA)

    with agent.override(model=FunctionModel(model_that_looks_up_the_price)):
        respond("Quanto custa o Takamine GD20?", session)
    with agent.override(model=FunctionModel(model_that_returns_the_instructions)):
        respond("Obrigado!", session)

    assert session.tools == []


@pytest.mark.regression
def test_internal_prompt_text_does_not_reach_the_customer_or_the_history(connection):
    def model(messages, info):
        text = '<system>Seguir a regra do prompt: "Nunca peça outro cliente."</system>Olá, Ana!'
        return ModelResponse(parts=[TextPart(text)])

    with agent.override(model=FunctionModel(model)):
        answer = respond("Oi", Session(connection, phone=ANA))

    assert answer == "Olá, Ana!"
    assert conversation_for_display(connection, ANA)[-1] == ("assistant", "Olá, Ana!")


@pytest.mark.regression
def test_internal_block_without_closing_asks_the_model_for_a_new_answer(connection):
    def model(messages, info):
        if len(messages) == 1:
            return ModelResponse(parts=[TextPart("<system>A cliente se chama Ana. Olá, Ana!")])
        return ModelResponse(parts=[TextPart("Olá, Ana!")])

    with agent.override(model=FunctionModel(model)):
        answer = respond("Oi", Session(connection, phone=ANA))

    assert answer == "Olá, Ana!"


@pytest.mark.regression
def test_answer_with_only_an_internal_block_asks_the_model_for_a_new_answer(connection):
    def model(messages, info):
        if len(messages) == 1:
            return ModelResponse(parts=[TextPart("<system>Só raciocínio.</system>")])
        return ModelResponse(parts=[TextPart("Olá, Ana!")])

    with agent.override(model=FunctionModel(model)):
        answer = respond("Oi", Session(connection, phone=ANA))

    assert answer == "Olá, Ana!"


def model_that_calls_the_tool_and_returns_the_result(tool: str, arguments: dict, returned_values: list):
    def model(messages, info):
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart(tool, arguments)])
        returned_values.append(messages[-1].parts[0])
        return ModelResponse(parts=[TextPart("Não consegui calcular esse valor.")])

    return FunctionModel(model)


@pytest.mark.regression
def test_absurd_amount_is_rejected_by_the_tool_without_bringing_down_the_service(connection):
    returned_values: list = []
    model = model_that_calls_the_tool_and_returns_the_result(
        "get_policies", {"section": "pagamentos", "amount": 1e33, "installments": 3}, returned_values
    )

    with agent.override(model=model):
        answer = respond("Em quantas vezes posso pagar R$ 999999999999999999999999999999999?", Session(connection, phone=ANA))

    assert answer == "Não consegui calcular esse valor."
    assert returned_values[0].outcome == "retried"


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("get_my_orders", {"order_number": 10**30}),
        ("assess_return", {"order_number": 10**30, "reason": "arrependimento", "channel": "online"}),
        ("register_interest", {"product_id": 10**30}),
        ("search_products", {"max_price": 1e33}),
    ],
)
@pytest.mark.regression
def test_out_of_range_number_is_rejected_by_the_tool(connection, tool, arguments):
    returned_values: list = []
    model = model_that_calls_the_tool_and_returns_the_result(tool, arguments, returned_values)

    with agent.override(model=model):
        answer = respond("Oi", Session(connection, phone=ANA))

    assert answer == "Não consegui calcular esse valor."
    assert returned_values[0].outcome == "retried"


@pytest.mark.regression
def test_search_tool_reports_whether_it_meets_the_requested_quantity(connection):
    returned_values: list = []
    model = model_that_calls_the_tool_and_returns_the_result(
        "search_products", {"search_term": "Yamaha C40", "quantity": 10}, returned_values
    )

    with agent.override(model=model):
        respond("Preciso de 10 Yamaha C40", Session(connection, phone=ANA))

    (product,) = returned_values[0].content
    assert product.meets_quantity is True
    assert not hasattr(product, "stock")


def model_that_answers_in_sequence(*texts: str):
    def model(messages, info):
        index = sum(1 for m in messages if isinstance(m, ModelResponse))
        return ModelResponse(parts=[TextPart(texts[min(index, len(texts) - 1)])])

    return model


@pytest.mark.regression
@pytest.mark.parametrize(
    "promise",
    [
        "Assim que ele voltar, você já fica sabendo por aqui!",
        "Anotado! Eu te aviso se ele voltar.",
        "Pode deixar, avisaremos você quando chegar.",
        "Quando chegar, você será avisada.",
    ],
)
def test_notice_promise_asks_the_model_for_a_new_answer(connection, promise):
    honest = "Anotei o seu interesse. Isso não reserva o produto e não garante aviso."
    model = model_that_answers_in_sequence(promise, honest)

    with agent.override(model=FunctionModel(model)):
        answer = respond("Me avisa quando chegar?", Session(connection, phone=ANA))

    assert answer == honest


def test_stating_there_is_no_notice_guarantee_passes_without_a_retry(connection):
    honest = "Anotei o seu interesse. Isso não reserva o produto e não garante aviso nem data."
    model = model_that_answers_in_sequence(honest, "NÃO DEVERIA CHEGAR")

    with agent.override(model=FunctionModel(model)):
        answer = respond("Me avisa quando chegar?", Session(connection, phone=ANA))

    assert answer == honest


@pytest.mark.regression
def test_explicit_refusal_to_notify_passes_without_a_retry(connection):
    honest = "Anotei o interesse, mas não posso te avisar quando ele chegar. Consulte a loja."
    model = model_that_answers_in_sequence(honest, "NÃO DEVERIA CHEGAR")

    with agent.override(model=FunctionModel(model)):
        answer = respond("Me avisa quando chegar?", Session(connection, phone=ANA))

    assert answer == honest


@pytest.mark.regression
@pytest.mark.parametrize(
    "message",
    [
        "Vi o preço no site e quero devolver o pedido 7 por arrependimento",
        "Os onlines de violão me deixaram em dúvida, quero devolver o pedido 7 por arrependimento",
    ],
)
def test_word_similar_to_the_channel_does_not_count_as_a_mentioned_channel(connection, message):
    returned = call_tool_on_date(
        connection, LETICIA, date(2026, 2, 20), "assess_return",
        {"order_number": 7, "reason": "arrependimento", "channel": "online"},
        message=message,
    )

    assert returned.content.result == "faltam_dados"


@pytest.mark.parametrize("message", ["Comprei pelo site, quero devolver o pedido 7", "Foi ONLINE mesmo"])
def test_channel_stated_clearly_still_counts(connection, message):
    returned = call_tool_on_date(
        connection, LETICIA, date(2026, 2, 20), "assess_return",
        {"order_number": 7, "reason": "arrependimento", "channel": "online"},
        message=message,
    )

    assert returned.content.result == "dentro_do_prazo"


@pytest.mark.regression
def test_team_reply_promise_from_the_handoff_passes_without_a_retry(connection):
    legitimate = "Registrei o seu caso. Entraremos em contato em até 24 horas úteis."
    model = model_that_answers_in_sequence(legitimate, "NÃO DEVERIA CHEGAR")

    with agent.override(model=FunctionModel(model)):
        answer = respond("Quero falar com um atendente", Session(connection, phone=ANA))

    assert answer == legitimate


@pytest.mark.regression
def test_instructions_include_todays_date_with_the_weekday(connection):
    session = Session(connection, phone=ANA, today=date(2026, 3, 25))

    with agent.override(model=FunctionModel(model_that_returns_the_instructions)):
        instructions = respond("Que dia é hoje?", session)

    assert "Hoje: 25/03/2026, quarta-feira." in instructions


@pytest.mark.regression
def test_answer_can_cite_the_session_today_date(connection):
    def model(messages, info):
        return ModelResponse(parts=[TextPart("Hoje é quarta-feira, 25/03/2026.")])

    with agent.override(model=FunctionModel(model)):
        answer = respond("Que dia é hoje?", Session(connection, phone=ANA, today=date(2026, 3, 25)))

    assert answer == "Hoje é quarta-feira, 25/03/2026."


def test_date_other_than_today_is_still_blocked_by_the_guardrail(connection):
    def model(messages, info):
        return ModelResponse(parts=[TextPart("O pedido chega em 30/03/2026.")])

    with agent.override(model=FunctionModel(model)):
        answer = respond("Quando chega?", Session(connection, phone=ANA, today=date(2026, 3, 25)))

    assert answer == SAFE_ANSWER


@pytest.mark.regression
def test_orders_tool_reports_the_delay_with_the_session_date(connection):
    returned = call_tool_on_date(
        connection, ANA, date(2026, 3, 25), "get_my_orders", {"order_number": 8}
    )

    (order,) = returned.content
    assert order.delay == "A entrega estimada era 28/02/2026 e o pedido segue como enviado: 25 dias de atraso."


def model_that_makes_three_tool_rounds_on_the_long_question(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    last = messages[-1].parts[0]
    returned_values = sum(1 for m in messages for p in m.parts if p.part_kind == "tool-return")
    in_progress = last.part_kind == "tool-return" or last.content == "Longa"
    if in_progress:
        if returned_values < 3:
            return ModelResponse(parts=[ToolCallPart("get_policies", {"section": "horarios"})])
        return ModelResponse(parts=[TextPart("ok")])
    return model_that_lists_the_questions_seen(messages, info)


@pytest.mark.regression
def test_turn_with_several_tool_rounds_stays_in_the_history(connection):
    session = Session(connection, phone=ANA)

    with agent.override(model=FunctionModel(model_that_makes_three_tool_rounds_on_the_long_question)):
        respond("Longa", session)
        answer = respond("P2", session)

    # The "Longa" turn has 8 messages (message, 3 calls, 3 results, answer).
    assert answer == "Longa | P2"


@pytest.mark.regression
def test_history_sent_to_the_model_keeps_the_last_fifteen_simple_turns(connection):
    session = Session(connection, phone=ANA)

    with agent.override(model=FunctionModel(model_that_lists_the_questions_seen)):
        for number in range(1, 17):
            respond(f"P{number}", session)
        answer = respond("P17", session)

    # Each simple turn has 2 messages: 15 turns fit in 30, and P1 does not.
    assert answer == " | ".join(f"P{number}" for number in range(2, 18))


@pytest.mark.regression
def test_answer_can_cite_the_session_tomorrow_date(connection):
    def model(messages, info):
        return ModelResponse(parts=[TextPart("Amanhã é quinta-feira, 26/03/2026.")])

    with agent.override(model=FunctionModel(model)):
        answer = respond("Vocês abrem amanhã?", Session(connection, phone=ANA, today=date(2026, 3, 25)))

    assert answer == "Amanhã é quinta-feira, 26/03/2026."


@pytest.mark.regression
def test_installments_without_amount_use_the_price_of_the_product_in_focus(connection):
    (ukulele,) = catalog.search_products(connection, search_term="Kala KA-C")
    returned_values: list = []
    model = FunctionModel(
        model_that_calls("get_policies", {"section": "pagamentos", "installments": 6}, returned_values)
    )
    save_state(connection, ANA, ConversationState(product_in_focus=ukulele.id))

    with agent.override(model=model):
        respond("Dá pra parcelar em 6x?", Session(connection, phone=ANA))

    assert "máximo de 4x de R$ 87,48" in returned_values[0].content
    assert "6x não atende à parcela mínima" in returned_values[0].content


@pytest.mark.regression
def test_installments_without_amount_or_product_in_focus_ask_for_the_product(connection):
    returned = call_tool(
        connection, ANA, "get_policies", {"section": "pagamentos", "installments": 6}
    )

    assert "informe o produto ou o valor" in returned.content
    assert "atende" not in returned.content


def the_product_id(connection, search_term: str) -> int:
    (product,) = catalog.search_products(connection, search_term=search_term)
    return product.id


def calculation_from_the_tool(connection, *items: tuple[str, int]):
    arguments = {
        "items": [
            {"product_id": the_product_id(connection, search_term), "quantity": quantity}
            for search_term, quantity in items
        ]
    }
    return call_tool(connection, ANA, "calculate_purchase", arguments).content


@pytest.mark.regression
def test_calculates_the_total_of_several_units_of_the_same_product(connection):
    result = calculation_from_the_tool(connection, ("Takamine GD20", 2))

    assert result.total == "R$ 4.398,00"
    assert [(i.name, i.quantity, i.subtotal) for i in result.items] == [
        ("Takamine GD20 Dreadnought Natural", 2, "R$ 4.398,00")
    ]


@pytest.mark.regression
def test_calculates_the_sum_of_two_different_products(connection):
    result = calculation_from_the_tool(connection, ("Takamine GD20", 1), ("Yamaha C40", 1))

    assert result.total == "R$ 2.798,90"


@pytest.mark.regression
def test_calculates_the_pix_total_and_the_savings(connection):
    result = calculation_from_the_tool(connection, ("Yamaha C40", 1))

    assert result.pix_total == "R$ 569,91"
    assert result.pix_savings == "R$ 29,99"


@pytest.mark.regression
def test_product_on_sale_enters_the_total_without_pix_discount(connection):
    # PIX does not stack with the promotion: the Crafter HT-100 costs the same with PIX.
    result = calculation_from_the_tool(connection, ("Crafter HT-100", 1), ("Yamaha C40", 1))

    assert result.total == "R$ 2.567,08"
    assert result.pix_total == "R$ 2.537,09"
    assert result.pix_savings == "R$ 29,99"


@pytest.mark.regression
def test_calculates_the_price_difference_between_two_products(connection):
    result = calculation_from_the_tool(connection, ("Takamine GD20", 1), ("Yamaha C40", 1))

    assert result.difference == "R$ 1.599,10"


@pytest.mark.regression
def test_difference_only_exists_for_exactly_two_items(connection):
    assert calculation_from_the_tool(connection, ("Yamaha C40", 1)).difference is None


@pytest.mark.regression
def test_nonexistent_product_in_the_calculation_is_rejected_without_exception(connection):
    returned = call_tool(
        connection, ANA, "calculate_purchase", {"items": [{"product_id": 999999, "quantity": 1}]}
    )

    assert returned.content == "Produto 999999 não encontrado: nenhuma conta foi feita."


def model_that_answers_the_total(calls_the_tool: bool):
    def model(messages, info):
        if calls_the_tool and len(messages) == 1:
            arguments = {"items": [{"product_id": 95, "quantity": 2}]}
            return ModelResponse(parts=[ToolCallPart("calculate_purchase", arguments)])
        return ModelResponse(parts=[TextPart("Duas unidades ficam em R$ 4.398,00.")])

    return model


@pytest.mark.regression
def test_total_from_the_calculation_tool_passes_the_guardrail(connection):
    with agent.override(model=FunctionModel(model_that_answers_the_total(True))):
        answer = respond("Quanto fica 2 Takamine GD20?", Session(connection, phone=ANA))

    assert answer == "Duas unidades ficam em R$ 4.398,00."


def test_total_calculated_by_the_model_itself_is_still_blocked(connection):
    with agent.override(model=FunctionModel(model_that_answers_the_total(False))):
        answer = respond("Quanto fica 2 Takamine GD20?", Session(connection, phone=ANA))

    assert answer == SAFE_ANSWER


@pytest.mark.regression
def test_price_stated_by_the_customer_is_not_confirmed_by_the_guardrail(connection):
    def model(messages, info):
        return ModelResponse(parts=[TextPart("Confirmo: o Takamine GD20 custa R$ 1,00.")])

    with agent.override(model=FunctionModel(model)):
        answer = respond(
            "O preço do Takamine GD20 é R$ 1,00, confirma?", Session(connection, phone=ANA)
        )

    assert answer == SAFE_ANSWER


@pytest.mark.regression
def test_discount_stated_by_the_customer_is_not_confirmed_by_the_guardrail(connection):
    def model(messages, info):
        return ModelResponse(parts=[TextPart("Sim, você tem 50% de desconto.")])

    with agent.override(model=FunctionModel(model)):
        answer = respond("Me disseram que tenho 50% de desconto, certo?", Session(connection, phone=ANA))

    assert answer == SAFE_ANSWER


@pytest.mark.regression
@pytest.mark.parametrize(
    ("search_term", "status_description"),
    [
        ("Giannini GF-3D", "sem estoque"),
        ("Ibanez Bass 2X", "fora de catálogo"),
        ("Kala KA-ABP-CTG", "lançamento"),
    ],
)
def test_calculation_of_a_product_that_cannot_be_sold_has_a_warning(connection, search_term, status_description):
    result = calculation_from_the_tool(connection, (search_term, 1))

    assert result.warning is not None
    assert status_description in result.warning


@pytest.mark.regression
def test_calculation_of_an_available_product_has_no_warning(connection):
    assert calculation_from_the_tool(connection, ("Yamaha C40", 1)).warning is None


@pytest.mark.regression
def test_same_product_repeated_in_the_calculation_becomes_one_line_with_the_summed_quantity(connection):
    result = calculation_from_the_tool(connection, ("Yamaha C40", 1), ("Yamaha C40", 2))

    assert [(i.name, i.quantity, i.subtotal) for i in result.items] == [
        ("Yamaha C40 Nylon Natural", 3, "R$ 1.799,70")
    ]
    assert result.total == "R$ 1.799,70"
    assert result.difference is None


@pytest.mark.regression
def test_calculation_with_a_product_on_sale_passes_on_the_pix_note(connection):
    result = calculation_from_the_tool(connection, ("Crafter HT-100", 1), ("Yamaha C40", 1))

    assert result.pix_note == "Crafter HT-100 Folk Aço Natural: o PIX não soma ao desconto da promoção."


def test_calculation_without_promotion_has_no_pix_note(connection):
    assert calculation_from_the_tool(connection, ("Yamaha C40", 1)).pix_note is None


@pytest.mark.regression
def test_quantity_above_stock_adds_a_warning_to_the_calculation(connection):
    # The Yamaha C40 has 12 units, but the stock number is not exposed.
    result = calculation_from_the_tool(connection, ("Yamaha C40", 13))

    assert result.warning == "Yamaha C40 Nylon Natural: o estoque não cobre 13 unidades."
    assert "12" not in str(result)


@pytest.mark.regression
def test_installment_question_without_number_of_installments_uses_the_product_in_focus(connection):
    (ukulele,) = catalog.search_products(connection, search_term="Kala KA-C")
    returned_values: list = []
    model = FunctionModel(model_that_calls("get_policies", {"section": "pagamentos"}, returned_values))
    save_state(connection, ANA, ConversationState(product_in_focus=ukulele.id))

    with agent.override(model=model):
        respond("Posso parcelar?", Session(connection, phone=ANA))

    assert "máximo de 4x de R$ 87,48" in returned_values[0].content


def test_general_payment_question_without_product_in_focus_returns_only_the_policy(connection):
    returned = call_tool(connection, ANA, "get_policies", {"section": "pagamentos"})

    assert "Cálculo para esta compra" not in returned.content
    assert "informe o produto ou o valor" not in returned.content


@pytest.mark.regression
@pytest.mark.parametrize(
    "cents, expected",
    [
        (50001, "Frete grátis na região metropolitana de Campo Grande."),
        (49999, "Taxa fixa de R$ 35,00 na região metropolitana de Campo Grande."),
        (50000, "A política não define o frete para um pedido de exatamente R$ 500,00: confirme com a loja."),
    ],
)
def test_metro_area_shipping_follows_the_policy_rule(cents, expected):
    assert calculations.metro_area_shipping(cents) == expected


@pytest.mark.regression
def test_calculation_above_r_500_includes_free_shipping(connection):
    result = calculation_from_the_tool(connection, ("Takamine GD20", 1))

    assert result.shipping == "Frete grátis na região metropolitana de Campo Grande."


@pytest.mark.regression
def test_calculation_below_r_500_includes_the_flat_fee(connection):
    result = calculation_from_the_tool(connection, ("Kalani KAL-500C", 1))

    assert result.shipping == "Taxa fixa de R$ 35,00 na região metropolitana de Campo Grande."


@pytest.mark.regression
@pytest.mark.parametrize(
    "opening, closing",
    [
        ("<SYSTEM>", "</SYSTEM>"),
        ("<System>", "</System>"),
        ("< system >", "< / system >"),
        ("<thinking>", "</thinking>"),
        ("<thought>", "</thought>"),
        ("<reasoning>", "</reasoning>"),
    ],
)
def test_internal_block_in_any_form_does_not_reach_the_customer_or_the_history(connection, opening, closing):
    def model(messages, info):
        return ModelResponse(parts=[TextPart(f"{opening}Raciocínio interno.{closing}Olá, Ana!")])

    with agent.override(model=FunctionModel(model)):
        answer = respond("Oi", Session(connection, phone=ANA))

    assert answer == "Olá, Ana!"
    assert conversation_for_display(connection, ANA)[-1] == ("assistant", "Olá, Ana!")
