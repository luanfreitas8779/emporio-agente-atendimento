from pathlib import Path

import pytest
import streamlit as st
from pydantic_ai import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from streamlit.testing.v1 import AppTest

import src.database
from src.agent import MENSAGEM_DE_ERRO_TECNICO, agente

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


def test_resposta_de_um_telefone_nao_aparece_na_conversa_de_outro(tela, monkeypatch):
    monkeypatch.setattr("src.agent.responder", lambda mensagem, sessao: "Resposta da Ana")

    tela.session_state["pendente"] = {"pergunta": "Oi", "telefone": "(67) 99654-7821"}
    tela.sidebar.text_input[0].set_value("(67) 99789-0123").run()

    assert all(m["texto"] != "Resposta da Ana" for m in tela.session_state["mensagens"])


@pytest.mark.regressao
def test_falha_inesperada_libera_o_campo_e_mostra_a_mensagem_tecnica_sem_traceback(tela, monkeypatch):
    def responder_com_falha(mensagem, sessao):
        raise RuntimeError("falha em /caminho/interno")

    monkeypatch.setattr("src.agent.responder", responder_com_falha)

    tela.chat_input[0].set_value("Oi").run()

    assert not tela.exception
    assert tela.session_state["mensagens"][-1]["texto"] == MENSAGEM_DE_ERRO_TECNICO
    assert tela.session_state["pendente"] is None
    assert not tela.chat_input[0].disabled


@pytest.mark.regressao
def test_falha_ao_abrir_o_banco_tambem_mostra_a_mensagem_tecnica(tela, monkeypatch):
    aberturas = []
    conectar_de_verdade = src.database.conectar

    def conectar_com_falha_depois_da_verificacao_inicial(caminho):
        aberturas.append(caminho)
        if len(aberturas) == 2:
            raise OSError("disco indisponível")
        return conectar_de_verdade(caminho)

    monkeypatch.setattr("src.database.conectar", conectar_com_falha_depois_da_verificacao_inicial)
    tela.session_state["pendente"] = {"pergunta": "Oi", "telefone": ""}

    tela.run()

    assert not tela.exception
    assert tela.session_state["mensagens"][-1]["texto"] == MENSAGEM_DE_ERRO_TECNICO
    assert not tela.chat_input[0].disabled


@pytest.mark.regressao
def test_banco_sem_a_carga_de_dados_orienta_o_comando_em_vez_de_mostrar_traceback(tmp_path, monkeypatch):
    monkeypatch.setattr("src.config.CAMINHO_BANCO", tmp_path / "vazio.db")

    tela = AppTest.from_file(APP, default_timeout=30).run()

    assert not tela.exception
    assert "python -m src.load_data" in tela.error[0].value
    assert len(tela.chat_input) == 0


@pytest.mark.regressao
def test_falha_ao_abrir_o_banco_na_abertura_da_tela_orienta_sem_traceback(tmp_path, monkeypatch):
    def conectar_com_falha(caminho):
        raise OSError("sem permissão em /caminho/interno")

    monkeypatch.setattr("src.config.CAMINHO_BANCO", tmp_path / "teste.db")
    monkeypatch.setattr("src.database.conectar", conectar_com_falha)

    tela = AppTest.from_file(APP, default_timeout=30).run()

    assert not tela.exception
    assert "banco de dados" in tela.error[0].value
    assert "/caminho/interno" not in tela.error[0].value
    assert len(tela.chat_input) == 0
