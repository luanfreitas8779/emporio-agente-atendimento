import tomllib
from pathlib import Path

import pytest
import streamlit as st
from pydantic_ai import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from streamlit.testing.v1 import AppTest

import src.database
from src.agent import MENSAGEM_DE_ERRO_TECNICO, ChamadaDeFerramenta, agente

APP = str(Path(__file__).parent.parent / "app.py")


@pytest.fixture
def tela(connection, tmp_path, monkeypatch):
    monkeypatch.setattr("src.config.DATABASE_PATH", tmp_path / "teste.db")
    modelo = FunctionModel(lambda messages, info: ModelResponse(parts=[TextPart("Olá!")]))
    monkeypatch.setattr(agente, "model", modelo)
    return AppTest.from_file(APP, default_timeout=30).run()


def test_pergunta_fica_pendente_enquanto_o_tom_responde(tela, monkeypatch):
    # The field is only disabled while there is a pending question (ADR-020). AppTest does not
    # observe `disabled` during the run; this is checked in the browser (docs/05, section 8).
    durante: list = []

    def responder_observando(message, sessao):
        durante.append(st.session_state.get("pendente")["pergunta"])
        return "Olá!"

    monkeypatch.setattr("src.agent.responder", responder_observando)

    tela.chat_input[0].set_value("Oi").run()

    assert durante == ["Oi"]


def test_depois_da_resposta_o_campo_libera_e_a_conversa_tem_uma_resposta(tela):
    tela.chat_input[0].set_value("Oi").run()

    assert not tela.exception
    assert [m["papel"] for m in tela.session_state["messages"]] == ["user", "assistant"]
    assert tela.session_state["messages"][1]["text"] == "Olá!"
    assert tela.session_state["pendente"] is None
    assert not tela.chat_input[0].disabled


def test_pergunta_pendente_e_respondida_com_o_telefone_de_quem_a_enviou(tela, monkeypatch):
    # Changing the phone number during the answer cannot hand the question to another customer (ADR-009).
    phones: list = []

    def responder_observando(message, sessao):
        phones.append(sessao.phone)
        return "Olá!"

    monkeypatch.setattr("src.agent.responder", responder_observando)

    tela.session_state["pendente"] = {"pergunta": "Oi", "phone": "(67) 99654-7821"}
    tela.sidebar.text_input[0].set_value("(67) 99789-0123").run()

    assert phones == ["(67) 99654-7821"]


def test_resposta_de_um_telefone_nao_aparece_na_conversa_de_outro(tela, monkeypatch):
    monkeypatch.setattr("src.agent.responder", lambda message, sessao: "Resposta da Ana")

    tela.session_state["pendente"] = {"pergunta": "Oi", "phone": "(67) 99654-7821"}
    tela.sidebar.text_input[0].set_value("(67) 99789-0123").run()

    assert all(m["text"] != "Resposta da Ana" for m in tela.session_state["messages"])


@pytest.mark.regression
def test_falha_inesperada_libera_o_campo_e_mostra_a_mensagem_tecnica_sem_traceback(tela, monkeypatch):
    def responder_com_falha(message, sessao):
        raise RuntimeError("falha em /caminho/interno")

    monkeypatch.setattr("src.agent.responder", responder_com_falha)

    tela.chat_input[0].set_value("Oi").run()

    assert not tela.exception
    assert tela.session_state["messages"][-1]["text"] == MENSAGEM_DE_ERRO_TECNICO
    assert tela.session_state["pendente"] is None
    assert not tela.chat_input[0].disabled


@pytest.mark.regression
def test_falha_ao_iniciar_a_sessao_tambem_mostra_a_mensagem_tecnica(tela, monkeypatch):
    # Opening the database for the session is the part that fails; the screen's initial check already passed.
    def sessao_com_falha(*arguments, **nomeados):
        raise OSError("disco indisponível")

    monkeypatch.setattr("src.agent.Sessao", sessao_com_falha)
    tela.session_state["pendente"] = {"pergunta": "Oi", "phone": ""}

    tela.run()

    assert not tela.exception
    assert tela.session_state["messages"][-1]["text"] == MENSAGEM_DE_ERRO_TECNICO
    assert not tela.chat_input[0].disabled


@pytest.mark.regression
def test_banco_sem_a_carga_de_dados_orienta_o_comando_em_vez_de_mostrar_traceback(tmp_path, monkeypatch):
    monkeypatch.setattr("src.config.DATABASE_PATH", tmp_path / "vazio.db")

    tela = AppTest.from_file(APP, default_timeout=30).run()

    assert not tela.exception
    assert "python -m src.load_data" in tela.error[0].value
    assert len(tela.chat_input) == 0


@pytest.mark.regression
def test_falha_ao_abrir_o_banco_na_abertura_da_tela_orienta_sem_traceback(tmp_path, monkeypatch):
    def conectar_com_falha(path):
        raise OSError("sem permissão em /caminho/interno")

    monkeypatch.setattr("src.config.DATABASE_PATH", tmp_path / "teste.db")
    monkeypatch.setattr("src.database.connect", conectar_com_falha)

    tela = AppTest.from_file(APP, default_timeout=30).run()

    assert not tela.exception
    assert "banco de dados" in tela.error[0].value
    assert "/caminho/interno" not in tela.error[0].value
    assert len(tela.chat_input) == 0


ANA = "(67) 99654-7821"


@pytest.mark.regression
def test_informar_o_telefone_depois_da_primeira_pergunta_preserva_a_conversa(tela):
    tela.chat_input[0].set_value("Cadê meu pedido?").run()

    tela.sidebar.text_input[0].set_value(ANA).run()

    assert [m["text"] for m in tela.session_state["messages"]][:2] == ["Cadê meu pedido?", "Olá!"]


@pytest.mark.regression
def test_informar_o_telefone_responde_de_novo_a_pergunta_pendente_com_o_telefone_novo(tela, monkeypatch):
    chamadas: list = []

    def responder_observando(message, sessao):
        chamadas.append((message, sessao.phone))
        return "Olá!"

    monkeypatch.setattr("src.agent.responder", responder_observando)
    tela.chat_input[0].set_value("Cadê meu pedido?").run()

    tela.sidebar.text_input[0].set_value(ANA).run()

    assert chamadas == [("Cadê meu pedido?", ""), ("Cadê meu pedido?", ANA)]
    assert [m["papel"] for m in tela.session_state["messages"]] == ["user", "assistant", "assistant"]
    assert tela.session_state["pendente"] is None


@pytest.mark.regression
def test_tom_abre_a_conversa_com_uma_saudacao(tela):
    assert tela.chat_message[0].markdown[0].value.startswith("Olá! Sou o Tom")


def test_saudacao_some_quando_a_conversa_ja_tem_mensagens(tela):
    tela.chat_input[0].set_value("Oi").run()

    texts = [m.value for c in tela.chat_message for m in c.markdown]

    assert not any(t.startswith("Olá! Sou o Tom") for t in texts)


@pytest.mark.regression
@pytest.mark.parametrize("phone", ["123", "(67) 9965", "abc"])
def test_telefone_invalido_gera_aviso_na_barra_lateral(tela, phone):
    tela.sidebar.text_input[0].set_value(phone).run()

    assert "telefone" in tela.sidebar.warning[0].value.lower()


@pytest.mark.parametrize("phone", ["", ANA])
def test_telefone_vazio_ou_valido_nao_gera_aviso(tela, phone):
    tela.sidebar.text_input[0].set_value(phone).run()

    assert len(tela.sidebar.warning) == 0


@pytest.mark.regression
def test_sem_telefone_a_tela_indica_onde_informar_no_menu_lateral(tela):
    legendas = [c.value for c in tela.caption]

    assert any("menu lateral" in l for l in legendas)


def test_com_telefone_valido_a_indicacao_do_menu_lateral_some(tela):
    tela.sidebar.text_input[0].set_value(ANA).run()

    assert not any("menu lateral" in c.value for c in tela.caption)


@pytest.mark.regression
def test_texto_do_cliente_e_exibido_literal_sem_interpretar_markdown(tela):
    pergunta = "# TITULO ![x](http://exemplo.com/a.png) :red[colorido] $10"

    tela.chat_input[0].set_value(pergunta).run()

    do_cliente = [c for c in tela.chat_message if c.name == "user"][0]
    assert [t.value for t in do_cliente.text] == [pergunta]
    assert len(do_cliente.markdown) == 0


@pytest.mark.regression
def test_painel_de_ferramentas_mostra_rotulos_sem_nomes_internos_nem_argumentos(tela, monkeypatch):
    def responder_com_ferramentas(message, sessao):
        sessao.ferramentas = [
            ChamadaDeFerramenta("search_products", {"search_term": "violão"}),
            ChamadaDeFerramenta("consultar_meus_pedidos", {"customer_id": 1}),
        ]
        return "Olá!"

    monkeypatch.setattr("src.agent.responder", responder_com_ferramentas)

    tela.chat_input[0].set_value("Oi").run()

    painel = tela.expander[0]
    assert painel.label == "Como o Tom chegou a essa resposta"
    assert [c.value for c in painel.caption] == ["Consulta ao catálogo", "Consulta aos seus pedidos"]
    assert len(painel.code) == 0


@pytest.mark.regression
def test_configuracao_do_streamlit_esconde_as_opcoes_de_desenvolvedor_do_cliente():
    # AppTest does not render the browser bar: what is checked is the configuration (docs/05, section 8).
    configuracao = tomllib.loads((Path(APP).parent / ".streamlit" / "config.toml").read_text(encoding="utf-8"))

    assert configuracao["client"]["toolbarMode"] == "viewer"


@pytest.mark.regression
def test_com_telefone_invalido_so_o_aviso_aparece_sem_a_dica_do_menu_lateral(tela):
    tela.sidebar.text_input[0].set_value("123").run()

    assert not any("menu lateral" in c.value for c in tela.caption)


@pytest.mark.regression
def test_pergunta_ja_respondida_sem_depender_do_cadastro_nao_e_refeita(tela, monkeypatch):
    chamadas: list = []

    def responder_com_catalogo(message, sessao):
        chamadas.append(sessao.phone)
        sessao.ferramentas = [ChamadaDeFerramenta("search_products", {"search_term": "violão"})]
        return "Custa R$ 100,00."

    monkeypatch.setattr("src.agent.responder", responder_com_catalogo)
    tela.chat_input[0].set_value("Quanto custa o violão?").run()

    tela.sidebar.text_input[0].set_value(ANA).run()

    assert chamadas == [""]
    assert [m["papel"] for m in tela.session_state["messages"]] == ["user", "assistant"]


@pytest.mark.regression
def test_pergunta_que_dependia_do_cadastro_e_refeita_com_o_telefone(tela, monkeypatch):
    chamadas: list = []

    def responder_com_pedidos(message, sessao):
        chamadas.append(sessao.phone)
        sessao.ferramentas = [ChamadaDeFerramenta("consultar_meus_pedidos", {})]
        return "Telefone sem cadastro."

    monkeypatch.setattr("src.agent.responder", responder_com_pedidos)
    tela.chat_input[0].set_value("Cadê meu pedido?").run()

    tela.sidebar.text_input[0].set_value(ANA).run()

    assert chamadas == ["", ANA]
