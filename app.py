import streamlit as st

from src.agent import Sessao, responder
from src.config import CAMINHO_BANCO
from src.database import conectar


def exibir(papel: str, texto: str) -> None:
    # O Streamlit interpreta "$" como fórmula matemática, o que quebra os preços.
    st.chat_message(papel).markdown(texto.replace("$", r"\$"))


st.set_page_config(page_title="Empório da Música", page_icon="🎸")
st.title("Empório da Música")
st.caption("Sua música começa aqui.")

if "mensagens" not in st.session_state:
    st.session_state.mensagens = []

# O telefone identifica a sessão. Digitá-lo não prova identidade (ADR-009).
st.session_state.telefone = st.sidebar.text_input(
    "Seu telefone", value=st.session_state.get("telefone", ""), placeholder="(67) 99999-9999"
)
st.sidebar.caption("Informe o telefone cadastrado para consultar seus pedidos.")

for mensagem in st.session_state.mensagens:
    exibir(mensagem["papel"], mensagem["texto"])

if pergunta := st.chat_input("Escreva sua mensagem"):
    exibir("user", pergunta)
    st.session_state.mensagens.append({"papel": "user", "texto": pergunta})

    conexao = conectar(CAMINHO_BANCO)
    try:
        with st.spinner("O Tom está consultando..."):
            resposta = responder(pergunta, Sessao(conexao, st.session_state.telefone))
    finally:
        conexao.close()

    exibir("assistant", resposta)
    st.session_state.mensagens.append({"papel": "assistant", "texto": resposta})
