import logging

import streamlit as st

from src.agent import MENSAGEM_DE_ERRO_TECNICO, Sessao, responder
from src.config import CAMINHO_BANCO
from src.database import conectar
from src.memory import exibir_conversa
from src.phone import normalizar_telefone


def exibir(papel: str, texto: str, ferramentas: list[dict] | None = None) -> None:
    with st.chat_message(papel):
        # O Streamlit interpreta "$" como fórmula matemática, o que quebra os preços.
        st.markdown(texto.replace("$", r"\$"))
        # O painel só existe nas respostas desta tela; o histórico recarregado não o traz.
        if ferramentas is not None:
            with st.expander("Ferramentas usadas"):
                if ferramentas:
                    for chamada in ferramentas:
                        st.code(f"{chamada['nome']}({chamada['argumentos']})", language="python")
                else:
                    st.caption("Nenhuma ferramenta.")


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
    exibir(mensagem["papel"], mensagem["texto"], mensagem.get("ferramentas"))

# Uma nova mensagem durante a resposta interrompe a execução e deixa a anterior sem resposta.
# Por isso o campo fica bloqueado enquanto há uma pergunta pendente (ADR-020). A pergunta
# guarda o telefone de quem a enviou, que não muda se o campo da barra lateral for alterado.
pendente = st.session_state.get("pendente")
if pergunta := st.chat_input("Escreva sua mensagem", disabled=pendente is not None):
    st.session_state.mensagens.append({"papel": "user", "texto": pergunta})
    st.session_state.pendente = {"pergunta": pergunta, "telefone": st.session_state.telefone}
    st.rerun()

if pendente is not None:
    sessao = None
    try:
        try:
            sessao = Sessao(conectar(CAMINHO_BANCO), pendente["telefone"])
            with st.spinner("O Tom está digitando..."):
                resposta = responder(pendente["pergunta"], sessao)
        except Exception:
            # Sem isto o traceback apareceria ao cliente e o campo ficaria bloqueado (ADR-020).
            logging.getLogger(__name__).exception("Falha ao responder na tela")
            resposta = MENSAGEM_DE_ERRO_TECNICO
        # Se o telefone da tela mudou, a resposta já foi guardada para quem perguntou e
        # não deve aparecer na conversa de outro número.
        if normalizar_telefone(pendente["telefone"]) == st.session_state.get("conversa_de"):
            st.session_state.mensagens.append(
                {
                    "papel": "assistant",
                    "texto": resposta,
                    "ferramentas": [
                        {"nome": chamada.nome, "argumentos": chamada.argumentos}
                        for chamada in (sessao.ferramentas if sessao is not None else [])
                    ],
                }
            )
    finally:
        if sessao is not None:
            sessao.conexao.close()
        st.session_state.pendente = None
    st.rerun()
