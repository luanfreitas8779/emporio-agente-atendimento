from pathlib import Path

import pytest
import streamlit as st
from pydantic_ai import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from streamlit.testing.v1 import AppTest

from src.agent import agente

APP = str(Path(__file__).parent.parent / "app.py")


@pytest.fixture
def tela(conexao, tmp_path, monkeypatch):
    monkeypatch.setattr("src.config.CAMINHO_BANCO", tmp_path / "teste.db")
    modelo = FunctionModel(lambda mensagens, info: ModelResponse(parts=[TextPart("Olá!")]))
    monkeypatch.setattr(agente, "model", modelo)
    return AppTest.from_file(APP, default_timeout=30).run()


def test_pergunta_fica_pendente_enquanto_o_tom_responde(tela, monkeypatch):
    # O campo só fica desabilitado enquanto há pergunta pendente (ADR-020). O AppTest não
    # observa o `disabled` durante a execução; isso é conferido no navegador (docs/05, seção 8).
    durante: list = []

    def responder_observando(mensagem, sessao):
        durante.append(st.session_state.get("pendente")["pergunta"])
        return "Olá!"

    monkeypatch.setattr("src.agent.responder", responder_observando)

    tela.chat_input[0].set_value("Oi").run()

    assert durante == ["Oi"]


def test_depois_da_resposta_o_campo_libera_e_a_conversa_tem_uma_resposta(tela):
    tela.chat_input[0].set_value("Oi").run()

    assert not tela.exception
    assert [m["papel"] for m in tela.session_state["mensagens"]] == ["user", "assistant"]
    assert tela.session_state["mensagens"][1]["texto"] == "Olá!"
    assert tela.session_state["pendente"] is None
    assert not tela.chat_input[0].disabled


def test_pergunta_pendente_e_respondida_com_o_telefone_de_quem_a_enviou(tela, monkeypatch):
    # Trocar o telefone durante a resposta não pode passar a pergunta para outro cliente (ADR-009).
    telefones: list = []

    def responder_observando(mensagem, sessao):
        telefones.append(sessao.telefone)
        return "Olá!"

    monkeypatch.setattr("src.agent.responder", responder_observando)

    tela.session_state["pendente"] = {"pergunta": "Oi", "telefone": "(67) 99654-7821"}
    tela.sidebar.text_input[0].set_value("(67) 99789-0123").run()

    assert telefones == ["(67) 99654-7821"]
