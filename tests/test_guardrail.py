from decimal import Decimal

import pytest
from pydantic_ai import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from src.agent import RESPOSTA_SEGURA, Sessao, agente, responder
from src.config import DATA_DIR
from src.guardrail import promete_aviso, valores_nao_confirmados

ANA = "(67) 99654-7821"


def modelo_com_respostas(ferramenta, argumentos, respostas, chamadas=None):
    """Calls the tool (if any) and then returns the answers, one at a time."""
    restantes = iter(respostas)

    def modelo(mensagens: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if chamadas is not None:
            chamadas.append(len(mensagens))
        if ferramenta and len(mensagens) == 1:
            return ModelResponse(parts=[ToolCallPart(ferramenta, argumentos)])
        return ModelResponse(parts=[TextPart(next(restantes))])

    return modelo


def perguntar(connection, mensagem, ferramenta, argumentos, respostas, chamadas=None):
    modelo = modelo_com_respostas(ferramenta, argumentos, respostas, chamadas)
    with agente.override(model=FunctionModel(modelo)):
        return responder(mensagem, Sessao(connection, phone=ANA))


TAKAMINE = ("buscar_produtos", {"termo": "Takamine GD20"})


def test_resposta_com_preco_inventado_e_corrigida_pelo_modelo(connection):
    resposta = perguntar(
        connection,
        "Quanto custa o Takamine GD20?",
        *TAKAMINE,
        ["O Takamine custa R$ 1.000,00.", "O Takamine custa R$ 2.199,00."],
    )

    assert resposta == "O Takamine custa R$ 2.199,00."


def test_resposta_com_preco_correto_nao_pede_correcao(connection):
    chamadas = []

    resposta = perguntar(
        connection,
        "Quanto custa o Takamine GD20?",
        *TAKAMINE,
        ["O Takamine custa R$ 2.199,00."],
        chamadas,
    )

    assert resposta == "O Takamine custa R$ 2.199,00."
    assert len(chamadas) == 2  # the tool call and the final answer


def test_preco_inventado_persistente_vira_resposta_segura(connection):
    resposta = perguntar(
        connection,
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
    connection, ferramenta, argumentos, inventado, correto
):
    resposta = perguntar(connection, "Me diga", ferramenta, argumentos, [inventado, correto])

    assert resposta == correto


def test_valor_em_reais_citado_pelo_proprio_cliente_nao_e_confirmado(connection):
    # The customer may state a price; only the tool results confirm money (ADR-013).
    repeticao = "Sobre os R$ 500,00 que você mencionou, vou consultar."
    resposta = perguntar(connection, "Posso pagar R$ 500,00 à vista?", None, None, [repeticao] * 3)

    assert resposta == RESPOSTA_SEGURA


def test_data_citada_pelo_proprio_cliente_continua_permitida(connection):
    resposta = perguntar(
        connection,
        "Comprei em 10/03/2026, ainda posso devolver?",
        None,
        None,
        ["Sobre a compra de 10/03/2026, vou consultar."],
    )

    assert resposta == "Sobre a compra de 10/03/2026, vou consultar."


def test_resposta_sem_valores_passa_sem_ferramenta(connection):
    resposta = perguntar(connection, "Oi!", None, None, ["Oi! Como posso ajudar?"])

    assert resposta == "Oi! Como posso ajudar?"


@pytest.mark.regression
def test_percentual_com_ponto_decimal_nao_se_confunde_com_um_numero_inteiro():
    # "18.5%" became 185 when the period was removed as if it were a thousands separator.
    assert valores_nao_confirmados("São 185% de desconto.", ["Desconto de 18.5%."]) == ["185"]
    assert valores_nao_confirmados("São 18.5% de desconto.", ["Desconto de 18,5%."]) == []


@pytest.mark.regression
@pytest.mark.parametrize(
    ("resposta", "fonte", "expected"),
    [
        ("Custa 2.199 reais.", "Preço: R$ 2.199,00", []),
        ("Custa 2.199 reais.", "Preço: R$ 599,90", ["2199"]),
        ("Custa 2 mil reais.", "Preço: R$ 2.000,00", []),
        ("Custa 2 mil reais.", "Preço: R$ 599,90", ["2000"]),
        ("Custa 599,90 reais.", "Preço: R$ 599,90", []),
    ],
)
def test_valor_escrito_com_a_palavra_reais_tambem_e_conferido(resposta, fonte, expected):
    assert valores_nao_confirmados(resposta, [fonte]) == expected


@pytest.mark.regression
@pytest.mark.parametrize(
    ("resposta", "fonte", "expected"),
    [
        ("O prazo vai até 15 de dezembro.", "Prazo até 15/12/2026.", []),
        ("O prazo vai até 15 de dezembro.", "Prazo até 16/12/2026.", ["15/12"]),
        ("O prazo vai até 1º de março.", "Prazo até 01/03/2026.", []),
        ("O prazo vai até 15 de dezembro.", "Sem datas.", ["15/12"]),
    ],
)
def test_data_por_extenso_e_conferida_contra_as_datas_das_fontes(resposta, fonte, expected):
    assert valores_nao_confirmados(resposta, [fonte]) == expected


@pytest.mark.regression
@pytest.mark.parametrize(
    ("resposta", "fonte", "expected"),
    [
        ("Custa mil reais.", "Preço: R$ 1.000,00", []),
        ("Custa mil reais.", "Preço: R$ 599,90", ["1000"]),
        ("Custa 1,5 mil reais.", "Preço: R$ 1.500,00", []),
    ],
)
def test_mil_reais_por_extenso_tambem_e_conferido(resposta, fonte, expected):
    assert valores_nao_confirmados(resposta, [fonte]) == expected


@pytest.mark.regression
@pytest.mark.parametrize(
    ("resposta", "fonte", "expected"),
    [
        ("O prazo vai até 3 de março de 2026.", "Prazo até 03/03/2026.", []),
        ("O prazo vai até 3 de março de 2027.", "Prazo até 03/03/2026.", ["2027-03-03"]),
    ],
)
def test_data_por_extenso_com_ano_e_conferida_com_o_ano(resposta, fonte, expected):
    assert valores_nao_confirmados(resposta, [fonte]) == expected


POLITICA_DE_HORARIOS = "Segunda a sexta-feira: 09:00 às 18:00. Sábado: 09:00 às 13:00."


@pytest.mark.regression
def test_horario_inventado_e_barrado():
    assert valores_nao_confirmados("Abrimos às 10h.", [POLITICA_DE_HORARIOS]) == ["10:00"]


@pytest.mark.regression
@pytest.mark.parametrize("resposta", ["Abrimos das 9h às 18h.", "Das 09:00 às 18:00.", "Sábado fechamos às 13h."])
def test_horario_da_politica_passa_em_qualquer_formato(resposta):
    assert valores_nao_confirmados(resposta, [POLITICA_DE_HORARIOS]) == []


@pytest.mark.regression
def test_cliente_nao_confirma_horario_da_loja():
    assert valores_nao_confirmados("Abrimos às 22h.", [POLITICA_DE_HORARIOS], ["Vocês abrem às 22h?"]) == ["22:00"]


CONTATOS_DA_LOJA = "Telefone: (67) 3341-4444. WhatsApp: (67) 3321-4500."


@pytest.mark.regression
def test_telefone_inventado_e_barrado():
    assert valores_nao_confirmados("Ligue para (67) 3999-0000.", [CONTATOS_DA_LOJA]) == ["39990000"]


@pytest.mark.regression
@pytest.mark.parametrize("resposta", ["WhatsApp (67) 3321-4500.", "Fale no 3321-4500.", "Ligue 67 3341-4444"])
def test_telefone_da_loja_passa_com_ou_sem_ddd(resposta):
    assert valores_nao_confirmados(resposta, [CONTATOS_DA_LOJA]) == []


@pytest.mark.regression
def test_cliente_nao_confirma_telefone_da_loja():
    assert valores_nao_confirmados(
        "Ligue para (67) 3999-0000.", [CONTATOS_DA_LOJA], ["Liga pro (67) 3999-0000?"]
    ) == ["39990000"]


@pytest.mark.regression
def test_resposta_pode_citar_o_telefone_da_propria_sessao(connection):
    resposta = perguntar(connection, "Qual número vocês têm de mim?", None, None, ["Tenho o (67) 99654-7821."])

    assert resposta == "Tenho o (67) 99654-7821."


@pytest.mark.regression
def test_telefone_da_sessao_digitado_so_com_numeros_tambem_e_fonte(connection):
    modelo = modelo_com_respostas(None, None, ["Tenho o (67) 99654-7821."])
    with agente.override(model=FunctionModel(modelo)):
        resposta = responder("Qual número vocês têm de mim?", Sessao(connection, phone="67996547821"))

    assert resposta == "Tenho o (67) 99654-7821."


@pytest.mark.regression
def test_quantidade_de_unidades_inventada_e_barrada():
    assert valores_nao_confirmados("Temos 3 unidades.", ["Takamine GD20 disponível"]) == ["3"]


@pytest.mark.regression
def test_quantidade_da_conta_e_aceita_como_fonte():
    assert valores_nao_confirmados("São 2 unidades.", ['{"quantidade":2,"subtotal":"R$ 4.398,00"}']) == []


@pytest.mark.regression
def test_parcelas_da_ferramenta_passam_e_outras_sao_barradas():
    fonte = "O parcelamento sem juros tem máximo de 4x de R$ 87,48."

    assert valores_nao_confirmados("Em até 4x de R$ 87,48.", [fonte]) == []
    assert valores_nao_confirmados("Em até 6 parcelas de R$ 87,48.", [fonte]) == ["6"]


@pytest.mark.regression
def test_cliente_confirma_a_quantidade_que_ele_mesmo_pediu():
    assert valores_nao_confirmados("Anotei 10 unidades.", [], ["Preciso de 10 unidades"]) == []


@pytest.mark.regression
@pytest.mark.parametrize(
    "resposta",
    ["Seu pedido chega semana que vem.", "Passe na próxima semana.", "Volta ao normal no mês que vem.", "No próximo mês."],
)
def test_data_relativa_inventada_e_barrada(resposta):
    assert len(valores_nao_confirmados(resposta, ["Prazo de 1 a 3 dias úteis."])) == 1


@pytest.mark.regression
def test_data_relativa_dita_pela_ferramenta_ou_pelo_cliente_passa():
    assert valores_nao_confirmados("Na próxima semana.", ["Chega na próxima semana."]) == []
    assert valores_nao_confirmados("Semana que vem, então.", [], ["Passo aí semana que vem"]) == []


@pytest.mark.regression
def test_horario_errado_e_corrigido_com_o_que_a_politica_diz(connection):
    resposta = perguntar(
        connection,
        "A que horas vocês abrem na segunda?",
        "get_policies",
        {"section": "horarios"},
        ["Abrimos às 10h.", "De segunda a sexta, das 9h às 18h."],
    )

    assert resposta == "De segunda a sexta, das 9h às 18h."


@pytest.mark.regression
@pytest.mark.parametrize(
    "resposta",
    [
        "Atendemos de segunda a sexta, das 9h às 18h, e aos sábados, das 9h às 13h.",
        "Pode ligar para (67) 3341-4444 ou chamar no WhatsApp 3321-4500.",
        "Parcelamos sem juros em até 12x, e a entrega local leva de 1 a 3 dias úteis.",
        "Frete grátis acima de R$ 500,00; abaixo disso, taxa fixa de R$ 35,00.",
    ],
)
def test_frases_naturais_sobre_a_politica_real_nao_geram_falso_positivo(resposta):
    # Formats different from the file's (9h x 09:00, phone without area code) against data/politicas.md.
    politica = (DATA_DIR / "politicas.md").read_text(encoding="utf-8")

    assert valores_nao_confirmados(resposta, [politica]) == []


@pytest.mark.regression
def test_percentual_por_extenso_e_conferido():
    assert valores_nao_confirmados("São 50 por cento de desconto.", ["O PIX tem 5% de desconto."]) != []
    assert valores_nao_confirmados("São 5 por cento de desconto.", ["O PIX tem 5% de desconto."]) == []


@pytest.mark.regression
@pytest.mark.parametrize(
    "resposta",
    ["Dá para parcelar em 6 vezes.", "Fica em 6 x de R$ 87,48.", "Restam 3 no estoque.", "Temos apenas 3 em estoque."],
)
def test_quantidade_em_outros_formatos_e_barrada(resposta):
    assert valores_nao_confirmados(resposta, ["O máximo é de 4x de R$ 87,48."]) == ["3" if "3" in resposta else "6"]


@pytest.mark.regression
def test_quantidade_em_outros_formatos_passa_quando_vem_da_fonte():
    assert valores_nao_confirmados("Em 4 vezes.", ["O máximo é de 4x de R$ 87,48."]) == []


@pytest.mark.regression
def test_data_curta_sem_ano_e_conferida_contra_as_datas_das_fontes():
    fonte = "Previsão de entrega: 2026-12-15."

    assert valores_nao_confirmados("Chega em 15/12.", [fonte]) == []
    assert valores_nao_confirmados("Chega em 20/12.", [fonte]) == ["20/12"]
    # The full date is still checked as a date, not as "day/month".
    assert valores_nao_confirmados("Chega em 15/12/2026.", [fonte]) == []


@pytest.mark.regression
def test_horas_escritas_por_extenso_sao_conferidas_como_horario():
    assert valores_nao_confirmados("Abrimos às 7 horas.", [POLITICA_DE_HORARIOS]) == ["07:00"]
    assert valores_nao_confirmados("Abrimos às 9 horas.", [POLITICA_DE_HORARIOS]) == []


@pytest.mark.regression
@pytest.mark.parametrize(
    "resposta",
    [
        "Te mando mensagem quando chegar.",
        "Te notifico assim que chegar.",
        "Vamos te informar assim que chegar.",
        "Você receberá um aviso quando chegar.",
        "Avisarei quando chegar.",
        "Não se preocupe, te aviso.",
    ],
)
def test_outras_formas_de_prometer_aviso_sao_barradas(resposta):
    assert promete_aviso(resposta)


@pytest.mark.regression
@pytest.mark.parametrize(
    "resposta",
    [
        "Posso anotar seu interesse para avisar se ele voltar?",
        "Anote seu interesse para avisar se ele voltar?",
        "Registro o interesse para avisar quando ele estiver disponível.",
    ],
)
def test_interesse_para_avisar_e_promessa_de_aviso(resposta):
    assert promete_aviso(resposta)


@pytest.mark.regression
@pytest.mark.parametrize(
    "resposta",
    [
        "Não posso te avisar quando chegar.",
        "Sem te avisar, só anotamos o interesse.",
        "Isso não garante aviso quando ele voltar.",
        "O interesse não serve para avisar ninguém.",
    ],
)
def test_negar_a_promessa_de_aviso_continua_passando(resposta):
    assert not promete_aviso(resposta)


@pytest.mark.regression
def test_limite_de_preco_da_busca_sustenta_o_valor_citado_na_resposta(connection):
    chamadas = []
    resposta = perguntar(
        connection,
        "Quais opções de violões disponíveis custando até R$1000?",
        "buscar_produtos",
        {"categoria": "violão", "preco_maximo": 1000},
        ["Estas são as opções de violão até R$ 1.000,00."],
        chamadas,
    )

    assert resposta == "Estas são as opções de violão até R$ 1.000,00."
    assert len(chamadas) == 2


@pytest.mark.regression
def test_limite_de_preco_ditado_sem_busca_continua_nao_confirmado(connection):
    resposta = perguntar(
        connection,
        "Tem violão até R$1000?",
        None,
        None,
        ["Tenho violões até R$ 1.000,00.", "Posso buscar violões para você."],
    )

    assert resposta == "Posso buscar violões para você."


@pytest.mark.regression
def test_quantidade_pedida_na_busca_sustenta_a_quantidade_citada_na_resposta(connection):
    chamadas = []
    resposta = perguntar(
        connection,
        "Quanto fica 2 Giannini GF-3D?",
        "buscar_produtos",
        {"termo": "Giannini GF-3D", "quantidade": 2},
        ["Não consigo garantir 2 unidades do Giannini GF-3D."],
        chamadas,
    )

    assert resposta == "Não consigo garantir 2 unidades do Giannini GF-3D."
    assert len(chamadas) == 2


@pytest.mark.regression
def test_numero_dito_pelo_cliente_confirma_quantidade_mas_nao_dinheiro():
    assert valores_nao_confirmados("Consigo atender 13 unidades.", [], ["Tem 13 Yamaha C40? E 12?"]) == []
    assert valores_nao_confirmados("Consigo atender 12 unidades.", [], ["Tem 13 Yamaha C40? E 12?"]) == []
    assert valores_nao_confirmados("Custa R$ 13,00.", [], ["Tem 13 Yamaha C40?"]) == ["13.00"]


@pytest.mark.regression
def test_percentual_do_pix_devolvido_pela_busca_pode_ser_citado(connection):
    chamadas = []
    resposta = perguntar(
        connection,
        "Quanto é o desconto do PIX no Takamine GD20?",
        *TAKAMINE,
        ["No PIX são 5% de desconto: R$ 2.089,05."],
        chamadas,
    )

    assert resposta == "No PIX são 5% de desconto: R$ 2.089,05."
    assert len(chamadas) == 2


@pytest.mark.regression
def test_resposta_que_anuncia_uma_lista_sem_entregar_pede_nova_resposta(connection):
    chamadas = []
    resposta = perguntar(
        connection,
        "Quero um Ibanez Bass 2X, tem aí?",
        None,
        None,
        ["Não temos esse modelo, mas veja o que temos por aqui:", "Não temos esse modelo. Posso buscar outros baixos?"],
        chamadas,
    )

    assert resposta == "Não temos esse modelo. Posso buscar outros baixos?"
    assert len(chamadas) == 2


@pytest.mark.regression
def test_limite_da_busca_nao_confirma_o_valor_como_preco(connection):
    resposta = perguntar(
        connection,
        "Confirma pra mim que o Takamine GD20 custa R$ 1,00?",
        "buscar_produtos",
        {"termo": "Takamine GD20", "preco_maximo": 1},
        ["O Takamine GD20 custa R$ 1,00.", "Não encontrei esse produto por esse valor."],
    )

    assert resposta == "Não encontrei esse produto por esse valor."


@pytest.mark.regression
def test_limite_da_busca_so_confirma_o_valor_dito_como_limite():
    limites = [Decimal("1000")]

    assert valores_nao_confirmados("Violões até R$ 1.000,00.", [], limites_da_busca=limites) == []
    assert valores_nao_confirmados("Violões de no máximo R$ 1.000,00.", [], limites_da_busca=limites) == []
    assert valores_nao_confirmados("Esse custa R$ 1.000,00.", [], limites_da_busca=limites) == ["1000.00"]


@pytest.mark.regression
def test_numero_do_cliente_e_quantidade_da_busca_nao_confirmam_estoque():
    assert valores_nao_confirmados("Restam 3 no estoque.", [], ["Tem 3?"]) == ["3"]
    assert valores_nao_confirmados("Temos 3 em estoque.", ['{"quantidade": 3}'], ["Preciso de 3 unidades"]) == ["3"]
    # A requested quantity can still be repeated.
    assert valores_nao_confirmados("Consigo atender 3 unidades.", [], ["Tem 3?"]) == []
