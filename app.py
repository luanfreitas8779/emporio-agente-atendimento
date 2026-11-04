import logging
import sqlite3

import streamlit as st

from src.agent import TECHNICAL_ERROR_MESSAGE, Session, respond
from src.config import DATABASE_PATH
from src.database import connect
from src.load_data import database_loaded
from src.memory import conversation_for_display
from src.phone import normalize_phone


SAUDACAO = "Olá! Sou o Tom, do atendimento da Empório da Música. Posso ajudar com produtos, pedidos, trocas e pagamentos."


# Tool names and arguments are internal: the customer only sees what was looked up.
ROTULOS_DAS_FERRAMENTAS = {
    "search_products": "Consulta ao catálogo",
    "get_policies": "Consulta às políticas da loja",
    "calculate_purchase": "Cálculo da compra",
    "get_my_orders": "Consulta aos seus pedidos",
    "assess_return": "Avaliação de devolução",
    "register_interest": "Registro de interesse no produto",
    "hand_off_to_staff": "Encaminhamento para a equipe",
}


# Lookups that answer the same with or without a registered phone number.
FERRAMENTAS_SEM_CADASTRO = frozenset({"search_products", "get_policies", "calculate_purchase"})


def exibir(papel: str, text: str, tools: list[dict] | None = None) -> None:
    with st.chat_message(papel):
        if papel == "user":
            # What the customer types is not interpreted: headings, external images, and colors become text.
            st.text(text)
        else:
            # Streamlit interprets "$" as a math formula, which breaks the prices.
            st.markdown(text.replace("$", r"\$"))
        # The panel only exists for answers on this screen; the reloaded history does not bring it.
        if tools is not None:
            with st.expander("Como o Tom chegou a essa resposta"):
                if tools:
                    for call in tools:
                        st.caption(ROTULOS_DAS_FERRAMENTAS.get(call["name"], "Consulta interna"))
                else:
                    st.caption("Nenhuma ferramenta.")


st.set_page_config(page_title="Empório da Música", page_icon="🎸")
st.title("Empório da Música")
st.caption("Sua música começa aqui.")

# Without the data load there is no catalog or orders to look up.
try:
    _conexao = connect(DATABASE_PATH)
    try:
        _carregado = database_loaded(_conexao)
    finally:
        _conexao.close()
except (OSError, sqlite3.Error):
    logging.getLogger(__name__).exception("Could not open the database")
    st.error("Não foi possível abrir o banco de dados. Verifique o arquivo e reinicie o app.")
    st.stop()
if not _carregado:
    st.error("O banco de dados ainda não foi preparado. Execute `python -m src.load_data` e reinicie o app.")
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []

# The phone number identifies the session. Typing it does not prove identity (ADR-009).
# The key keeps the same field across runs; changing the value on each run recreated it empty.
st.sidebar.text_input("Seu telefone", key="phone", placeholder="(67) 99999-9999")
st.sidebar.caption("Informe o telefone cadastrado para consultar seus pedidos.")

# When the phone number is entered (or changed), the screen shows the conversation stored for it.
# An invalid phone number has no stored conversation, so the screen starts empty.
telefone_da_conversa = normalize_phone(st.session_state.phone)
if st.session_state.phone.strip() and telefone_da_conversa is None:
    st.sidebar.warning("Telefone inválido. Informe o DDD e o número, por exemplo (67) 99999-9999.")
if st.session_state.get("conversa_de") != telefone_da_conversa:
    # Whoever chatted before entering the phone number keeps seeing what was said (QA-15).
    sem_telefone = [] if st.session_state.get("conversa_de") else st.session_state.messages
    st.session_state.conversa_de = telefone_da_conversa
    connection = connect(DATABASE_PATH)
    try:
        st.session_state.messages = [
            {"papel": papel, "text": text}
            for papel, text in conversation_for_display(connection, st.session_state.phone)
        ] + (sem_telefone if telefone_da_conversa else [])
    finally:
        connection.close()
    # The last question asked without a phone number is answered again, now with the phone number,
    # unless the answer only used lookups that do not depend on the customer record.
    questions = [m["text"] for m in sem_telefone if m["papel"] == "user"]
    usadas = {c["name"] for m in sem_telefone[-1:] for c in m.get("tools") or []}
    if (
        telefone_da_conversa
        and questions
        and not (usadas and usadas <= FERRAMENTAS_SEM_CADASTRO)
        and st.session_state.get("pendente") is None
    ):
        st.session_state.pendente = {"question": questions[-1], "phone": st.session_state.phone}

# On mobile the sidebar starts collapsed and the phone field is hidden.
if not st.session_state.phone.strip():
    st.caption("Para consultar seus pedidos, informe o telefone cadastrado no menu lateral (ícone no canto superior esquerdo).")

# The greeting belongs only to the screen: it is not stored in the history or sent to the model.
if not st.session_state.messages:
    exibir("assistant", SAUDACAO)

for message in st.session_state.messages:
    exibir(message["papel"], message["text"], message.get("tools"))

# A new message during the answer interrupts the run and leaves the previous one unanswered.
# That is why the field is locked while there is a pending question (ADR-020). The question
# keeps the phone number of whoever sent it, which does not change if the sidebar field changes.
pendente = st.session_state.get("pendente")
if question := st.chat_input("Escreva sua mensagem", disabled=pendente is not None):
    st.session_state.messages.append({"papel": "user", "text": question})
    st.session_state.pendente = {"question": question, "phone": st.session_state.phone}
    st.rerun()

if pendente is not None:
    session = None
    try:
        try:
            session = Session(connect(DATABASE_PATH), pendente["phone"])
            with st.spinner("O Tom está digitando..."):
                answer = respond(pendente["question"], session)
        except Exception:
            # Without this the traceback would reach the customer and the field would stay locked (ADR-020).
            logging.getLogger(__name__).exception("Failed to answer on the screen")
            answer = TECHNICAL_ERROR_MESSAGE
        # If the screen's phone number changed, the answer was already stored for whoever asked and
        # must not appear in another number's conversation.
        if normalize_phone(pendente["phone"]) == st.session_state.get("conversa_de"):
            st.session_state.messages.append(
                {
                    "papel": "assistant",
                    "text": answer,
                    "tools": [
                        {"name": call.name, "arguments": call.arguments}
                        for call in (session.tools if session is not None else [])
                    ],
                }
            )
    finally:
        if session is not None:
            session.connection.close()
        st.session_state.pendente = None
    st.rerun()
