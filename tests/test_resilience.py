import decimal
import json
import sqlite3

import pytest
from pydantic_ai import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.exceptions import (
    ModelAPIError,
    ModelAuthenticationError,
    ModelConnectionError,
    ModelHTTPError,
    ModelOverloadedError,
    ModelQuotaExceededError,
    ModelRateLimitError,
    ModelRequestTimeout,
    ModelServerError,
    ModelTimeoutError,
    ModelUnavailableError,
)
from pydantic_ai.models.function import FunctionModel

from src.agent import (
    MENSAGEM_DE_ERRO_TECNICO,
    MENSAGEM_DE_LIMITE,
    MENSAGEM_DE_LIMITE_DIARIO,
    MENSAGEM_DE_TIMEOUT,
    ChamadaDeFerramenta,
    RESPOSTA_SEGURA_SEM_REGISTRO,
    Sessao,
    agente,
    responder,
)
from src.database import connect
from src.memory import carregar_estado, exibir_conversa

ANA = "(67) 99654-7821"


def limite_atingido(retry_after: float | None = None) -> ModelRateLimitError:
    return ModelRateLimitError("modelo", "limite de uso", retry_after=retry_after)


def modelo_que_falha_antes_de_responder(falhas: list[Exception], tentativas: list[int]):
    """Raises each error in the list, one per call, and then answers."""

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


def test_erro_de_limite_gera_nova_tentativa(connection, esperas):
    tentativas: list[int] = []
    modelo = modelo_que_falha_antes_de_responder([limite_atingido()], tentativas)

    with agente.override(model=modelo):
        resposta = responder("Oi", Sessao(connection, phone=ANA))

    assert resposta == "Resposta do Tom"
    assert len(tentativas) == 2


@pytest.mark.parametrize(
    "retry_after, expected",
    [(7, [7]), (300, [15]), (None, [2])],
)
def test_espera_o_tempo_pedido_pelo_provedor_com_teto_de_15_segundos(
    connection, esperas, retry_after, expected
):
    modelo = modelo_que_falha_antes_de_responder([limite_atingido(retry_after)], [])

    with agente.override(model=modelo):
        responder("Oi", Sessao(connection, phone=ANA))

    assert esperas == expected


def test_limite_persistente_gera_mensagem_clara_apos_3_tentativas(connection, esperas):
    tentativas: list[int] = []
    modelo = modelo_que_falha_antes_de_responder([limite_atingido() for _ in range(5)], tentativas)

    with agente.override(model=modelo):
        resposta = responder("Oi", Sessao(connection, phone=ANA))

    assert resposta == MENSAGEM_DE_LIMITE
    assert len(tentativas) == 3
    assert esperas == [2, 5]


def test_a_conversa_nao_se_perde_quando_o_limite_persiste(connection, esperas):
    modelo = modelo_que_falha_antes_de_responder([limite_atingido() for _ in range(5)], [])

    with agente.override(model=modelo):
        responder("Quanto custa o Takamine GD20?", Sessao(connection, phone=ANA))

    assert exibir_conversa(connection, ANA) == [
        ("user", "Quanto custa o Takamine GD20?"),
        ("assistant", MENSAGEM_DE_LIMITE),
    ]


@pytest.mark.parametrize(
    "error",
    [ModelTimeoutError("modelo", "sem resposta"), ModelRequestTimeout("modelo", 40)],
)
def test_chamada_sem_resposta_do_provedor_gera_mensagem_clara_sem_nova_tentativa(
    connection, esperas, error
):
    tentativas: list[int] = []
    modelo = modelo_que_falha_antes_de_responder([error], tentativas)

    with agente.override(model=modelo):
        resposta = responder("Oi", Sessao(connection, phone=ANA))

    assert resposta == MENSAGEM_DE_TIMEOUT
    assert len(tentativas) == 1
    assert exibir_conversa(connection, ANA) == [("user", "Oi"), ("assistant", MENSAGEM_DE_TIMEOUT)]


@pytest.mark.parametrize(
    "error",
    [
        ModelConnectionError("modelo", "sem rede"),
        ModelAuthenticationError("modelo", "chave inválida"),
        ModelAPIError("modelo", "erro qualquer"),
        sqlite3.OperationalError("no such table: products"),
    ],
)
def test_erro_tecnico_gera_mensagem_amigavel_sem_detalhes(connection, esperas, error):
    modelo = modelo_que_falha_antes_de_responder([error], [])

    with agente.override(model=modelo):
        resposta = responder("Oi", Sessao(connection, phone=ANA))

    assert resposta == MENSAGEM_DE_ERRO_TECNICO
    for detalhe in ("sem rede", "chave inválida", "erro qualquer", "products"):
        assert detalhe not in resposta
    assert exibir_conversa(connection, ANA)[-1] == ("assistant", MENSAGEM_DE_ERRO_TECNICO)


@pytest.mark.regression
@pytest.mark.parametrize("error", [
        ModelUnavailableError("modelo", "indisponível"),
        ModelOverloadedError("modelo", "sobrecarga"),
        ModelServerError("modelo", "erro 504"),
    ])
def test_indisponibilidade_temporaria_do_provedor_tambem_gera_nova_tentativa(connection, esperas, error):
    tentativas: list[int] = []
    modelo = modelo_que_falha_antes_de_responder([error], tentativas)

    with agente.override(model=modelo):
        resposta = responder("Oi", Sessao(connection, phone=ANA))

    assert resposta == "Resposta do Tom"
    assert len(tentativas) == 2


def test_cota_esgotada_nao_repete_e_informa_o_limite(connection, esperas):
    tentativas: list[int] = []
    modelo = modelo_que_falha_antes_de_responder([ModelQuotaExceededError("modelo", "cota")], tentativas)

    with agente.override(model=modelo):
        resposta = responder("Oi", Sessao(connection, phone=ANA))

    assert resposta == MENSAGEM_DE_LIMITE_DIARIO
    assert len(tentativas) == 1
    assert esperas == []


def test_banco_sem_tabelas_gera_mensagem_amigavel_em_vez_de_traceback(tmp_path):
    vazio = connect(tmp_path / "vazio.db")

    resposta = responder("Oi", Sessao(vazio, phone=ANA))

    assert resposta == MENSAGEM_DE_ERRO_TECNICO
    vazio.close()


def test_falha_ao_registrar_o_encaminhamento_da_resposta_segura_nao_derruba_o_atendimento(connection):
    connection.execute("DROP TABLE handoffs")

    def modelo(mensagens, info):
        return ModelResponse(parts=[TextPart("Custa R$ 9,99")])

    with agente.override(model=FunctionModel(modelo)):
        resposta = responder("Preço do violão?", Sessao(connection, phone=ANA))

    assert resposta == RESPOSTA_SEGURA_SEM_REGISTRO


def test_limite_que_persiste_e_registrado_com_o_que_o_provedor_informou(
    connection, esperas, log_de_limites_temporario
):
    corpo = {"error": {"details": [{"violations": [{"quotaValue": "20", "quotaId": "PorDia"}]}]}}
    error = ModelHTTPError.for_category(
        ModelRateLimitError, status_code=429, model_name="gemini-3.5-flash-lite", body=corpo
    )
    modelo = modelo_que_falha_antes_de_responder([error, error, error], [])

    with agente.override(model=modelo):
        responder("Oi", Sessao(connection, phone=ANA))

    eventos = [json.loads(l) for l in log_de_limites_temporario.read_text(encoding="utf-8").splitlines()]
    assert [(e["status"], e["limite"], e["cota"]) for e in eventos] == [(429, "20", "PorDia")]


def test_falha_ao_gravar_o_registro_de_limites_nao_impede_a_mensagem(connection, esperas, tmp_path, monkeypatch):
    # A directory in place of the file makes the write fail.
    monkeypatch.setattr("src.config.LIMITS_LOG_PATH", tmp_path)
    modelo = modelo_que_falha_antes_de_responder([limite_atingido() for _ in range(5)], [])

    with agente.override(model=modelo):
        resposta = responder("Oi", Sessao(connection, phone=ANA))

    assert resposta == MENSAGEM_DE_LIMITE


def test_turno_com_erro_nao_herda_as_ferramentas_do_turno_anterior(connection, esperas):
    sessao = Sessao(connection, phone=ANA)
    sessao.ferramentas = [ChamadaDeFerramenta("search_products", {"search_term": "x"})]
    modelo = modelo_que_falha_antes_de_responder([limite_atingido() for _ in range(5)], [])

    with agente.override(model=modelo):
        responder("Oi", sessao)

    assert sessao.ferramentas == []


def test_nova_tentativa_nao_herda_o_estado_da_tentativa_que_falhou(connection, esperas):
    chamadas: list[int] = []

    def modelo(mensagens, info):
        chamadas.append(1)
        if len(chamadas) == 1:
            return ModelResponse(
                parts=[ToolCallPart("search_products", {"search_term": "Takamine GD20"})]
            )
        if len(chamadas) == 2:
            raise limite_atingido()
        return ModelResponse(parts=[TextPart("Resposta do Tom")])

    with agente.override(model=FunctionModel(modelo)):
        responder("Quanto custa o Takamine GD20?", Sessao(connection, phone=ANA))

    assert carregar_estado(connection, ANA).produto_em_foco is None


@pytest.mark.regression
@pytest.mark.parametrize("error", [ValueError("data inválida"), decimal.InvalidOperation(), OverflowError("grande")])
def test_excecao_inesperada_gera_mensagem_amigavel_e_guarda_a_conversa(connection, esperas, error):
    modelo = modelo_que_falha_antes_de_responder([error], [])

    with agente.override(model=modelo):
        resposta = responder("Oi", Sessao(connection, phone=ANA))

    assert resposta == MENSAGEM_DE_ERRO_TECNICO
    assert exibir_conversa(connection, ANA)[-1] == ("assistant", MENSAGEM_DE_ERRO_TECNICO)


@pytest.mark.regression
def test_erro_de_servidor_persistente_gera_mensagem_tecnica_e_nao_a_de_limite(connection, esperas):
    tentativas: list[int] = []
    erros = [ModelServerError("modelo", "erro 504")] * 3
    modelo = modelo_que_falha_antes_de_responder(erros, tentativas)

    with agente.override(model=modelo):
        resposta = responder("Oi", Sessao(connection, phone=ANA))

    assert resposta == MENSAGEM_DE_ERRO_TECNICO
    assert len(tentativas) == 3


def limite_do_provedor(cota: str, retry_delay: str | None = None) -> ModelRateLimitError:
    """429 in the Gemini format: the quota violation and, sometimes, the RetryInfo."""
    detalhes = [{"violations": [{"quotaId": cota, "quotaValue": "15"}]}]
    if retry_delay:
        detalhes.append({"retryDelay": retry_delay})
    return ModelHTTPError.for_category(
        ModelRateLimitError,
        status_code=429,
        model_name="gemini-3.5-flash-lite",
        body={"error": {"details": detalhes}},
    )


@pytest.mark.regression
def test_limite_diario_nao_repete_e_diz_que_o_atendimento_volta_amanha(connection, esperas):
    tentativas: list[int] = []
    error = limite_do_provedor("GenerateRequestsPerDayPerProjectPerModel-FreeTier")
    modelo = modelo_que_falha_antes_de_responder([error, error, error], tentativas)

    with agente.override(model=modelo):
        resposta = responder("Oi", Sessao(connection, phone=ANA))

    assert len(tentativas) == 1
    assert esperas == []
    assert resposta == MENSAGEM_DE_LIMITE_DIARIO


@pytest.mark.regression
@pytest.mark.parametrize("retry_delay, expected", [("27s", [15]), ("7.5s", [7.5]), ("lixo", [2])])
def test_espera_usa_o_retry_delay_do_corpo_quando_retry_after_vem_vazio(
    connection, esperas, retry_delay, expected
):
    error = limite_do_provedor("GenerateRequestsPerMinutePerProjectPerModel-FreeTier", retry_delay)
    modelo = modelo_que_falha_antes_de_responder([error], [])

    with agente.override(model=modelo):
        responder("Oi", Sessao(connection, phone=ANA))

    assert esperas == expected


@pytest.mark.regression
def test_mensagem_de_limite_nao_cita_o_servico_de_ia_nem_o_fornecedor(connection, esperas):
    error = limite_do_provedor("GenerateRequestsPerMinutePerProjectPerModel-FreeTier", "20s")
    modelo = modelo_que_falha_antes_de_responder([error, error, error], [])

    with agente.override(model=modelo):
        resposta = responder("Oi", Sessao(connection, phone=ANA))

    assert resposta == "Estamos com muitos atendimentos ao mesmo tempo. Tente novamente em alguns minutos."


@pytest.mark.regression
def test_limite_diario_e_reconhecido_mesmo_quando_vem_depois_da_violacao_por_minuto(connection, esperas):
    violacoes = [
        {"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"},
        {"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"},
    ]
    error = ModelHTTPError.for_category(
        ModelRateLimitError,
        status_code=429,
        model_name="gemini-3.5-flash-lite",
        body={"error": {"details": [{"violations": violacoes}]}},
    )
    tentativas: list[int] = []
    modelo = modelo_que_falha_antes_de_responder([error, error, error], tentativas)

    with agente.override(model=modelo):
        resposta = responder("Oi", Sessao(connection, phone=ANA))

    assert len(tentativas) == 1
    assert resposta == MENSAGEM_DE_LIMITE_DIARIO


@pytest.mark.regression
def test_cota_esgotada_informa_que_o_atendimento_volta_amanha(connection, esperas):
    modelo = modelo_que_falha_antes_de_responder([ModelQuotaExceededError("modelo", "cota")], [])

    with agente.override(model=modelo):
        resposta = responder("Oi", Sessao(connection, phone=ANA))

    assert resposta == MENSAGEM_DE_LIMITE_DIARIO


@pytest.mark.regression
@pytest.mark.parametrize("error", [ValueError("dado inválido"), OSError("disco cheio")])
def test_qualquer_falha_ao_gravar_a_mensagem_tecnica_nao_impede_a_resposta(connection, esperas, monkeypatch, error):
    def gravar_com_falha(*argumentos, **nomeados):
        raise error

    monkeypatch.setattr("src.agent.memory.salvar_mensagens", gravar_com_falha)
    modelo = modelo_que_falha_antes_de_responder([ModelQuotaExceededError("modelo", "cota")], [])

    with agente.override(model=modelo):
        resposta = responder("Oi", Sessao(connection, phone=ANA))

    assert resposta == MENSAGEM_DE_LIMITE_DIARIO
