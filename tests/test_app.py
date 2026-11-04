import tomllib
from pathlib import Path

import pytest
import streamlit as st
from pydantic_ai import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from streamlit.testing.v1 import AppTest

import src.database
from src.agent import TECHNICAL_ERROR_MESSAGE, ToolCall, agent

APP = str(Path(__file__).parent.parent / "app.py")


@pytest.fixture
def screen(connection, tmp_path, monkeypatch):
    monkeypatch.setattr("src.config.DATABASE_PATH", tmp_path / "teste.db")
    model = FunctionModel(lambda messages, info: ModelResponse(parts=[TextPart("Olá!")]))
    monkeypatch.setattr(agent, "model", model)
    return AppTest.from_file(APP, default_timeout=30).run()


def test_question_stays_pending_while_tom_answers(screen, monkeypatch):
    # The field is only disabled while there is a pending question (ADR-020). AppTest does not
    # observe `disabled` during the run; this is checked in the browser (docs/05, section 8).
    during: list = []

    def respond_while_observing(message, session):
        during.append(st.session_state.get("pending")["question"])
        return "Olá!"

    monkeypatch.setattr("src.agent.respond", respond_while_observing)

    screen.chat_input[0].set_value("Oi").run()

    assert during == ["Oi"]


def test_after_the_answer_the_field_is_enabled_and_the_conversation_has_one_answer(screen):
    screen.chat_input[0].set_value("Oi").run()

    assert not screen.exception
    assert [m["role"] for m in screen.session_state["messages"]] == ["user", "assistant"]
    assert screen.session_state["messages"][1]["text"] == "Olá!"
    assert screen.session_state["pending"] is None
    assert not screen.chat_input[0].disabled


def test_pending_question_is_answered_with_the_phone_of_whoever_sent_it(screen, monkeypatch):
    # Changing the phone number during the answer cannot hand the question to another customer (ADR-009).
    phones: list = []

    def respond_while_observing(message, session):
        phones.append(session.phone)
        return "Olá!"

    monkeypatch.setattr("src.agent.respond", respond_while_observing)

    screen.session_state["pending"] = {"question": "Oi", "phone": "(67) 99654-7821"}
    screen.sidebar.text_input[0].set_value("(67) 99789-0123").run()

    assert phones == ["(67) 99654-7821"]


def test_answer_for_one_phone_does_not_appear_in_another_conversation(screen, monkeypatch):
    monkeypatch.setattr("src.agent.respond", lambda message, session: "Resposta da Ana")

    screen.session_state["pending"] = {"question": "Oi", "phone": "(67) 99654-7821"}
    screen.sidebar.text_input[0].set_value("(67) 99789-0123").run()

    assert all(m["text"] != "Resposta da Ana" for m in screen.session_state["messages"])


@pytest.mark.regression
def test_unexpected_failure_enables_the_field_and_shows_the_technical_message_without_traceback(screen, monkeypatch):
    def respond_with_failure(message, session):
        raise RuntimeError("falha em /caminho/interno")

    monkeypatch.setattr("src.agent.respond", respond_with_failure)

    screen.chat_input[0].set_value("Oi").run()

    assert not screen.exception
    assert screen.session_state["messages"][-1]["text"] == TECHNICAL_ERROR_MESSAGE
    assert screen.session_state["pending"] is None
    assert not screen.chat_input[0].disabled


@pytest.mark.regression
def test_failure_to_start_the_session_also_shows_the_technical_message(screen, monkeypatch):
    # Opening the database for the session is the part that fails; the screen's initial check already passed.
    def failing_session(*arguments, **named):
        raise OSError("disco indisponível")

    monkeypatch.setattr("src.agent.Session", failing_session)
    screen.session_state["pending"] = {"question": "Oi", "phone": ""}

    screen.run()

    assert not screen.exception
    assert screen.session_state["messages"][-1]["text"] == TECHNICAL_ERROR_MESSAGE
    assert not screen.chat_input[0].disabled


@pytest.mark.regression
def test_database_without_the_data_load_shows_the_command_instead_of_a_traceback(tmp_path, monkeypatch):
    monkeypatch.setattr("src.config.DATABASE_PATH", tmp_path / "vazio.db")

    screen = AppTest.from_file(APP, default_timeout=30).run()

    assert not screen.exception
    assert "python -m src.load_data" in screen.error[0].value
    assert len(screen.chat_input) == 0


@pytest.mark.regression
def test_failure_to_open_the_database_when_the_screen_opens_guides_without_traceback(tmp_path, monkeypatch):
    def connect_with_failure(path):
        raise OSError("sem permissão em /caminho/interno")

    monkeypatch.setattr("src.config.DATABASE_PATH", tmp_path / "teste.db")
    monkeypatch.setattr("src.database.connect", connect_with_failure)

    screen = AppTest.from_file(APP, default_timeout=30).run()

    assert not screen.exception
    assert "banco de dados" in screen.error[0].value
    assert "/caminho/interno" not in screen.error[0].value
    assert len(screen.chat_input) == 0


ANA = "(67) 99654-7821"


@pytest.mark.regression
def test_entering_the_phone_after_the_first_question_keeps_the_conversation(screen):
    screen.chat_input[0].set_value("Cadê meu pedido?").run()

    screen.sidebar.text_input[0].set_value(ANA).run()

    assert [m["text"] for m in screen.session_state["messages"]][:2] == ["Cadê meu pedido?", "Olá!"]


@pytest.mark.regression
def test_entering_the_phone_answers_the_pending_question_again_with_the_new_phone(screen, monkeypatch):
    calls: list = []

    def respond_while_observing(message, session):
        calls.append((message, session.phone))
        return "Olá!"

    monkeypatch.setattr("src.agent.respond", respond_while_observing)
    screen.chat_input[0].set_value("Cadê meu pedido?").run()

    screen.sidebar.text_input[0].set_value(ANA).run()

    assert calls == [("Cadê meu pedido?", ""), ("Cadê meu pedido?", ANA)]
    assert [m["role"] for m in screen.session_state["messages"]] == ["user", "assistant", "assistant"]
    assert screen.session_state["pending"] is None


@pytest.mark.regression
def test_tom_opens_the_conversation_with_a_greeting(screen):
    assert screen.chat_message[0].markdown[0].value.startswith("Olá! Sou o Tom")


def test_greeting_disappears_when_the_conversation_has_messages(screen):
    screen.chat_input[0].set_value("Oi").run()

    texts = [m.value for c in screen.chat_message for m in c.markdown]

    assert not any(t.startswith("Olá! Sou o Tom") for t in texts)


@pytest.mark.regression
@pytest.mark.parametrize("phone", ["123", "(67) 9965", "abc"])
def test_invalid_phone_shows_a_warning_in_the_sidebar(screen, phone):
    screen.sidebar.text_input[0].set_value(phone).run()

    assert "telefone" in screen.sidebar.warning[0].value.lower()


@pytest.mark.parametrize("phone", ["", ANA])
def test_empty_or_valid_phone_shows_no_warning(screen, phone):
    screen.sidebar.text_input[0].set_value(phone).run()

    assert len(screen.sidebar.warning) == 0


@pytest.mark.regression
def test_without_phone_the_screen_shows_where_to_enter_it_in_the_side_menu(screen):
    captions = [c.value for c in screen.caption]

    assert any("menu lateral" in l for l in captions)


def test_with_valid_phone_the_side_menu_hint_disappears(screen):
    screen.sidebar.text_input[0].set_value(ANA).run()

    assert not any("menu lateral" in c.value for c in screen.caption)


@pytest.mark.regression
def test_customer_text_is_shown_literally_without_rendering_markdown(screen):
    question = "# TITULO ![x](http://exemplo.com/a.png) :red[colorido] $10"

    screen.chat_input[0].set_value(question).run()

    from_customer = [c for c in screen.chat_message if c.name == "user"][0]
    assert [t.value for t in from_customer.text] == [question]
    assert len(from_customer.markdown) == 0


@pytest.mark.regression
def test_tool_panel_shows_labels_without_internal_names_or_arguments(screen, monkeypatch):
    def respond_with_tools(message, session):
        session.tools = [
            ToolCall("search_products", {"search_term": "violão"}),
            ToolCall("get_my_orders", {"customer_id": 1}),
        ]
        return "Olá!"

    monkeypatch.setattr("src.agent.respond", respond_with_tools)

    screen.chat_input[0].set_value("Oi").run()

    panel = screen.expander[0]
    assert panel.label == "Como o Tom chegou a essa resposta"
    assert [c.value for c in panel.caption] == ["Consulta ao catálogo", "Consulta aos seus pedidos"]
    assert len(panel.code) == 0


@pytest.mark.regression
def test_streamlit_config_hides_developer_options_from_the_customer():
    # AppTest does not render the browser bar: what is checked is the configuration (docs/05, section 8).
    settings = tomllib.loads((Path(APP).parent / ".streamlit" / "config.toml").read_text(encoding="utf-8"))

    assert settings["client"]["toolbarMode"] == "viewer"


@pytest.mark.regression
def test_with_invalid_phone_only_the_warning_appears_without_the_side_menu_hint(screen):
    screen.sidebar.text_input[0].set_value("123").run()

    assert not any("menu lateral" in c.value for c in screen.caption)


@pytest.mark.regression
def test_question_already_answered_without_the_customer_record_is_not_asked_again(screen, monkeypatch):
    calls: list = []

    def respond_with_catalog(message, session):
        calls.append(session.phone)
        session.tools = [ToolCall("search_products", {"search_term": "violão"})]
        return "Custa R$ 100,00."

    monkeypatch.setattr("src.agent.respond", respond_with_catalog)
    screen.chat_input[0].set_value("Quanto custa o violão?").run()

    screen.sidebar.text_input[0].set_value(ANA).run()

    assert calls == [""]
    assert [m["role"] for m in screen.session_state["messages"]] == ["user", "assistant"]


@pytest.mark.regression
def test_question_that_depended_on_the_customer_record_is_asked_again_with_the_phone(screen, monkeypatch):
    calls: list = []

    def respond_with_orders(message, session):
        calls.append(session.phone)
        session.tools = [ToolCall("get_my_orders", {})]
        return "Telefone sem cadastro."

    monkeypatch.setattr("src.agent.respond", respond_with_orders)
    screen.chat_input[0].set_value("Cadê meu pedido?").run()

    screen.sidebar.text_input[0].set_value(ANA).run()

    assert calls == ["", ANA]
