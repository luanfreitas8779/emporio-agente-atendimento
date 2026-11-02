import logging
import sqlite3

import streamlit as st

from src.agent import MENSAGEM_DE_ERRO_TECNICO, Sessao, responder
from src.config import CAMINHO_BANCO
from src.database import conectar
from src.load_data import banco_carregado
from src.memory import exibir_conversa
from src.phone import normalizar_telefone


SAUDACAO = "Olá! Sou o Tom, do atendimento da Empório da Música. Posso ajudar com produtos, pedidos, trocas e pagamentos."


# Nomes e argumentos das ferramentas são internos: o cliente vê só o que foi consultado.
ROTULOS_DAS_FERRAMENTAS = {
    "buscar_produtos": "Consulta ao catálogo",
    "consultar_politicas": "Consulta às políticas da loja",
    "calcular_compra": "Cálculo da compra",
    "consultar_meus_pedidos": "Consulta aos seus pedidos",
    "avaliar_devolucao": "Avaliação de devolução",
    "registrar_interesse": "Registro de interesse no produto",
    "encaminhar_para_atendente": "Encaminhamento para a equipe",
}


def exibir(papel: str, texto: str, ferramentas: list[dict] | None = None) -> None:
    with st.chat_message(papel):
        if papel == "user":
            # O que o cliente digita não é interpretado: título, imagem externa e cor viram texto.
            st.text(texto)
        else:
            # O Streamlit interpreta "$" como fórmula matemática, o que quebra os preços.
            st.markdown(texto.replace("$", r"\$"))
        # O painel só existe nas respostas desta tela; o histórico recarregado não o traz.
        if ferramentas is not None:
            with st.expander("Como o Tom chegou a essa resposta"):
                if ferramentas:
                    for chamada in ferramentas:
                        st.caption(ROTULOS_DAS_FERRAMENTAS.get(chamada["nome"], "Consulta interna"))
                else:
                    st.caption("Nenhuma ferramenta.")


st.set_page_config(page_title="Empório da Música", page_icon="🎸")
st.title("Empório da Música")
st.caption("Sua música começa aqui.")

# Sem a carga de dados não há catálogo nem pedidos para consultar.
try:
    _conexao = conectar(CAMINHO_BANCO)
    try:
        _carregado = banco_carregado(_conexao)
    finally:
        _conexao.close()
except (OSError, sqlite3.Error):
    logging.getLogger(__name__).exception("Não foi possível abrir o banco de dados")
    st.error("Não foi possível abrir o banco de dados. Verifique o arquivo e reinicie o app.")
    st.stop()
if not _carregado:
    st.error("O banco de dados ainda não foi preparado. Execute `python -m src.load_data` e reinicie o app.")
    st.stop()

if "mensagens" not in st.session_state:
    st.session_state.mensagens = []

# O telefone identifica a sessão. Digitá-lo não prova identidade (ADR-009).
# O key mantém o mesmo campo entre execuções; mudar o value a cada uma o recriava vazio.
st.sidebar.text_input("Seu telefone", key="telefone", placeholder="(67) 99999-9999")
st.sidebar.caption("Informe o telefone cadastrado para consultar seus pedidos.")

# Ao informar (ou trocar) o telefone, a tela mostra a conversa guardada para ele.
# Um telefone inválido não tem conversa guardada, então a tela recomeça vazia.
telefone_da_conversa = normalizar_telefone(st.session_state.telefone)
if st.session_state.telefone.strip() and telefone_da_conversa is None:
    st.sidebar.warning("Telefone inválido. Informe o DDD e o número, por exemplo (67) 99999-9999.")
if st.session_state.get("conversa_de") != telefone_da_conversa:
    # Quem conversou antes de informar o telefone continua vendo o que foi dito (QA-15).
    sem_telefone = [] if st.session_state.get("conversa_de") else st.session_state.mensagens
    st.session_state.conversa_de = telefone_da_conversa
    conexao = conectar(CAMINHO_BANCO)
    try:
        st.session_state.mensagens = [
            {"papel": papel, "texto": texto}
            for papel, texto in exibir_conversa(conexao, st.session_state.telefone)
        ] + (sem_telefone if telefone_da_conversa else [])
    finally:
        conexao.close()
    # A última pergunta feita sem telefone é respondida de novo, agora com o telefone informado.
    perguntas = [m["texto"] for m in sem_telefone if m["papel"] == "user"]
    if telefone_da_conversa and perguntas and st.session_state.get("pendente") is None:
        st.session_state.pendente = {"pergunta": perguntas[-1], "telefone": st.session_state.telefone}

# No celular a barra lateral começa recolhida e o campo de telefone fica escondido.
if telefone_da_conversa is None:
    st.caption("Para consultar seus pedidos, informe o telefone cadastrado no menu lateral (ícone no canto superior esquerdo).")

# A saudação é só da tela: não entra no histórico guardado nem na conversa enviada ao modelo.
if not st.session_state.mensagens:
    exibir("assistant", SAUDACAO)

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
