import pytest
from pydantic_ai import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from src.agent import RESPOSTA_SEGURA, Sessao, agente, responder
from src.guardrail import valores_nao_confirmados

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


def test_valor_em_reais_citado_pelo_proprio_cliente_nao_e_confirmado(conexao):
    # O cliente pode ditar um preço; só o retorno das ferramentas confirma dinheiro (ADR-013).
    repeticao = "Sobre os R$ 500,00 que você mencionou, vou consultar."
    resposta = perguntar(conexao, "Posso pagar R$ 500,00 à vista?", None, None, [repeticao] * 3)

    assert resposta == RESPOSTA_SEGURA


def test_data_citada_pelo_proprio_cliente_continua_permitida(conexao):
    resposta = perguntar(
        conexao,
        "Comprei em 10/03/2026, ainda posso devolver?",
        None,
        None,
        ["Sobre a compra de 10/03/2026, vou consultar."],
    )

    assert resposta == "Sobre a compra de 10/03/2026, vou consultar."


def test_resposta_sem_valores_passa_sem_ferramenta(conexao):
    resposta = perguntar(conexao, "Oi!", None, None, ["Oi! Como posso ajudar?"])

    assert resposta == "Oi! Como posso ajudar?"


@pytest.mark.regressao
def test_percentual_com_ponto_decimal_nao_se_confunde_com_um_numero_inteiro():
    # "18.5%" virava 185 ao tirar o ponto como se fosse separador de milhar.
    assert valores_nao_confirmados("São 185% de desconto.", ["Desconto de 18.5%."]) == ["185"]
    assert valores_nao_confirmados("São 18.5% de desconto.", ["Desconto de 18,5%."]) == []


@pytest.mark.regressao
@pytest.mark.parametrize(
    ("resposta", "fonte", "esperado"),
    [
        ("Custa 2.199 reais.", "Preço: R$ 2.199,00", []),
        ("Custa 2.199 reais.", "Preço: R$ 599,90", ["2199"]),
        ("Custa 2 mil reais.", "Preço: R$ 2.000,00", []),
        ("Custa 2 mil reais.", "Preço: R$ 599,90", ["2000"]),
        ("Custa 599,90 reais.", "Preço: R$ 599,90", []),
    ],
)
def test_valor_escrito_com_a_palavra_reais_tambem_e_conferido(resposta, fonte, esperado):
    assert valores_nao_confirmados(resposta, [fonte]) == esperado


@pytest.mark.regressao
@pytest.mark.parametrize(
    ("resposta", "fonte", "esperado"),
    [
        ("O prazo vai até 15 de dezembro.", "Prazo até 15/12/2026.", []),
        ("O prazo vai até 15 de dezembro.", "Prazo até 16/12/2026.", ["15/12"]),
        ("O prazo vai até 1º de março.", "Prazo até 01/03/2026.", []),
        ("O prazo vai até 15 de dezembro.", "Sem datas.", ["15/12"]),
    ],
)
def test_data_por_extenso_e_conferida_contra_as_datas_das_fontes(resposta, fonte, esperado):
    assert valores_nao_confirmados(resposta, [fonte]) == esperado


@pytest.mark.regressao
@pytest.mark.parametrize(
    ("resposta", "fonte", "esperado"),
    [
        ("Custa mil reais.", "Preço: R$ 1.000,00", []),
        ("Custa mil reais.", "Preço: R$ 599,90", ["1000"]),
        ("Custa 1,5 mil reais.", "Preço: R$ 1.500,00", []),
    ],
)
def test_mil_reais_por_extenso_tambem_e_conferido(resposta, fonte, esperado):
    assert valores_nao_confirmados(resposta, [fonte]) == esperado


@pytest.mark.regressao
@pytest.mark.parametrize(
    ("resposta", "fonte", "esperado"),
    [
        ("O prazo vai até 3 de março de 2026.", "Prazo até 03/03/2026.", []),
        ("O prazo vai até 3 de março de 2027.", "Prazo até 03/03/2026.", ["2027-03-03"]),
    ],
)
def test_data_por_extenso_com_ano_e_conferida_com_o_ano(resposta, fonte, esperado):
    assert valores_nao_confirmados(resposta, [fonte]) == esperado


POLITICA_DE_HORARIOS = "Segunda a sexta-feira: 09:00 às 18:00. Sábado: 09:00 às 13:00."


@pytest.mark.regressao
def test_horario_inventado_e_barrado():
    assert valores_nao_confirmados("Abrimos às 10h.", [POLITICA_DE_HORARIOS]) == ["10:00"]


@pytest.mark.regressao
@pytest.mark.parametrize("resposta", ["Abrimos das 9h às 18h.", "Das 09:00 às 18:00.", "Sábado fechamos às 13h."])
def test_horario_da_politica_passa_em_qualquer_formato(resposta):
    assert valores_nao_confirmados(resposta, [POLITICA_DE_HORARIOS]) == []


@pytest.mark.regressao
def test_cliente_nao_confirma_horario_da_loja():
    assert valores_nao_confirmados("Abrimos às 22h.", [POLITICA_DE_HORARIOS], ["Vocês abrem às 22h?"]) == ["22:00"]


CONTATOS_DA_LOJA = "Telefone: (67) 3341-4444. WhatsApp: (67) 3321-4500."


@pytest.mark.regressao
def test_telefone_inventado_e_barrado():
    assert valores_nao_confirmados("Ligue para (67) 3999-0000.", [CONTATOS_DA_LOJA]) == ["39990000"]


@pytest.mark.regressao
@pytest.mark.parametrize("resposta", ["WhatsApp (67) 3321-4500.", "Fale no 3321-4500.", "Ligue 67 3341-4444"])
def test_telefone_da_loja_passa_com_ou_sem_ddd(resposta):
    assert valores_nao_confirmados(resposta, [CONTATOS_DA_LOJA]) == []


@pytest.mark.regressao
def test_cliente_nao_confirma_telefone_da_loja():
    assert valores_nao_confirmados(
        "Ligue para (67) 3999-0000.", [CONTATOS_DA_LOJA], ["Liga pro (67) 3999-0000?"]
    ) == ["39990000"]


@pytest.mark.regressao
def test_resposta_pode_citar_o_telefone_da_propria_sessao(conexao):
    resposta = perguntar(conexao, "Qual número vocês têm de mim?", None, None, ["Tenho o (67) 99654-7821."])

    assert resposta == "Tenho o (67) 99654-7821."


@pytest.mark.regressao
def test_telefone_da_sessao_digitado_so_com_numeros_tambem_e_fonte(conexao):
    modelo = modelo_com_respostas(None, None, ["Tenho o (67) 99654-7821."])
    with agente.override(model=FunctionModel(modelo)):
        resposta = responder("Qual número vocês têm de mim?", Sessao(conexao, telefone="67996547821"))

    assert resposta == "Tenho o (67) 99654-7821."


@pytest.mark.regressao
def test_quantidade_de_unidades_inventada_e_barrada():
    assert valores_nao_confirmados("Temos 3 unidades.", ["Takamine GD20 disponível"]) == ["3"]


@pytest.mark.regressao
def test_quantidade_da_conta_e_aceita_como_fonte():
    assert valores_nao_confirmados("São 2 unidades.", ['{"quantidade":2,"subtotal":"R$ 4.398,00"}']) == []


@pytest.mark.regressao
def test_parcelas_da_ferramenta_passam_e_outras_sao_barradas():
    fonte = "O parcelamento sem juros tem máximo de 4x de R$ 87,48."

    assert valores_nao_confirmados("Em até 4x de R$ 87,48.", [fonte]) == []
    assert valores_nao_confirmados("Em até 6 parcelas de R$ 87,48.", [fonte]) == ["6"]


@pytest.mark.regressao
def test_cliente_confirma_a_quantidade_que_ele_mesmo_pediu():
    assert valores_nao_confirmados("Anotei 10 unidades.", [], ["Preciso de 10 unidades"]) == []


@pytest.mark.regressao
@pytest.mark.parametrize(
    "resposta",
    ["Seu pedido chega semana que vem.", "Passe na próxima semana.", "Volta ao normal no mês que vem.", "No próximo mês."],
)
def test_data_relativa_inventada_e_barrada(resposta):
    assert len(valores_nao_confirmados(resposta, ["Prazo de 1 a 3 dias úteis."])) == 1


@pytest.mark.regressao
def test_data_relativa_dita_pela_ferramenta_ou_pelo_cliente_passa():
    assert valores_nao_confirmados("Na próxima semana.", ["Chega na próxima semana."]) == []
    assert valores_nao_confirmados("Semana que vem, então.", [], ["Passo aí semana que vem"]) == []


@pytest.mark.regressao
def test_horario_errado_e_corrigido_com_o_que_a_politica_diz(conexao):
    resposta = perguntar(
        conexao,
        "A que horas vocês abrem na segunda?",
        "consultar_politicas",
        {"secao": "horarios"},
        ["Abrimos às 10h.", "De segunda a sexta, das 9h às 18h."],
    )

    assert resposta == "De segunda a sexta, das 9h às 18h."
