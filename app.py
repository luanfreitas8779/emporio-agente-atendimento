import streamlit as st

from src.agent import Sessao, responder
from src.config import CAMINHO_BANCO
from src.database import conectar
from src.memory import exibir_conversa
from src.phone import normalizar_telefone


def exibir(papel: str, texto: str) -> None:
    # O Streamlit interpreta "$" como fórmula matemática, o que quebra os preços.
    st.chat_message(papel).markdown(texto.replace("$", r"\$"))


st.set_page_config(page_title="Empório da Música", page_icon="🎸")
st.title("Empório da Música")
st.caption("Sua música começa aqui.")

if "mensagens" not in st.session_state:
    st.session_state.mensagens = []

# O telefone identifica a sessão. Digitá-lo não prova identidade (ADR-009).
# O key mantém o mesmo campo entre execuções; mudar o value a cada uma o recriava vazio.
st.sidebar.text_input("Seu telefone", key="telefone", placeholder="(67) 99999-9999")
st.sidebar.caption("Informe o telefone cadastrado para consultar seus pedidos.")

# Ao informar (ou trocar) o telefone, a tela mostra a conversa guardada para ele.
# Um telefone inválido não tem conversa guardada, então a tela recomeça vazia.
telefone_da_conversa = normalizar_telefone(st.session_state.telefone)
if st.session_state.get("conversa_de") != telefone_da_conversa:
    st.session_state.conversa_de = telefone_da_conversa
    conexao = conectar(CAMINHO_BANCO)
    try:
        st.session_state.mensagens = [
            {"papel": papel, "texto": texto}
            for papel, texto in exibir_conversa(conexao, st.session_state.telefone)
        ]
    finally:
        conexao.close()

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
