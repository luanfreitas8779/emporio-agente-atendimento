import asyncio
from datetime import date

import pytest
from pydantic_ai import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from src import calculations, catalog
from src.agent import SAFE_ANSWER, SEM_CADASTRO, Session, agent, respond
from src.database import connect
from src.interests import list_pending, register
from src.load_data import read_csv
from src.memory import ConversationState, load_state, conversation_for_display, save_state
from src.restock import restock
from tests.conftest import DATA_DIR


def modelo_que_consulta_o_preco(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    if len(messages) == 1:
        return ModelResponse(
            parts=[ToolCallPart("search_products", {"search_term": "Takamine GD20"})]
        )
    result = messages[-1].parts[0].content
    return ModelResponse(parts=[TextPart(f"Encontrei: {result}")])


def test_responde_com_o_preco_vindo_do_catalogo(connection):
    with agent.override(model=FunctionModel(modelo_que_consulta_o_preco)):
        answer = respond("Quanto custa o Takamine GD20?", Session(connection))

    assert "R$ 2.199,00" in answer


@pytest.mark.regression
def test_responde_com_um_loop_assincrono_em_execucao(connection):
    async def responder_dentro_do_loop():
        return respond("Quanto custa o Takamine GD20?", Session(connection))

    with agent.override(model=FunctionModel(modelo_que_consulta_o_preco)):
        answer = asyncio.run(responder_dentro_do_loop())

    assert "R$ 2.199,00" in answer


def modelo_que_busca_violoes_disponiveis_ate_1000(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    if len(messages) == 1:
        arguments = {
            "category": "Violões",
            "max_price": 1000,
            "only_available": True,
        }
        return ModelResponse(parts=[ToolCallPart("search_products", arguments)])
    products = messages[-1].parts[0].content
    return ModelResponse(parts=[TextPart(str(len(products)))])


def test_agente_lista_os_12_violoes_disponiveis_ate_1000_reais(connection):
    with agent.override(
        model=FunctionModel(modelo_que_busca_violoes_disponiveis_ate_1000)
    ):
        answer = respond("Violões disponíveis até R$ 1000?", Session(connection))

    assert answer == "12"


def modelo_que_lista_as_promocoes_ativas(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    if len(messages) == 1:
        return ModelResponse(parts=[ToolCallPart("search_products", {"only_on_sale": True})])
    products = messages[-1].parts[0].content
    rows = [f"{p.name}: {p.price}, {p.discount_percent}%, {p.final_price}" for p in products]
    return ModelResponse(parts=[TextPart("\n".join(rows))])


def test_agente_lista_os_4_produtos_em_promocao_com_preco_original_percentual_e_preco_final(connection):
    with agent.override(model=FunctionModel(modelo_que_lista_as_promocoes_ativas)):
        answer = respond("Quais produtos estão em promoção agora?", Session(connection))

    assert len(answer.splitlines()) == 4
    assert "Crafter HT-100 Folk Aço Natural: R$ 2.399,00, 18%, R$ 1.967,18" in answer


def modelo_que_sugere_alternativas_ao_produto_indisponivel(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    resultados = [
        part.content
        for message in messages
        for part in message.parts
        if part.part_kind == "tool-return"
    ]
    if not resultados:
        return ModelResponse(
            parts=[ToolCallPart("search_products", {"search_term": "Giannini GF-3D"})]
        )
    if len(resultados) == 1:
        (giannini,) = resultados[0]
        assert giannini.availability == "indisponivel"
        arguments = {"category": giannini.category, "only_available": True}
        return ModelResponse(parts=[ToolCallPart("search_products", arguments)])
    names = [product.name for product in resultados[1]]
    return ModelResponse(parts=[TextPart("; ".join(names))])


def test_agente_encontra_alternativas_disponiveis_para_produto_sem_estoque(connection):
    with agent.override(
        model=FunctionModel(modelo_que_sugere_alternativas_ao_produto_indisponivel)
    ):
        answer = respond("Tem o Giannini GF-3D?", Session(connection))

    assert "Yamaha C40 Nylon Natural" in answer
    assert "Giannini GF-3D" not in answer


def modelo_que_consulta_os_horarios(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    if len(messages) == 1:
        return ModelResponse(
            parts=[ToolCallPart("get_policies", {"section": "horarios"})]
        )
    return ModelResponse(parts=[TextPart(messages[-1].parts[0].content)])


def test_agente_responde_o_horario_de_sabado_a_partir_da_politica(connection):
    with agent.override(model=FunctionModel(modelo_que_consulta_os_horarios)):
        answer = respond("Abre sábado?", Session(connection))

    assert "Sábado: 09:00 às 13:00" in answer


def modelo_que_calcula_o_parcelamento(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    if len(messages) == 1:
        arguments = {"section": "pagamentos", "amount": 349.90, "installments": 6}
        return ModelResponse(parts=[ToolCallPart("get_policies", arguments)])
    return ModelResponse(parts=[TextPart(messages[-1].parts[0].content)])


def test_agente_informa_que_349_90_em_6x_nao_atende_a_parcela_minima(connection):
    with agent.override(model=FunctionModel(modelo_que_calcula_o_parcelamento)):
        answer = respond("Dá pra pagar R$ 349,90 em 6x?", Session(connection))

    assert "6x não atende" in answer


def modelo_que_pede_secao_inexistente(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    if len(messages) == 1:
        return ModelResponse(
            parts=[ToolCallPart("get_policies", {"section": "fofocas"})]
        )
    return ModelResponse(parts=[TextPart("tentou de novo")])


def test_agente_recusa_secao_fora_da_lista_e_o_modelo_tenta_de_novo(connection):
    with agent.override(model=FunctionModel(modelo_que_pede_secao_inexistente)):
        answer = respond("Me conta uma fofoca", Session(connection))

    assert answer == "tentou de novo"


def modelo_que_chama(tool: str, arguments: dict, capturados: list):
    """Calls the tool once and stores the result, without depending on its text."""

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart(tool, arguments)])
        capturados.append(messages[-1].parts[0])
        return ModelResponse(parts=[TextPart("ok")])

    return model


def chamar_ferramenta(connection, phone, tool, arguments):
    capturados: list = []
    with agent.override(model=FunctionModel(modelo_que_chama(tool, arguments, capturados))):
        respond("Teste", Session(connection, phone=phone))
    return capturados[0]


ANA = "(67) 99654-7821"


def test_cliente_identificado_consulta_o_status_e_o_rastreio_do_pedido_8(connection):
    retorno = chamar_ferramenta(connection, ANA, "consultar_meus_pedidos", {"numero_pedido": 8})

    (order,) = retorno.content
    assert order.status == "shipped"
    assert order.rastreio == "BRJL5544332BR"


def test_telefone_sem_cadastro_recebe_a_explicacao_de_que_nao_ha_pedidos(connection):
    retorno = chamar_ferramenta(
        connection, "(67) 90000-0000", "consultar_meus_pedidos", {"numero_pedido": 8}
    )

    assert retorno.content == SEM_CADASTRO


def test_sessao_sem_telefone_tambem_nao_consulta_pedidos(connection):
    retorno = chamar_ferramenta(connection, None, "consultar_meus_pedidos", {"numero_pedido": 8})

    assert retorno.content == SEM_CADASTRO


def test_pedido_de_outro_cliente_volta_vazio_para_o_agente(connection):
    # Order 5 belongs to customer 5.
    retorno = chamar_ferramenta(connection, ANA, "consultar_meus_pedidos", {"numero_pedido": 5})

    assert retorno.content == []


@pytest.mark.regression
def test_mensagem_nao_consegue_trocar_o_cliente_consultado(connection):
    # Order 4 belongs to customer 1; the session belongs to customer 2.
    retorno = chamar_ferramenta(
        connection, ANA, "consultar_meus_pedidos", {"numero_pedido": 4, "customer_id": 1}
    )

    # The extra argument is rejected and no order is looked up.
    assert retorno.outcome == "retried"
    assert retorno.content[0]["type"] == "extra_forbidden"


def modelo_que_devolve_as_instrucoes(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    return ModelResponse(parts=[TextPart(info.instructions or "")])


def test_cliente_cadastrado_e_chamado_pelo_nome(connection):
    sessao = Session(connection, phone="(67) 99654-7821")

    with agent.override(model=FunctionModel(modelo_que_devolve_as_instrucoes)):
        instrucoes = respond("Oi!", sessao)

    assert "Ana" in instrucoes
    assert "Carolina" not in instrucoes
    assert "Ferreira" not in instrucoes


def test_instrucoes_nao_expoem_dados_pessoais_alem_do_nome(connection):
    sessao = Session(connection, phone=ANA)

    with agent.override(model=FunctionModel(modelo_que_devolve_as_instrucoes)):
        instrucoes = respond("Oi!", sessao)

    # The source of the values is the CSV, not the code under test.
    for customer in read_csv(DATA_DIR / "customers.csv"):
        assert customer["email"] not in instrucoes
        assert customer["phone"] not in instrucoes


def test_retorno_dos_pedidos_nao_expoe_email_nem_cidade(connection):
    retorno = chamar_ferramenta(connection, ANA, "consultar_meus_pedidos", {})

    text = repr(retorno.content)
    for customer in read_csv(DATA_DIR / "customers.csv"):
        assert customer["email"] not in text
    assert "Campo Grande" not in text


def test_telefone_sem_cadastro_nao_recebe_nome_nas_instrucoes(connection):
    sessao = Session(connection, phone="(67) 90000-0000")

    with agent.override(model=FunctionModel(modelo_que_devolve_as_instrucoes)):
        instrucoes = respond("Oi!", sessao)

    assert "sem cadastro" in instrucoes


def modelo_que_envia_argumentos(tool: str, arguments: dict):
    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        pediu_correcao = any(
            getattr(part, "outcome", None) == "retried" or part.part_kind == "retry-prompt"
            for message in messages
            for part in message.parts
        )
        if pediu_correcao:
            return ModelResponse(parts=[TextPart("argumento recusado")])
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart(tool, arguments)])
        return ModelResponse(parts=[TextPart("argumento aceito")])

    return model


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("get_policies", {"section": "pagamentos", "amount": -5}),
        ("get_policies", {"section": "pagamentos", "amount": 100, "installments": 0}),
        ("search_products", {"max_price": -1}),
        ("consultar_meus_pedidos", {"numero_pedido": 0}),
    ],
)
@pytest.mark.regression
def test_ferramentas_recusam_argumentos_fora_da_faixa(connection, tool, arguments):
    sessao = Session(connection, phone="(67) 99654-7821")

    with agent.override(model=FunctionModel(modelo_que_envia_argumentos(tool, arguments))):
        answer = respond("Teste", sessao)

    assert answer == "argumento recusado"


@pytest.mark.regression
def test_modelo_recebe_a_situacao_traduzida_e_nao_o_status_cru(connection):
    retorno = chamar_ferramenta(connection, ANA, "consultar_meus_pedidos", {"numero_pedido": 8})

    visto_pelo_modelo = retorno.model_response_str()
    assert "enviado" in visto_pelo_modelo
    assert "shipped" not in visto_pelo_modelo


def modelo_que_lista_as_perguntas_vistas(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    perguntas = [
        part.content
        for message in messages
        for part in message.parts
        if part.part_kind == "user-prompt"
    ]
    return ModelResponse(parts=[TextPart(" | ".join(perguntas))])


def test_segunda_mensagem_chega_ao_modelo_junto_com_a_primeira(connection):
    sessao = Session(connection, phone=ANA)

    with agent.override(model=FunctionModel(modelo_que_lista_as_perguntas_vistas)):
        respond("Quero um violão", sessao)
        answer = respond("E o mais barato?", sessao)

    assert answer == "Quero um violão | E o mais barato?"


def test_nova_sessao_com_o_mesmo_telefone_recupera_a_conversa(connection, tmp_path):
    with agent.override(model=FunctionModel(modelo_que_lista_as_perguntas_vistas)):
        respond("Quero um violão", Session(connection, phone=ANA))

        # Another connection to the same file is equivalent to restarting the application.
        nova = connect(tmp_path / "teste.db")
        try:
            answer = respond("Chegou?", Session(nova, phone="67996547821"))
        finally:
            nova.close()

    assert answer == "Quero um violão | Chegou?"


def test_telefone_diferente_nao_recebe_o_historico_de_outra_pessoa(connection):
    with agent.override(model=FunctionModel(modelo_que_lista_as_perguntas_vistas)):
        respond("Quero um violão", Session(connection, phone=ANA))
        answer = respond("Oi", Session(connection, phone="(67) 90000-0000"))

    assert answer == "Oi"


def test_sessao_sem_telefone_valido_nao_guarda_conversa(connection):
    with agent.override(model=FunctionModel(modelo_que_lista_as_perguntas_vistas)):
        respond("Quero um violão", Session(connection, phone="123"))
        answer = respond("Oi", Session(connection, phone="123"))

    assert answer == "Oi"


def modelo_que_consulta_o_horario_e_lista_as_perguntas(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    if messages[-1].parts[0].part_kind == "user-prompt":
        return ModelResponse(
            parts=[ToolCallPart("get_policies", {"section": "horarios"})]
        )
    return modelo_que_lista_as_perguntas_vistas(messages, info)


@pytest.mark.regression
def test_historico_enviado_ao_modelo_nao_separa_chamada_de_ferramenta_do_retorno(connection, monkeypatch):
    # A small limit forces the cut in the middle of a turn with a tool.
    monkeypatch.setattr("src.memory.MAX_HISTORY_MESSAGES", 7)
    sessao = Session(connection, phone=ANA)

    with agent.override(
        model=FunctionModel(modelo_que_consulta_o_horario_e_lista_as_perguntas)
    ):
        for pergunta in ("P1", "P2", "P3"):
            respond(pergunta, sessao)
        answer = respond("P4", sessao)

    # Each turn with a tool has 4 messages: only one whole turn would fit in 7.
    assert answer == "P3 | P4"


def modelo_que_repete_um_preco_de_turno_anterior(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    ultima = messages[-1].parts[0]
    if ultima.part_kind == "user-prompt" and ultima.content == "Quanto custa?":
        return ModelResponse(
            parts=[ToolCallPart("search_products", {"search_term": "Takamine GD20"})]
        )
    if ultima.part_kind == "tool-return":
        return ModelResponse(parts=[TextPart("Custa R$ 2.199,00")])
    return ModelResponse(parts=[TextPart("Continua R$ 2.199,00")])


@pytest.mark.regression
def test_guarda_nao_aceita_valor_citado_apenas_em_turno_anterior(connection):
    sessao = Session(connection, phone=ANA)

    with agent.override(model=FunctionModel(modelo_que_repete_um_preco_de_turno_anterior)):
        primeira = respond("Quanto custa?", sessao)
        segunda = respond("E agora?", sessao)

    assert primeira == "Custa R$ 2.199,00"
    assert segunda == SAFE_ANSWER


def modelo_que_inventa_um_preco_ate_a_pergunta_seguinte(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    # The correction requested by the guardrail also arrives as a customer message, so
    # the model insists while the next question has not appeared yet.
    perguntas = [
        part.content
        for message in messages
        for part in message.parts
        if part.part_kind == "user-prompt"
    ]
    if "Preço do violão?" in perguntas and "Oi" not in perguntas:
        return ModelResponse(parts=[TextPart("Custa R$ 9,99")])
    return modelo_que_lista_as_perguntas_vistas(messages, info)


def test_resposta_segura_tambem_entra_no_historico(connection):
    sessao = Session(connection, phone=ANA)

    with agent.override(model=FunctionModel(modelo_que_inventa_um_preco_ate_a_pergunta_seguinte)):
        segura = respond("Preço do violão?", sessao)
        answer = respond("Oi", sessao)

    assert segura == SAFE_ANSWER
    assert answer == "Preço do violão? | Oi"


@pytest.mark.regression
def test_historico_corrompido_e_ignorado_e_o_atendimento_continua(connection):
    sessao = Session(connection, phone=ANA)

    with agent.override(model=FunctionModel(modelo_que_lista_as_perguntas_vistas)):
        respond("Quero um violão", sessao)
        connection.execute("UPDATE messages SET content = 'não é json'")
        answer = respond("Oi", sessao)

    assert answer == "Oi"


def modelo_que_busca_um_produto_e_depois_mostra_as_instrucoes(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    ultima = messages[-1].parts[0]
    if ultima.part_kind == "user-prompt" and ultima.content == "Tem o Giannini?":
        return ModelResponse(
            parts=[ToolCallPart("search_products", {"search_term": "Giannini GF-3D"})]
        )
    if ultima.part_kind == "tool-return":
        return ModelResponse(parts=[TextPart("ok")])
    return ModelResponse(parts=[TextPart(info.instructions or "")])


def test_produto_unico_encontrado_fica_em_foco_nas_mensagens_seguintes(connection):
    sessao = Session(connection, phone=ANA)

    with agent.override(
        model=FunctionModel(modelo_que_busca_um_produto_e_depois_mostra_as_instrucoes)
    ):
        respond("Tem o Giannini?", sessao)
        instrucoes = respond("E o preço?", sessao)

    assert "Produto em foco: Giannini GF-3D" in instrucoes


def modelo_que_consulta_o_pedido_8_e_depois_mostra_as_instrucoes(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    ultima = messages[-1].parts[0]
    if ultima.part_kind == "user-prompt" and ultima.content == "Cadê meu pedido?":
        return ModelResponse(
            parts=[ToolCallPart("consultar_meus_pedidos", {"numero_pedido": 8})]
        )
    if ultima.part_kind == "tool-return":
        return ModelResponse(parts=[TextPart("ok")])
    return ModelResponse(parts=[TextPart(info.instructions or "")])


def test_pedido_consultado_fica_em_analise_nas_mensagens_seguintes(connection):
    sessao = Session(connection, phone=ANA)

    with agent.override(
        model=FunctionModel(modelo_que_consulta_o_pedido_8_e_depois_mostra_as_instrucoes)
    ):
        respond("Cadê meu pedido?", sessao)
        instrucoes = respond("E o rastreio?", sessao)

    assert "Pedido em análise: 8" in instrucoes


def test_estado_sobrevive_ao_reinicio_e_nao_vaza_para_outro_telefone(connection, tmp_path):
    model = FunctionModel(modelo_que_busca_um_produto_e_depois_mostra_as_instrucoes)
    with agent.override(model=model):
        respond("Tem o Giannini?", Session(connection, phone=ANA))

        nova = connect(tmp_path / "teste.db")
        try:
            da_ana = respond("E o preço?", Session(nova, phone="67996547821"))
            de_outra_pessoa = respond("E o preço?", Session(nova, phone="(67) 90000-0000"))
        finally:
            nova.close()

    assert "Produto em foco: Giannini GF-3D" in da_ana
    assert "Produto em foco" not in de_outra_pessoa


def modelo_que_busca_varios_produtos_e_depois_mostra_as_instrucoes(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    ultima = messages[-1].parts[0]
    if ultima.part_kind == "user-prompt" and ultima.content == "Quais violões?":
        return ModelResponse(parts=[ToolCallPart("search_products", {"category": "Violões"})])
    if ultima.part_kind == "tool-return":
        return ModelResponse(parts=[TextPart("ok")])
    return ModelResponse(parts=[TextPart(info.instructions or "")])


def test_busca_com_varios_resultados_nao_define_produto_em_foco(connection):
    sessao = Session(connection, phone=ANA)

    with agent.override(
        model=FunctionModel(modelo_que_busca_varios_produtos_e_depois_mostra_as_instrucoes)
    ):
        respond("Quais violões?", sessao)
        instrucoes = respond("E agora?", sessao)

    assert "Produto em foco" not in instrucoes


def test_conversa_antiga_e_exibida_so_com_o_que_o_cliente_viu(connection):
    sessao = Session(connection, phone=ANA)

    with agent.override(
        model=FunctionModel(modelo_que_consulta_o_horario_e_lista_as_perguntas)
    ):
        respond("P1", sessao)
        respond("P2", sessao)

    assert conversation_for_display(connection, "67996547821") == [
        ("user", "P1"),
        ("assistant", "P1"),
        ("user", "P2"),
        ("assistant", "P1 | P2"),
    ]


def modelo_que_inventa_um_preco_e_depois_se_corrige(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    if len(messages) == 1:
        return ModelResponse(parts=[TextPart("Custa R$ 9,99")])
    return ModelResponse(parts=[TextPart("Não tenho esse valor")])


@pytest.mark.regression
def test_conversa_antiga_nao_exibe_a_resposta_rejeitada_pela_guarda(connection):
    with agent.override(model=FunctionModel(modelo_que_inventa_um_preco_e_depois_se_corrige)):
        respond("Preço?", Session(connection, phone=ANA))

    assert conversation_for_display(connection, ANA) == [
        ("user", "Preço?"),
        ("assistant", "Não tenho esse valor"),
    ]


def test_telefone_sem_conversa_exibe_lista_vazia(connection):
    assert conversation_for_display(connection, "(67) 90000-0000") == []


LETICIA = "(67) 99789-0123"


def chamar_ferramenta_na_data(connection, phone, today, tool, arguments, message="Teste"):
    capturados: list = []
    model = FunctionModel(modelo_que_chama(tool, arguments, capturados))
    with agent.override(model=model):
        respond(message, Session(connection, phone=phone, today=today))
    return capturados[0]


def test_ferramenta_de_devolucao_usa_o_pedido_do_cliente_e_a_data_da_sessao(connection):
    retorno = chamar_ferramenta_na_data(
        connection, LETICIA, date(2026, 2, 20), "assess_return",
        {"numero_pedido": 7, "reason": "arrependimento", "channel": "online"},
        message="Comprei online e quero devolver o pedido 7 por arrependimento",
    )

    assert retorno.content.result == "dentro_do_prazo"
    assert retorno.content.rules[0].deadline == "24/02/2026"


@pytest.mark.regression
def test_canal_que_o_cliente_nao_citou_e_ignorado_e_o_veredito_pede_o_canal(connection):
    # The model assumed "online"; the customer only gave the reason.
    retorno = chamar_ferramenta_na_data(
        connection, LETICIA, date(2026, 2, 20), "assess_return",
        {"numero_pedido": 7, "reason": "arrependimento", "channel": "online"},
        message="Quero devolver o pedido 7 por arrependimento",
    )

    assert retorno.content.result == "faltam_dados"


@pytest.mark.regression
def test_canal_diferente_do_que_o_cliente_citou_tambem_e_ignorado(connection):
    retorno = chamar_ferramenta_na_data(
        connection, LETICIA, date(2026, 2, 20), "assess_return",
        {"numero_pedido": 7, "reason": "arrependimento", "channel": "online"},
        message="Comprei presencialmente e quero devolver o pedido 7 por arrependimento",
    )

    assert retorno.content.result == "faltam_dados"


def test_devolucao_de_pedido_de_outro_cliente_volta_como_nao_encontrado(connection):
    # Order 7 belongs to customer 14; the session belongs to customer 2.
    retorno = chamar_ferramenta(
        connection, ANA, "assess_return", {"numero_pedido": 7, "reason": "defeito"}
    )

    assert retorno.content.result == "pedido_nao_encontrado"


def test_devolucao_sem_cadastro_explica_que_pedidos_exigem_telefone_cadastrado(connection):
    retorno = chamar_ferramenta(
        connection, "(67) 90000-0000", "assess_return", {"numero_pedido": 7, "reason": "defeito"}
    )

    assert retorno.content == SEM_CADASTRO


@pytest.mark.parametrize(
    "arguments",
    [
        {"numero_pedido": 7, "reason": "fiquei com dó"},
        {"numero_pedido": 7, "reason": "defeito", "customer_id": 14},
    ],
)
def test_devolucao_recusa_motivo_desconhecido_e_cliente_como_argumento(connection, arguments):
    retorno = chamar_ferramenta(connection, ANA, "assess_return", arguments)

    assert retorno.outcome == "retried"


def modelo_que_avalia_a_devolucao_e_depois_mostra_as_instrucoes(arguments: dict):
    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        ultima = messages[-1].parts[0]
        if ultima.part_kind == "user-prompt" and ultima.content == "Quero devolver":
            return ModelResponse(parts=[ToolCallPart("assess_return", arguments)])
        if ultima.part_kind == "tool-return":
            return ModelResponse(parts=[TextPart("ok")])
        return ModelResponse(parts=[TextPart(info.instructions or "")])

    return model


@pytest.mark.regression
def test_canal_nao_informado_nao_deixa_pergunta_gravada_para_o_proximo_assunto(connection):
    sessao = Session(connection, phone=LETICIA)
    model = modelo_que_avalia_a_devolucao_e_depois_mostra_as_instrucoes(
        {"numero_pedido": 7, "reason": "arrependimento"}
    )

    with agent.override(model=FunctionModel(model)):
        respond("Quero devolver", sessao)
        instrucoes = respond("Foi online", sessao)

    # Tom's question stays only in the history; the state keeps only the order under review.
    assert "Pergunta pendente" not in instrucoes
    assert "Pedido em análise: 7" in instrucoes


@pytest.mark.parametrize("arguments", [
    {"numero_pedido": 7, "reason": "arrependimento"},
    {"numero_pedido": 7, "reason": "arrependimento", "channel": "presencial"},
    {"numero_pedido": 999, "reason": "arrependimento"},
])
@pytest.mark.regression
def test_pedido_que_nao_e_do_cliente_nao_vira_pedido_em_analise(connection, arguments):
    # Order 7 belongs to customer 14; the session belongs to customer 2 (Ana). Order 999 does not exist.
    sessao = Session(connection, phone=ANA)
    model = modelo_que_avalia_a_devolucao_e_depois_mostra_as_instrucoes(arguments)

    with agent.override(model=FunctionModel(model)):
        respond("Quero devolver", sessao)
        instrucoes = respond("Mostra o contexto", sessao)

    assert "Pedido em análise" not in instrucoes


def test_instrucoes_trazem_os_interesses_pendentes_so_do_telefone_da_sessao(connection):
    register(connection, ANA, 96)
    register(connection, "(67) 91111-2222", 90)

    with agent.override(model=FunctionModel(modelo_que_devolve_as_instrucoes)):
        da_ana = respond("Oi!", Session(connection, phone=ANA))
        de_outro = respond("Oi!", Session(connection, phone="(67) 93333-4444"))

    assert "Giannini GF-3D" in da_ana
    assert "Crafter HT-100" not in da_ana
    assert "Giannini GF-3D" not in de_outro
    assert "Crafter HT-100" not in de_outro


def test_ferramenta_registra_o_interesse_do_telefone_da_sessao_e_define_o_foco(connection):
    sessao = Session(connection, phone=ANA)
    capturados: list = []

    with agent.override(
        model=FunctionModel(modelo_que_chama("registrar_interesse", {"product_id": 96}, capturados))
    ):
        respond("Quero acompanhar esse violão", sessao)

    assert list_pending(connection, ANA) == ["Giannini GF-3D Dreadnought Sunburst"]
    assert sessao.state.product_in_focus == 96
    assert "não reserva o produto" in capturados[0].content


@pytest.mark.regression
def test_mensagem_nao_consegue_registrar_interesse_em_outro_telefone(connection):
    retorno = chamar_ferramenta(
        connection, ANA, "registrar_interesse", {"product_id": 96, "phone": "67911112222"}
    )

    assert retorno.outcome == "retried"
    assert list_pending(connection, "67911112222") == []
    assert list_pending(connection, ANA) == []


def modelo_que_retoma_o_interesse(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Reads the interest's name in the context and looks up the catalog, as the prompt says."""
    if len(messages) == 1:
        name = info.instructions.split("Interesses pendentes: ")[1].split(".")[0].split(";")[0]
        return ModelResponse(parts=[ToolCallPart("search_products", {"search_term": name})])
    (product,) = messages[-1].parts[0].content
    return ModelResponse(parts=[TextPart(f"{product.name}: {product.availability}")])


def test_chegou_o_violao_sem_reposicao_informa_que_continua_indisponivel(connection):
    register(connection, ANA, 96)

    with agent.override(model=FunctionModel(modelo_que_retoma_o_interesse)):
        answer = respond("Chegou o violão?", Session(connection, phone=ANA))

    assert answer == "Giannini GF-3D Dreadnought Sunburst: indisponivel"


def test_chegou_o_violao_apos_reposicao_informa_a_disponibilidade(connection):
    register(connection, ANA, 96)
    restock(connection, 96, 5)

    with agent.override(model=FunctionModel(modelo_que_retoma_o_interesse)):
        answer = respond("Chegou o violão?", Session(connection, phone=ANA))

    assert answer == "Giannini GF-3D Dreadnought Sunburst: disponivel"


def test_sem_interesse_salvo_o_contexto_diz_que_nao_ha_nenhum(connection):
    register(connection, "(67) 91111-2222", 96)

    with agent.override(model=FunctionModel(modelo_que_devolve_as_instrucoes)):
        instrucoes = respond("Chegou o violão?", Session(connection, phone=ANA))

    assert "Interesses pendentes: nenhum" in instrucoes
    assert "Giannini" not in instrucoes


def test_busca_com_varios_produtos_limpa_o_foco(connection):
    save_state(connection, ANA, ConversationState(product_in_focus=96))
    capturados: list = []

    with agent.override(
        model=FunctionModel(modelo_que_chama("search_products", {"category": "Violões"}, capturados))
    ):
        respond("Quais violões vocês têm?", Session(connection, phone=ANA))

    assert load_state(connection, ANA).product_in_focus is None


def test_busca_sem_resultado_limpa_o_foco(connection):
    save_state(connection, ANA, ConversationState(product_in_focus=96))
    capturados: list = []

    with agent.override(
        model=FunctionModel(modelo_que_chama("search_products", {"search_term": "saxofone"}, capturados))
    ):
        respond("Tem saxofone?", Session(connection, phone=ANA))

    assert load_state(connection, ANA).product_in_focus is None


def test_contexto_mostra_os_5_interesses_mais_recentes_e_avisa_do_restante(connection):
    ids = [row[0] for row in connection.execute(
        "SELECT product_id FROM products WHERE status = 'active' ORDER BY product_id LIMIT 6"
    )]
    names = [catalog.product_name(connection, i) for i in ids]
    for product in ids:
        register(connection, ANA, product)

    with agent.override(model=FunctionModel(modelo_que_devolve_as_instrucoes)):
        instrucoes = respond("Chegou?", Session(connection, phone=ANA))

    assert names[0] not in instrucoes
    assert all(name in instrucoes for name in names[1:])
    assert "e mais 1" in instrucoes


def test_ferramenta_registra_o_encaminhamento_do_telefone_da_sessao(connection):
    retorno = chamar_ferramenta(
        connection,
        ANA,
        "encaminhar_para_atendente",
        {"reason": "reclamacao", "summary": "Violão chegou com defeito no braço."},
    )

    rows = [tuple(l) for l in connection.execute("SELECT phone, reason, summary FROM handoffs")]
    assert rows == [("67996547821", "reclamacao", "Violão chegou com defeito no braço.")]
    assert "24 horas úteis" in retorno.content


def test_encaminhamento_sem_telefone_valido_explica_e_nao_grava(connection):
    retorno = chamar_ferramenta(
        connection, None, "encaminhar_para_atendente", {"reason": "reclamacao", "summary": "Defeito."}
    )

    assert "não foi possível identificar o telefone" in retorno.content.lower()
    assert "sobre_a_loja" in retorno.content
    assert connection.execute("SELECT COUNT(*) FROM handoffs").fetchone()[0] == 0


@pytest.mark.regression
def test_mensagem_nao_consegue_encaminhar_em_nome_de_outro_telefone(connection):
    retorno = chamar_ferramenta(
        connection,
        ANA,
        "encaminhar_para_atendente",
        {"reason": "reclamacao", "summary": "Defeito.", "phone": "67911112222"},
    )

    assert retorno.outcome == "retried"
    assert connection.execute("SELECT COUNT(*) FROM handoffs").fetchone()[0] == 0


def test_motivo_desconhecido_e_recusado_pela_ferramenta(connection):
    retorno = chamar_ferramenta(
        connection, ANA, "encaminhar_para_atendente", {"reason": "fofoca", "summary": "Defeito."}
    )

    assert retorno.outcome == "retried"
    assert connection.execute("SELECT COUNT(*) FROM handoffs").fetchone()[0] == 0


def modelo_que_sempre_inventa_um_preco(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    return ModelResponse(parts=[TextPart("Custa R$ 9,99")])


def test_resposta_segura_registra_o_encaminhamento_e_informa_o_prazo(connection):
    with agent.override(model=FunctionModel(modelo_que_sempre_inventa_um_preco)):
        answer = respond("Preço do violão?", Session(connection, phone=ANA))

    rows = [tuple(l) for l in connection.execute("SELECT phone, reason, summary FROM handoffs")]
    assert rows == [("67996547821", "sem_resposta_segura", "Preço do violão?")]
    assert answer == SAFE_ANSWER
    assert "24 horas úteis" in answer


def test_resposta_segura_sem_telefone_valido_explica_que_nao_foi_possivel_encaminhar(connection):
    with agent.override(model=FunctionModel(modelo_que_sempre_inventa_um_preco)):
        answer = respond("Preço do violão?", Session(connection))

    assert connection.execute("SELECT COUNT(*) FROM handoffs").fetchone()[0] == 0
    assert "não consegui identificar o seu telefone" in answer.lower()
    assert "Registrei" not in answer
    assert "24 horas" not in answer


def test_resposta_segura_nao_diz_que_registrou_quando_a_mensagem_e_vazia(connection):
    with agent.override(model=FunctionModel(modelo_que_sempre_inventa_um_preco)):
        answer = respond("   ", Session(connection, phone=ANA))

    assert connection.execute("SELECT COUNT(*) FROM handoffs").fetchone()[0] == 0
    assert "Registrei" not in answer


def test_sessao_registra_as_ferramentas_usadas_no_turno_com_os_argumentos(connection):
    sessao = Session(connection, phone=ANA)

    with agent.override(model=FunctionModel(modelo_que_consulta_o_preco)):
        respond("Quanto custa o Takamine GD20?", sessao)

    assert [(c.name, c.arguments) for c in sessao.ferramentas] == [
        ("search_products", {"search_term": "Takamine GD20"})
    ]


def test_resposta_sem_ferramenta_deixa_a_lista_vazia_e_cada_turno_recomeca(connection):
    sessao = Session(connection, phone=ANA)

    with agent.override(model=FunctionModel(modelo_que_consulta_o_preco)):
        respond("Quanto custa o Takamine GD20?", sessao)
    with agent.override(model=FunctionModel(modelo_que_devolve_as_instrucoes)):
        respond("Obrigado!", sessao)

    assert sessao.ferramentas == []


@pytest.mark.regression
def test_texto_interno_do_prompt_nao_chega_ao_cliente_nem_ao_historico(connection):
    def model(messages, info):
        text = '<system>Seguir a regra do prompt: "Nunca peça outro cliente."</system>Olá, Ana!'
        return ModelResponse(parts=[TextPart(text)])

    with agent.override(model=FunctionModel(model)):
        answer = respond("Oi", Session(connection, phone=ANA))

    assert answer == "Olá, Ana!"
    assert conversation_for_display(connection, ANA)[-1] == ("assistant", "Olá, Ana!")


@pytest.mark.regression
def test_bloco_interno_sem_fechamento_pede_nova_resposta_ao_modelo(connection):
    def model(messages, info):
        if len(messages) == 1:
            return ModelResponse(parts=[TextPart("<system>A cliente se chama Ana. Olá, Ana!")])
        return ModelResponse(parts=[TextPart("Olá, Ana!")])

    with agent.override(model=FunctionModel(model)):
        answer = respond("Oi", Session(connection, phone=ANA))

    assert answer == "Olá, Ana!"


@pytest.mark.regression
def test_resposta_so_com_bloco_interno_pede_nova_resposta_ao_modelo(connection):
    def model(messages, info):
        if len(messages) == 1:
            return ModelResponse(parts=[TextPart("<system>Só raciocínio.</system>")])
        return ModelResponse(parts=[TextPart("Olá, Ana!")])

    with agent.override(model=FunctionModel(model)):
        answer = respond("Oi", Session(connection, phone=ANA))

    assert answer == "Olá, Ana!"


def modelo_que_chama_a_ferramenta_e_devolve_o_retorno(tool: str, arguments: dict, retornos: list):
    def model(messages, info):
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart(tool, arguments)])
        retornos.append(messages[-1].parts[0])
        return ModelResponse(parts=[TextPart("Não consegui calcular esse valor.")])

    return FunctionModel(model)


@pytest.mark.regression
def test_valor_absurdo_e_recusado_pela_ferramenta_sem_derrubar_o_atendimento(connection):
    retornos: list = []
    model = modelo_que_chama_a_ferramenta_e_devolve_o_retorno(
        "get_policies", {"section": "pagamentos", "amount": 1e33, "installments": 3}, retornos
    )

    with agent.override(model=model):
        answer = respond("Em quantas vezes posso pagar R$ 999999999999999999999999999999999?", Session(connection, phone=ANA))

    assert answer == "Não consegui calcular esse valor."
    assert retornos[0].outcome == "retried"


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("consultar_meus_pedidos", {"numero_pedido": 10**30}),
        ("assess_return", {"numero_pedido": 10**30, "reason": "arrependimento", "channel": "online"}),
        ("registrar_interesse", {"product_id": 10**30}),
        ("search_products", {"max_price": 1e33}),
    ],
)
@pytest.mark.regression
def test_numero_fora_da_faixa_e_recusado_pela_ferramenta(connection, tool, arguments):
    retornos: list = []
    model = modelo_que_chama_a_ferramenta_e_devolve_o_retorno(tool, arguments, retornos)

    with agent.override(model=model):
        answer = respond("Oi", Session(connection, phone=ANA))

    assert answer == "Não consegui calcular esse valor."
    assert retornos[0].outcome == "retried"


@pytest.mark.regression
def test_ferramenta_de_busca_informa_se_atende_a_quantidade_pedida(connection):
    retornos: list = []
    model = modelo_que_chama_a_ferramenta_e_devolve_o_retorno(
        "search_products", {"search_term": "Yamaha C40", "quantity": 10}, retornos
    )

    with agent.override(model=model):
        respond("Preciso de 10 Yamaha C40", Session(connection, phone=ANA))

    (product,) = retornos[0].content
    assert product.meets_quantity is True
    assert not hasattr(product, "stock")


def modelo_que_responde_em_sequencia(*texts: str):
    def model(messages, info):
        indice = sum(1 for m in messages if isinstance(m, ModelResponse))
        return ModelResponse(parts=[TextPart(texts[min(indice, len(texts) - 1)])])

    return model


@pytest.mark.regression
@pytest.mark.parametrize(
    "promessa",
    [
        "Assim que ele voltar, você já fica sabendo por aqui!",
        "Anotado! Eu te aviso se ele voltar.",
        "Pode deixar, avisaremos você quando chegar.",
        "Quando chegar, você será avisada.",
    ],
)
def test_promessa_de_aviso_pede_nova_resposta_ao_modelo(connection, promessa):
    honesta = "Anotei o seu interesse. Isso não reserva o produto e não garante aviso."
    model = modelo_que_responde_em_sequencia(promessa, honesta)

    with agent.override(model=FunctionModel(model)):
        answer = respond("Me avisa quando chegar?", Session(connection, phone=ANA))

    assert answer == honesta


def test_aviso_de_que_nao_ha_garantia_de_aviso_passa_sem_nova_tentativa(connection):
    honesta = "Anotei o seu interesse. Isso não reserva o produto e não garante aviso nem data."
    model = modelo_que_responde_em_sequencia(honesta, "NÃO DEVERIA CHEGAR")

    with agent.override(model=FunctionModel(model)):
        answer = respond("Me avisa quando chegar?", Session(connection, phone=ANA))

    assert answer == honesta


@pytest.mark.regression
def test_recusa_explicita_de_avisar_passa_sem_nova_tentativa(connection):
    honesta = "Anotei o interesse, mas não posso te avisar quando ele chegar. Consulte a loja."
    model = modelo_que_responde_em_sequencia(honesta, "NÃO DEVERIA CHEGAR")

    with agent.override(model=FunctionModel(model)):
        answer = respond("Me avisa quando chegar?", Session(connection, phone=ANA))

    assert answer == honesta


@pytest.mark.regression
@pytest.mark.parametrize(
    "message",
    [
        "Vi o preço no site e quero devolver o pedido 7 por arrependimento",
        "Os onlines de violão me deixaram em dúvida, quero devolver o pedido 7 por arrependimento",
    ],
)
def test_palavra_parecida_com_o_canal_nao_conta_como_canal_citado(connection, message):
    retorno = chamar_ferramenta_na_data(
        connection, LETICIA, date(2026, 2, 20), "assess_return",
        {"numero_pedido": 7, "reason": "arrependimento", "channel": "online"},
        message=message,
    )

    assert retorno.content.result == "faltam_dados"


@pytest.mark.parametrize("message", ["Comprei pelo site, quero devolver o pedido 7", "Foi ONLINE mesmo"])
def test_canal_dito_com_clareza_continua_valendo(connection, message):
    retorno = chamar_ferramenta_na_data(
        connection, LETICIA, date(2026, 2, 20), "assess_return",
        {"numero_pedido": 7, "reason": "arrependimento", "channel": "online"},
        message=message,
    )

    assert retorno.content.result == "dentro_do_prazo"


@pytest.mark.regression
def test_promessa_de_retorno_da_equipe_do_encaminhamento_passa_sem_nova_tentativa(connection):
    legitima = "Registrei o seu caso. Entraremos em contato em até 24 horas úteis."
    model = modelo_que_responde_em_sequencia(legitima, "NÃO DEVERIA CHEGAR")

    with agent.override(model=FunctionModel(model)):
        answer = respond("Quero falar com um atendente", Session(connection, phone=ANA))

    assert answer == legitima


@pytest.mark.regression
def test_instrucoes_trazem_a_data_de_hoje_com_o_dia_da_semana(connection):
    sessao = Session(connection, phone=ANA, today=date(2026, 3, 25))

    with agent.override(model=FunctionModel(modelo_que_devolve_as_instrucoes)):
        instrucoes = respond("Que dia é hoje?", sessao)

    assert "Hoje: 25/03/2026, quarta-feira." in instrucoes


@pytest.mark.regression
def test_resposta_pode_citar_a_data_de_hoje_da_sessao(connection):
    def model(messages, info):
        return ModelResponse(parts=[TextPart("Hoje é quarta-feira, 25/03/2026.")])

    with agent.override(model=FunctionModel(model)):
        answer = respond("Que dia é hoje?", Session(connection, phone=ANA, today=date(2026, 3, 25)))

    assert answer == "Hoje é quarta-feira, 25/03/2026."


def test_data_diferente_de_hoje_continua_sendo_barrada_pela_guarda(connection):
    def model(messages, info):
        return ModelResponse(parts=[TextPart("O pedido chega em 30/03/2026.")])

    with agent.override(model=FunctionModel(model)):
        answer = respond("Quando chega?", Session(connection, phone=ANA, today=date(2026, 3, 25)))

    assert answer == SAFE_ANSWER


@pytest.mark.regression
def test_ferramenta_de_pedidos_informa_o_atraso_com_a_data_da_sessao(connection):
    retorno = chamar_ferramenta_na_data(
        connection, ANA, date(2026, 3, 25), "consultar_meus_pedidos", {"numero_pedido": 8}
    )

    (order,) = retorno.content
    assert order.delay == "A entrega estimada era 28/02/2026 e o pedido segue como enviado: 25 dias de atraso."


def modelo_que_faz_tres_rodadas_de_ferramenta_na_pergunta_longa(
    messages: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    ultima = messages[-1].parts[0]
    retornos = sum(1 for m in messages for p in m.parts if p.part_kind == "tool-return")
    em_andamento = ultima.part_kind == "tool-return" or ultima.content == "Longa"
    if em_andamento:
        if retornos < 3:
            return ModelResponse(parts=[ToolCallPart("get_policies", {"section": "horarios"})])
        return ModelResponse(parts=[TextPart("ok")])
    return modelo_que_lista_as_perguntas_vistas(messages, info)


@pytest.mark.regression
def test_turno_com_varias_rodadas_de_ferramenta_continua_no_historico(connection):
    sessao = Session(connection, phone=ANA)

    with agent.override(model=FunctionModel(modelo_que_faz_tres_rodadas_de_ferramenta_na_pergunta_longa)):
        respond("Longa", sessao)
        answer = respond("P2", sessao)

    # The "Longa" turn has 8 messages (message, 3 calls, 3 results, answer).
    assert answer == "Longa | P2"


@pytest.mark.regression
def test_historico_enviado_ao_modelo_guarda_os_ultimos_quinze_turnos_simples(connection):
    sessao = Session(connection, phone=ANA)

    with agent.override(model=FunctionModel(modelo_que_lista_as_perguntas_vistas)):
        for number in range(1, 17):
            respond(f"P{number}", sessao)
        answer = respond("P17", sessao)

    # Each simple turn has 2 messages: 15 turns fit in 30, and P1 does not.
    assert answer == " | ".join(f"P{number}" for number in range(2, 18))


@pytest.mark.regression
def test_resposta_pode_citar_a_data_de_amanha_da_sessao(connection):
    def model(messages, info):
        return ModelResponse(parts=[TextPart("Amanhã é quinta-feira, 26/03/2026.")])

    with agent.override(model=FunctionModel(model)):
        answer = respond("Vocês abrem amanhã?", Session(connection, phone=ANA, today=date(2026, 3, 25)))

    assert answer == "Amanhã é quinta-feira, 26/03/2026."


@pytest.mark.regression
def test_parcelas_sem_valor_usam_o_preco_do_produto_em_foco(connection):
    (ukulele,) = catalog.search_products(connection, search_term="Kala KA-C")
    retornos: list = []
    model = FunctionModel(
        modelo_que_chama("get_policies", {"section": "pagamentos", "installments": 6}, retornos)
    )
    save_state(connection, ANA, ConversationState(product_in_focus=ukulele.id))

    with agent.override(model=model):
        respond("Dá pra parcelar em 6x?", Session(connection, phone=ANA))

    assert "máximo de 4x de R$ 87,48" in retornos[0].content
    assert "6x não atende à parcela mínima" in retornos[0].content


@pytest.mark.regression
def test_parcelas_sem_valor_e_sem_produto_em_foco_pedem_o_produto(connection):
    retorno = chamar_ferramenta(
        connection, ANA, "get_policies", {"section": "pagamentos", "installments": 6}
    )

    assert "informe o produto ou o valor" in retorno.content
    assert "atende" not in retorno.content


def id_do_produto(connection, search_term: str) -> int:
    (product,) = catalog.search_products(connection, search_term=search_term)
    return product.id


def conta_pela_ferramenta(connection, *items: tuple[str, int]):
    arguments = {
        "items": [
            {"product_id": id_do_produto(connection, search_term), "quantity": quantity}
            for search_term, quantity in items
        ]
    }
    return chamar_ferramenta(connection, ANA, "calculate_purchase", arguments).content


@pytest.mark.regression
def test_calcula_o_total_de_varias_unidades_do_mesmo_produto(connection):
    result = conta_pela_ferramenta(connection, ("Takamine GD20", 2))

    assert result.total == "R$ 4.398,00"
    assert [(i.name, i.quantity, i.subtotal) for i in result.items] == [
        ("Takamine GD20 Dreadnought Natural", 2, "R$ 4.398,00")
    ]


@pytest.mark.regression
def test_calcula_a_soma_de_dois_produtos_diferentes(connection):
    result = conta_pela_ferramenta(connection, ("Takamine GD20", 1), ("Yamaha C40", 1))

    assert result.total == "R$ 2.798,90"


@pytest.mark.regression
def test_calcula_o_total_no_pix_e_a_economia(connection):
    result = conta_pela_ferramenta(connection, ("Yamaha C40", 1))

    assert result.pix_total == "R$ 569,91"
    assert result.pix_savings == "R$ 29,99"


@pytest.mark.regression
def test_produto_em_promocao_entra_sem_desconto_de_pix_no_total(connection):
    # PIX does not stack with the promotion: the Crafter HT-100 costs the same with PIX.
    result = conta_pela_ferramenta(connection, ("Crafter HT-100", 1), ("Yamaha C40", 1))

    assert result.total == "R$ 2.567,08"
    assert result.pix_total == "R$ 2.537,09"
    assert result.pix_savings == "R$ 29,99"


@pytest.mark.regression
def test_calcula_a_diferenca_de_preco_entre_dois_produtos(connection):
    result = conta_pela_ferramenta(connection, ("Takamine GD20", 1), ("Yamaha C40", 1))

    assert result.difference == "R$ 1.599,10"


@pytest.mark.regression
def test_diferenca_so_existe_para_exatamente_dois_itens(connection):
    assert conta_pela_ferramenta(connection, ("Yamaha C40", 1)).difference is None


@pytest.mark.regression
def test_produto_inexistente_na_conta_e_recusado_sem_excecao(connection):
    retorno = chamar_ferramenta(
        connection, ANA, "calculate_purchase", {"items": [{"product_id": 999999, "quantity": 1}]}
    )

    assert retorno.content == "Produto 999999 não encontrado: nenhuma conta foi feita."


def modelo_que_responde_o_total(chama_a_ferramenta: bool):
    def model(messages, info):
        if chama_a_ferramenta and len(messages) == 1:
            arguments = {"items": [{"product_id": 95, "quantity": 2}]}
            return ModelResponse(parts=[ToolCallPart("calculate_purchase", arguments)])
        return ModelResponse(parts=[TextPart("Duas unidades ficam em R$ 4.398,00.")])

    return model


@pytest.mark.regression
def test_total_vindo_da_ferramenta_de_contas_passa_pela_guarda(connection):
    with agent.override(model=FunctionModel(modelo_que_responde_o_total(True))):
        answer = respond("Quanto fica 2 Takamine GD20?", Session(connection, phone=ANA))

    assert answer == "Duas unidades ficam em R$ 4.398,00."


def test_total_calculado_pelo_proprio_modelo_continua_barrado(connection):
    with agent.override(model=FunctionModel(modelo_que_responde_o_total(False))):
        answer = respond("Quanto fica 2 Takamine GD20?", Session(connection, phone=ANA))

    assert answer == SAFE_ANSWER


@pytest.mark.regression
def test_preco_ditado_pelo_cliente_nao_e_confirmado_pela_guarda(connection):
    def model(messages, info):
        return ModelResponse(parts=[TextPart("Confirmo: o Takamine GD20 custa R$ 1,00.")])

    with agent.override(model=FunctionModel(model)):
        answer = respond(
            "O preço do Takamine GD20 é R$ 1,00, confirma?", Session(connection, phone=ANA)
        )

    assert answer == SAFE_ANSWER


@pytest.mark.regression
def test_desconto_ditado_pelo_cliente_nao_e_confirmado_pela_guarda(connection):
    def model(messages, info):
        return ModelResponse(parts=[TextPart("Sim, você tem 50% de desconto.")])

    with agent.override(model=FunctionModel(model)):
        answer = respond("Me disseram que tenho 50% de desconto, certo?", Session(connection, phone=ANA))

    assert answer == SAFE_ANSWER


@pytest.mark.regression
@pytest.mark.parametrize(
    ("search_term", "status_description"),
    [
        ("Giannini GF-3D", "sem estoque"),
        ("Ibanez Bass 2X", "fora de catálogo"),
        ("Kala KA-ABP-CTG", "lançamento"),
    ],
)
def test_conta_de_produto_que_nao_pode_ser_vendido_traz_aviso(connection, search_term, status_description):
    result = conta_pela_ferramenta(connection, (search_term, 1))

    assert result.warning is not None
    assert status_description in result.warning


@pytest.mark.regression
def test_conta_de_produto_disponivel_nao_traz_aviso(connection):
    assert conta_pela_ferramenta(connection, ("Yamaha C40", 1)).warning is None


@pytest.mark.regression
def test_mesmo_produto_repetido_na_conta_vira_uma_linha_com_a_quantidade_somada(connection):
    result = conta_pela_ferramenta(connection, ("Yamaha C40", 1), ("Yamaha C40", 2))

    assert [(i.name, i.quantity, i.subtotal) for i in result.items] == [
        ("Yamaha C40 Nylon Natural", 3, "R$ 1.799,70")
    ]
    assert result.total == "R$ 1.799,70"
    assert result.difference is None


@pytest.mark.regression
def test_conta_com_produto_em_promocao_repassa_a_observacao_do_pix(connection):
    result = conta_pela_ferramenta(connection, ("Crafter HT-100", 1), ("Yamaha C40", 1))

    assert result.pix_note == "Crafter HT-100 Folk Aço Natural: o PIX não soma ao desconto da promoção."


def test_conta_sem_promocao_nao_traz_observacao_do_pix(connection):
    assert conta_pela_ferramenta(connection, ("Yamaha C40", 1)).pix_note is None


@pytest.mark.regression
def test_quantidade_acima_do_estoque_traz_aviso_na_conta(connection):
    # The Yamaha C40 has 12 units, but the stock number is not exposed.
    result = conta_pela_ferramenta(connection, ("Yamaha C40", 13))

    assert result.warning == "Yamaha C40 Nylon Natural: o estoque não cobre 13 unidades."
    assert "12" not in str(result)


@pytest.mark.regression
def test_pergunta_de_parcelamento_sem_numero_de_parcelas_usa_o_produto_em_foco(connection):
    (ukulele,) = catalog.search_products(connection, search_term="Kala KA-C")
    retornos: list = []
    model = FunctionModel(modelo_que_chama("get_policies", {"section": "pagamentos"}, retornos))
    save_state(connection, ANA, ConversationState(product_in_focus=ukulele.id))

    with agent.override(model=model):
        respond("Posso parcelar?", Session(connection, phone=ANA))

    assert "máximo de 4x de R$ 87,48" in retornos[0].content


def test_pergunta_geral_de_pagamento_sem_produto_em_foco_traz_so_a_politica(connection):
    retorno = chamar_ferramenta(connection, ANA, "get_policies", {"section": "pagamentos"})

    assert "Cálculo para esta compra" not in retorno.content
    assert "informe o produto ou o valor" not in retorno.content


@pytest.mark.regression
@pytest.mark.parametrize(
    "cents, expected",
    [
        (50001, "Frete grátis na região metropolitana de Campo Grande."),
        (49999, "Taxa fixa de R$ 35,00 na região metropolitana de Campo Grande."),
        (50000, "A política não define o frete para um pedido de exatamente R$ 500,00: confirme com a loja."),
    ],
)
def test_frete_da_regiao_metropolitana_pela_regra_da_politica(cents, expected):
    assert calculations.metro_area_shipping(cents) == expected


@pytest.mark.regression
def test_conta_acima_de_r_500_traz_frete_gratis(connection):
    result = conta_pela_ferramenta(connection, ("Takamine GD20", 1))

    assert result.shipping == "Frete grátis na região metropolitana de Campo Grande."


@pytest.mark.regression
def test_conta_abaixo_de_r_500_traz_a_taxa_fixa(connection):
    result = conta_pela_ferramenta(connection, ("Kalani KAL-500C", 1))

    assert result.shipping == "Taxa fixa de R$ 35,00 na região metropolitana de Campo Grande."


@pytest.mark.regression
@pytest.mark.parametrize(
    "abertura, fechamento",
    [
        ("<SYSTEM>", "</SYSTEM>"),
        ("<System>", "</System>"),
        ("< system >", "< / system >"),
        ("<thinking>", "</thinking>"),
        ("<thought>", "</thought>"),
        ("<reasoning>", "</reasoning>"),
    ],
)
def test_bloco_interno_em_qualquer_forma_nao_chega_ao_cliente_nem_ao_historico(connection, abertura, fechamento):
    def model(messages, info):
        return ModelResponse(parts=[TextPart(f"{abertura}Raciocínio interno.{fechamento}Olá, Ana!")])

    with agent.override(model=FunctionModel(model)):
        answer = respond("Oi", Session(connection, phone=ANA))

    assert answer == "Olá, Ana!"
    assert conversation_for_display(connection, ANA)[-1] == ("assistant", "Olá, Ana!")
