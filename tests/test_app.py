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
    # Enquanto a resposta não chega, a tela mantém a pergunta pendente e o campo bloqueado.
    durante: list = []

    def responder_observando(mensagem, sessao):
        durante.append(st.session_state.get("pendente"))
        return "Olá!"

    monkeypatch.setattr("src.agent.responder", responder_observando)

    tela.chat_input[0].set_value("Oi").run()

    assert durante == ["Oi"]
