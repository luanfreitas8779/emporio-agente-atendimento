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
