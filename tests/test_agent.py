import asyncio

from pydantic_ai import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from src.agent import Sessao, agente, responder


def modelo_que_consulta_o_preco(
    mensagens: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    if len(mensagens) == 1:
        return ModelResponse(
            parts=[ToolCallPart("buscar_produtos", {"termo": "Takamine GD20"})]
        )
    resultado = mensagens[-1].parts[0].content
    return ModelResponse(parts=[TextPart(f"Encontrei: {resultado}")])


def test_responde_com_o_preco_vindo_do_catalogo(conexao):
    with agente.override(model=FunctionModel(modelo_que_consulta_o_preco)):
        resposta = responder("Quanto custa o Takamine GD20?", Sessao(conexao))

    assert "R$ 2.199,00" in resposta


def test_responde_com_um_loop_assincrono_em_execucao(conexao):
    async def responder_dentro_do_loop():
        return responder("Quanto custa o Takamine GD20?", Sessao(conexao))

    with agente.override(model=FunctionModel(modelo_que_consulta_o_preco)):
        resposta = asyncio.run(responder_dentro_do_loop())

    assert "R$ 2.199,00" in resposta


def modelo_que_busca_violoes_ate_1000(
    mensagens: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    if len(mensagens) == 1:
        argumentos = {
            "categoria": "Violões",
            "preco_maximo": 1000,
            "somente_disponiveis": True,
        }
        return ModelResponse(parts=[ToolCallPart("buscar_produtos", argumentos)])
    resultado = mensagens[-1].parts[0].content
    return ModelResponse(parts=[TextPart(f"{len(resultado)} opções")])


def test_agente_busca_por_categoria_e_preco_maximo(conexao):
    with agente.override(model=FunctionModel(modelo_que_busca_violoes_ate_1000)):
        resposta = responder("Violões disponíveis até R$ 1000?", Sessao(conexao))

    assert resposta == "12 opções"
