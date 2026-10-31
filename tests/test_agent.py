import asyncio

import pytest
from pydantic_ai import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from src.agent import SEM_CADASTRO, Sessao, agente, responder
from src.load_data import ler_csv
from tests.conftest import PASTA_DADOS


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


def modelo_que_chama(ferramenta: str, argumentos: dict, capturados: list):
    """Chama a ferramenta uma vez e guarda o retorno, sem depender do texto dele."""

    def modelo(mensagens: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(mensagens) == 1:
            return ModelResponse(parts=[ToolCallPart(ferramenta, argumentos)])
        capturados.append(mensagens[-1].parts[0])
        return ModelResponse(parts=[TextPart("ok")])

    return modelo


def chamar_ferramenta(conexao, telefone, ferramenta, argumentos):
    capturados: list = []
    with agente.override(model=FunctionModel(modelo_que_chama(ferramenta, argumentos, capturados))):
        responder("Teste", Sessao(conexao, telefone=telefone))
    return capturados[0]


ANA = "(67) 99654-7821"


def test_cliente_identificado_consulta_o_status_e_o_rastreio_do_pedido_8(conexao):
    retorno = chamar_ferramenta(conexao, ANA, "consultar_meus_pedidos", {"numero_pedido": 8})

    (pedido,) = retorno.content
    assert pedido.status == "shipped"
    assert pedido.rastreio == "BRJL5544332BR"


def test_telefone_sem_cadastro_recebe_a_explicacao_de_que_nao_ha_pedidos(conexao):
    retorno = chamar_ferramenta(
        conexao, "(67) 90000-0000", "consultar_meus_pedidos", {"numero_pedido": 8}
    )

    assert retorno.content == SEM_CADASTRO


def test_sessao_sem_telefone_tambem_nao_consulta_pedidos(conexao):
    retorno = chamar_ferramenta(conexao, None, "consultar_meus_pedidos", {"numero_pedido": 8})

    assert retorno.content == SEM_CADASTRO


def test_pedido_de_outro_cliente_volta_vazio_para_o_agente(conexao):
    # O pedido 5 pertence ao cliente 5.
    retorno = chamar_ferramenta(conexao, ANA, "consultar_meus_pedidos", {"numero_pedido": 5})

    assert retorno.content == []


def test_mensagem_nao_consegue_trocar_o_cliente_consultado(conexao):
    # O pedido 4 é do cliente 1; a sessão é da cliente 2.
    retorno = chamar_ferramenta(
        conexao, ANA, "consultar_meus_pedidos", {"numero_pedido": 4, "customer_id": 1}
    )

    # O argumento extra é recusado e nenhum pedido chega a ser consultado.
    assert retorno.outcome == "retried"
    assert retorno.content[0]["type"] == "extra_forbidden"


def modelo_que_devolve_as_instrucoes(
    mensagens: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    return ModelResponse(parts=[TextPart(info.instructions or "")])


def test_cliente_cadastrado_e_chamado_pelo_nome(conexao):
    sessao = Sessao(conexao, telefone="(67) 99654-7821")

    with agente.override(model=FunctionModel(modelo_que_devolve_as_instrucoes)):
        instrucoes = responder("Oi!", sessao)

    assert "Ana Carolina Ferreira" in instrucoes


def test_instrucoes_nao_expoem_dados_pessoais_alem_do_nome(conexao):
    sessao = Sessao(conexao, telefone=ANA)

    with agente.override(model=FunctionModel(modelo_que_devolve_as_instrucoes)):
        instrucoes = responder("Oi!", sessao)

    # A fonte dos valores é o CSV, não o código sob teste.
    for cliente in ler_csv(PASTA_DADOS / "customers.csv"):
        assert cliente["email"] not in instrucoes
        assert cliente["phone"] not in instrucoes


def test_retorno_dos_pedidos_nao_expoe_email_nem_cidade(conexao):
    retorno = chamar_ferramenta(conexao, ANA, "consultar_meus_pedidos", {})

    texto = repr(retorno.content)
    for cliente in ler_csv(PASTA_DADOS / "customers.csv"):
        assert cliente["email"] not in texto
    assert "Campo Grande" not in texto


def test_telefone_sem_cadastro_nao_recebe_nome_nas_instrucoes(conexao):
    sessao = Sessao(conexao, telefone="(67) 90000-0000")

    with agente.override(model=FunctionModel(modelo_que_devolve_as_instrucoes)):
        instrucoes = responder("Oi!", sessao)

    assert "sem cadastro" in instrucoes


def modelo_que_envia_argumentos(ferramenta: str, argumentos: dict):
    def modelo(mensagens: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        pediu_correcao = any(
            getattr(parte, "outcome", None) == "retried" or parte.part_kind == "retry-prompt"
            for mensagem in mensagens
            for parte in mensagem.parts
        )
        if pediu_correcao:
            return ModelResponse(parts=[TextPart("argumento recusado")])
        if len(mensagens) == 1:
            return ModelResponse(parts=[ToolCallPart(ferramenta, argumentos)])
        return ModelResponse(parts=[TextPart("argumento aceito")])

    return modelo


@pytest.mark.parametrize(
    "ferramenta, argumentos",
    [
        ("consultar_politicas", {"secao": "pagamentos", "valor": -5}),
        ("consultar_politicas", {"secao": "pagamentos", "valor": 100, "parcelas": 0}),
        ("buscar_produtos", {"preco_maximo": -1}),
        ("consultar_meus_pedidos", {"numero_pedido": 0}),
    ],
)
def test_ferramentas_recusam_argumentos_fora_da_faixa(conexao, ferramenta, argumentos):
    sessao = Sessao(conexao, telefone="(67) 99654-7821")

    with agente.override(model=FunctionModel(modelo_que_envia_argumentos(ferramenta, argumentos))):
        resposta = responder("Teste", sessao)

    assert resposta == "argumento recusado"
