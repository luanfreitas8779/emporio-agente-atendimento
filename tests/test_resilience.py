import json
import sqlite3

import pytest
from pydantic_ai import ModelResponse, TextPart
from pydantic_ai.exceptions import (
    ModelAPIError,
    ModelAuthenticationError,
    ModelConnectionError,
    ModelHTTPError,
    ModelRateLimitError,
    ModelRequestTimeout,
    ModelOverloadedError,
    ModelQuotaExceededError,
    ModelTimeoutError,
    ModelUnavailableError,
)
from pydantic_ai.models.function import FunctionModel

from src.agent import (
    MENSAGEM_DE_ERRO_TECNICO,
    MENSAGEM_DE_LIMITE,
    MENSAGEM_DE_TIMEOUT,
    RESPOSTA_SEGURA_SEM_REGISTRO,
    Sessao,
    agente,
    responder,
)
from src.database import conectar
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


@pytest.mark.parametrize("erro", [ModelUnavailableError("modelo", "indisponível"), ModelOverloadedError("modelo", "sobrecarga")])
def test_indisponibilidade_temporaria_do_provedor_tambem_gera_nova_tentativa(conexao, esperas, erro):
    tentativas: list[int] = []
    modelo = modelo_que_falha_antes_de_responder([erro], tentativas)

    with agente.override(model=modelo):
        resposta = responder("Oi", Sessao(conexao, telefone=ANA))

    assert resposta == "Resposta do Tom"
    assert len(tentativas) == 2


def test_cota_esgotada_nao_repete_e_informa_o_limite(conexao, esperas):
    tentativas: list[int] = []
    modelo = modelo_que_falha_antes_de_responder([ModelQuotaExceededError("modelo", "cota")], tentativas)

    with agente.override(model=modelo):
        resposta = responder("Oi", Sessao(conexao, telefone=ANA))

    assert resposta == MENSAGEM_DE_LIMITE
    assert len(tentativas) == 1
    assert esperas == []


def test_banco_sem_tabelas_gera_mensagem_amigavel_em_vez_de_traceback(tmp_path):
    vazio = conectar(tmp_path / "vazio.db")

    resposta = responder("Oi", Sessao(vazio, telefone=ANA))

    assert resposta == MENSAGEM_DE_ERRO_TECNICO
    vazio.close()


def test_falha_ao_registrar_o_encaminhamento_da_resposta_segura_nao_derruba_o_atendimento(conexao):
    conexao.execute("DROP TABLE handoffs")

    def modelo(mensagens, info):
        return ModelResponse(parts=[TextPart("Custa R$ 9,99")])

    with agente.override(model=FunctionModel(modelo)):
        resposta = responder("Preço do violão?", Sessao(conexao, telefone=ANA))

    assert resposta == RESPOSTA_SEGURA_SEM_REGISTRO


def test_limite_que_persiste_e_registrado_com_o_que_o_provedor_informou(
    conexao, esperas, log_de_limites_temporario
):
    corpo = {"error": {"details": [{"violations": [{"quotaValue": "20", "quotaId": "PorDia"}]}]}}
    erro = ModelHTTPError.for_category(
        ModelRateLimitError, status_code=429, model_name="gemini-3.5-flash-lite", body=corpo
    )
    modelo = modelo_que_falha_antes_de_responder([erro, erro, erro], [])

    with agente.override(model=modelo):
        responder("Oi", Sessao(conexao, telefone=ANA))

    eventos = [json.loads(l) for l in log_de_limites_temporario.read_text(encoding="utf-8").splitlines()]
    assert [(e["status"], e["limite"], e["cota"]) for e in eventos] == [(429, "20", "PorDia")]


def test_falha_ao_gravar_o_registro_de_limites_nao_impede_a_mensagem(conexao, esperas, tmp_path, monkeypatch):
    # Um diretório no lugar do arquivo faz a gravação falhar.
    monkeypatch.setattr("src.config.CAMINHO_LOG_DE_LIMITES", tmp_path)
    modelo = modelo_que_falha_antes_de_responder([limite_atingido() for _ in range(5)], [])

    with agente.override(model=modelo):
        resposta = responder("Oi", Sessao(conexao, telefone=ANA))

    assert resposta == MENSAGEM_DE_LIMITE
