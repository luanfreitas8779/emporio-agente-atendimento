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


def modelo_que_busca_violoes_disponiveis_ate_1000(
    mensagens: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    if len(mensagens) == 1:
        argumentos = {
            "categoria": "Violões",
            "preco_maximo": 1000,
            "somente_disponiveis": True,
        }
        return ModelResponse(parts=[ToolCallPart("buscar_produtos", argumentos)])
    produtos = mensagens[-1].parts[0].content
    return ModelResponse(parts=[TextPart(str(len(produtos)))])


def test_agente_lista_os_12_violoes_disponiveis_ate_1000_reais(conexao):
    with agente.override(
        model=FunctionModel(modelo_que_busca_violoes_disponiveis_ate_1000)
    ):
        resposta = responder("Violões disponíveis até R$ 1000?", Sessao(conexao))

    assert resposta == "12"


def modelo_que_sugere_alternativas_ao_produto_indisponivel(
    mensagens: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    resultados = [
        parte.content
        for mensagem in mensagens
        for parte in mensagem.parts
        if parte.part_kind == "tool-return"
    ]
    if not resultados:
        return ModelResponse(
            parts=[ToolCallPart("buscar_produtos", {"termo": "Giannini GF-3D"})]
        )
    if len(resultados) == 1:
        (giannini,) = resultados[0]
        assert giannini.disponibilidade == "indisponivel"
        argumentos = {"categoria": giannini.categoria, "somente_disponiveis": True}
        return ModelResponse(parts=[ToolCallPart("buscar_produtos", argumentos)])
    nomes = [produto.nome for produto in resultados[1]]
    return ModelResponse(parts=[TextPart("; ".join(nomes))])


def test_agente_encontra_alternativas_disponiveis_para_produto_sem_estoque(conexao):
    with agente.override(
        model=FunctionModel(modelo_que_sugere_alternativas_ao_produto_indisponivel)
    ):
        resposta = responder("Tem o Giannini GF-3D?", Sessao(conexao))

    assert "Yamaha C40 Nylon Natural" in resposta
    assert "Giannini GF-3D" not in resposta


def modelo_que_consulta_os_horarios(
    mensagens: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    if len(mensagens) == 1:
        return ModelResponse(
            parts=[ToolCallPart("consultar_politicas", {"secao": "horarios"})]
        )
    return ModelResponse(parts=[TextPart(mensagens[-1].parts[0].content)])


def test_agente_responde_o_horario_de_sabado_a_partir_da_politica(conexao):
    with agente.override(model=FunctionModel(modelo_que_consulta_os_horarios)):
        resposta = responder("Abre sábado?", Sessao(conexao))

    assert "Sábado: 09:00 às 13:00" in resposta


def modelo_que_calcula_o_parcelamento(
    mensagens: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    if len(mensagens) == 1:
        argumentos = {"secao": "pagamentos", "valor": 349.90, "parcelas": 6}
        return ModelResponse(parts=[ToolCallPart("consultar_politicas", argumentos)])
    return ModelResponse(parts=[TextPart(mensagens[-1].parts[0].content)])


def test_agente_informa_que_349_90_em_6x_nao_atende_a_parcela_minima(conexao):
    with agente.override(model=FunctionModel(modelo_que_calcula_o_parcelamento)):
        resposta = responder("Dá pra pagar R$ 349,90 em 6x?", Sessao(conexao))

    assert "6x não atende" in resposta


def modelo_que_pede_secao_inexistente(
    mensagens: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    if len(mensagens) == 1:
        return ModelResponse(
            parts=[ToolCallPart("consultar_politicas", {"secao": "fofocas"})]
        )
    return ModelResponse(parts=[TextPart("tentou de novo")])


def test_agente_recusa_secao_fora_da_lista_e_o_modelo_tenta_de_novo(conexao):
    with agente.override(model=FunctionModel(modelo_que_pede_secao_inexistente)):
        resposta = responder("Me conta uma fofoca", Sessao(conexao))

    assert resposta == "tentou de novo"


def modelo_que_consulta_o_pedido_8(
    mensagens: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    if len(mensagens) == 1:
        return ModelResponse(
            parts=[ToolCallPart("consultar_meus_pedidos", {"numero_pedido": 8})]
        )
    return ModelResponse(parts=[TextPart(str(mensagens[-1].parts[0].content))])


def test_cliente_identificado_consulta_o_status_e_o_rastreio_do_pedido_8(conexao):
    sessao = Sessao(conexao, telefone="(67) 99654-7821")

    with agente.override(model=FunctionModel(modelo_que_consulta_o_pedido_8)):
        resposta = responder("Onde está meu pedido 8?", sessao)

    assert "shipped" in resposta
    assert "BRJL5544332BR" in resposta


def test_telefone_sem_cadastro_recebe_a_explicacao_de_que_nao_ha_pedidos(conexao):
    sessao = Sessao(conexao, telefone="(67) 90000-0000")

    with agente.override(model=FunctionModel(modelo_que_consulta_o_pedido_8)):
        resposta = responder("Onde está meu pedido 8?", sessao)

    assert "sem cadastro" in resposta
    assert "shipped" not in resposta


def test_sessao_sem_telefone_tambem_nao_consulta_pedidos(conexao):
    with agente.override(model=FunctionModel(modelo_que_consulta_o_pedido_8)):
        resposta = responder("Onde está meu pedido 8?", Sessao(conexao))

    assert "sem cadastro" in resposta
