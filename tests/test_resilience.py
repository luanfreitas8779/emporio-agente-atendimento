import pytest
from pydantic_ai import ModelResponse, TextPart
from pydantic_ai.exceptions import ModelRateLimitError
from pydantic_ai.models.function import FunctionModel

from src.agent import Sessao, agente, responder

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
