import pytest
from pydantic_ai import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from src.agent import RESPOSTA_SEGURA, Sessao, agente, responder

ANA = "(67) 99654-7821"


def modelo_com_respostas(ferramenta, argumentos, respostas, chamadas=None):
    """Chama a ferramenta (se houver) e depois devolve as respostas, uma por vez."""
    restantes = iter(respostas)

    def modelo(mensagens: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if chamadas is not None:
            chamadas.append(len(mensagens))
        if ferramenta and len(mensagens) == 1:
            return ModelResponse(parts=[ToolCallPart(ferramenta, argumentos)])
        return ModelResponse(parts=[TextPart(next(restantes))])

    return modelo


def perguntar(conexao, mensagem, ferramenta, argumentos, respostas, chamadas=None):
    modelo = modelo_com_respostas(ferramenta, argumentos, respostas, chamadas)
    with agente.override(model=FunctionModel(modelo)):
        return responder(mensagem, Sessao(conexao, telefone=ANA))


TAKAMINE = ("buscar_produtos", {"termo": "Takamine GD20"})


def test_resposta_com_preco_inventado_e_corrigida_pelo_modelo(conexao):
    resposta = perguntar(
        conexao,
        "Quanto custa o Takamine GD20?",
        *TAKAMINE,
        ["O Takamine custa R$ 1.000,00.", "O Takamine custa R$ 2.199,00."],
    )

    assert resposta == "O Takamine custa R$ 2.199,00."


def test_resposta_com_preco_correto_nao_pede_correcao(conexao):
    chamadas = []

    resposta = perguntar(
        conexao,
        "Quanto custa o Takamine GD20?",
        *TAKAMINE,
        ["O Takamine custa R$ 2.199,00."],
        chamadas,
    )

    assert resposta == "O Takamine custa R$ 2.199,00."
    assert len(chamadas) == 2  # a chamada da ferramenta e a resposta final


def test_preco_inventado_persistente_vira_resposta_segura(conexao):
    resposta = perguntar(
        conexao,
        "Quanto custa o Takamine GD20?",
        *TAKAMINE,
        ["Custa R$ 1.000,00.", "Custa R$ 1.000,00.", "Custa R$ 1.000,00."],
    )

    assert resposta == RESPOSTA_SEGURA
    assert "1.000" not in resposta


@pytest.mark.parametrize(
    "ferramenta, argumentos, inventado, correto",
    [
        (
            "consultar_meus_pedidos",
            {"numero_pedido": 8},
            "O rastreio é BRJL0000000BR.",
            "O rastreio é BRJL5544332BR.",
        ),
        (
            "consultar_meus_pedidos",
            {"numero_pedido": 8},
            "A entrega está prevista para 15/03/2026.",
            "A entrega está prevista para 28/02/2026.",
        ),
        (
            "buscar_produtos",
            {"termo": "Crafter HT-100"},
            "Está com 30% de desconto.",
            "Está com 18% de desconto.",
        ),
    ],
)
def test_rastreio_data_e_percentual_inventados_sao_corrigidos(
    conexao, ferramenta, argumentos, inventado, correto
):
    resposta = perguntar(conexao, "Me diga", ferramenta, argumentos, [inventado, correto])

    assert resposta == correto


def test_valor_citado_pelo_proprio_cliente_e_permitido(conexao):
    resposta = perguntar(
        conexao,
        "Posso pagar R$ 500,00 à vista?",
        None,
        None,
        ["Sobre os R$ 500,00 que você mencionou, vou consultar."],
    )

    assert resposta == "Sobre os R$ 500,00 que você mencionou, vou consultar."


def test_resposta_sem_valores_passa_sem_ferramenta(conexao):
    resposta = perguntar(conexao, "Oi!", None, None, ["Oi! Como posso ajudar?"])

    assert resposta == "Oi! Como posso ajudar?"
