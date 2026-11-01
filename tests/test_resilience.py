import sqlite3

import pytest
from pydantic_ai import ModelResponse, TextPart
from pydantic_ai.exceptions import (
    ModelAPIError,
    ModelAuthenticationError,
    ModelConnectionError,
    ModelRateLimitError,
    ModelRequestTimeout,
    ModelTimeoutError,
)
from pydantic_ai.models.function import FunctionModel

from src.agent import (
    MENSAGEM_DE_ERRO_TECNICO,
    MENSAGEM_DE_LIMITE,
    MENSAGEM_DE_TIMEOUT,
    Sessao,
    agente,
    responder,
)
from src.memory import exibir_conversa

ANA = "(67) 99654-7821"


def limite_atingido(retry_after: float | None = None) -> ModelRateLimitError:
    return ModelRateLimitError("modelo", "limite de uso", retry_after=retry_after)


def modelo_que_falha_antes_de_responder(falhas: list[Exception], tentativas: list[int]):
    """Levanta cada erro da lista, um por chamada, e depois responde."""

    def modelo(mensagens, info):
        tentativas.append(1)
        if falhas:
            raise falhas.pop(0)
        return ModelResponse(parts=[TextPart("Resposta do Tom")])

    return FunctionModel(modelo)


@pytest.fixture
def esperas(monkeypatch):
    registradas: list[float] = []
    monkeypatch.setattr("src.agent._aguardar", registradas.append)
    return registradas


def test_erro_de_limite_gera_nova_tentativa(conexao, esperas):
    tentativas: list[int] = []
    modelo = modelo_que_falha_antes_de_responder([limite_atingido()], tentativas)

    with agente.override(model=modelo):
        resposta = responder("Oi", Sessao(conexao, telefone=ANA))

    assert resposta == "Resposta do Tom"
    assert len(tentativas) == 2


@pytest.mark.parametrize(
    "retry_after, esperado",
    [(7, [7]), (300, [15]), (None, [2])],
)
def test_espera_o_tempo_pedido_pelo_provedor_com_teto_de_15_segundos(
    conexao, esperas, retry_after, esperado
):
    modelo = modelo_que_falha_antes_de_responder([limite_atingido(retry_after)], [])

    with agente.override(model=modelo):
        responder("Oi", Sessao(conexao, telefone=ANA))

    assert esperas == esperado


def test_limite_persistente_gera_mensagem_clara_apos_3_tentativas(conexao, esperas):
    tentativas: list[int] = []
    modelo = modelo_que_falha_antes_de_responder([limite_atingido() for _ in range(5)], tentativas)

    with agente.override(model=modelo):
        resposta = responder("Oi", Sessao(conexao, telefone=ANA))

    assert resposta == MENSAGEM_DE_LIMITE
    assert len(tentativas) == 3
    assert esperas == [2, 5]


def test_a_conversa_nao_se_perde_quando_o_limite_persiste(conexao, esperas):
    modelo = modelo_que_falha_antes_de_responder([limite_atingido() for _ in range(5)], [])

    with agente.override(model=modelo):
        responder("Quanto custa o Takamine GD20?", Sessao(conexao, telefone=ANA))

    assert exibir_conversa(conexao, ANA) == [
        ("user", "Quanto custa o Takamine GD20?"),
        ("assistant", MENSAGEM_DE_LIMITE),
    ]


@pytest.mark.parametrize(
    "erro",
    [ModelTimeoutError("modelo", "sem resposta"), ModelRequestTimeout("modelo", 40)],
)
def test_chamada_sem_resposta_do_provedor_gera_mensagem_clara_sem_nova_tentativa(
    conexao, esperas, erro
):
    tentativas: list[int] = []
    modelo = modelo_que_falha_antes_de_responder([erro], tentativas)

    with agente.override(model=modelo):
        resposta = responder("Oi", Sessao(conexao, telefone=ANA))

    assert resposta == MENSAGEM_DE_TIMEOUT
    assert len(tentativas) == 1
    assert exibir_conversa(conexao, ANA) == [("user", "Oi"), ("assistant", MENSAGEM_DE_TIMEOUT)]


@pytest.mark.parametrize(
    "erro",
    [
        ModelConnectionError("modelo", "sem rede"),
        ModelAuthenticationError("modelo", "chave inválida"),
        ModelAPIError("modelo", "erro qualquer"),
        sqlite3.OperationalError("no such table: products"),
    ],
)
def test_erro_tecnico_gera_mensagem_amigavel_sem_detalhes(conexao, esperas, erro):
    modelo = modelo_que_falha_antes_de_responder([erro], [])

    with agente.override(model=modelo):
        resposta = responder("Oi", Sessao(conexao, telefone=ANA))

    assert resposta == MENSAGEM_DE_ERRO_TECNICO
    for detalhe in ("sem rede", "chave inválida", "erro qualquer", "products"):
        assert detalhe not in resposta
    assert exibir_conversa(conexao, ANA)[-1] == ("assistant", MENSAGEM_DE_ERRO_TECNICO)
