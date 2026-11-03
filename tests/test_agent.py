import asyncio
from datetime import date

import pytest
from pydantic_ai import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from src import calculos, catalog
from src.agent import RESPOSTA_SEGURA, SEM_CADASTRO, Sessao, agente, responder
from src.database import conectar
from src.interests import listar_pendentes, registrar
from src.load_data import ler_csv
from src.memory import Estado, carregar_estado, exibir_conversa, salvar_estado
from src.restock import repor_estoque
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


@pytest.mark.regressao
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


def modelo_que_lista_as_promocoes_ativas(mensagens: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    if len(mensagens) == 1:
        return ModelResponse(parts=[ToolCallPart("buscar_produtos", {"somente_promocao": True})])
    produtos = mensagens[-1].parts[0].content
    linhas = [f"{p.nome}: {p.preco}, {p.desconto_percentual}%, {p.preco_final}" for p in produtos]
    return ModelResponse(parts=[TextPart("\n".join(linhas))])


def test_agente_lista_os_4_produtos_em_promocao_com_preco_original_percentual_e_preco_final(conexao):
    with agente.override(model=FunctionModel(modelo_que_lista_as_promocoes_ativas)):
        resposta = responder("Quais produtos estão em promoção agora?", Sessao(conexao))

    assert len(resposta.splitlines()) == 4
    assert "Crafter HT-100 Folk Aço Natural: R$ 2.399,00, 18%, R$ 1.967,18" in resposta


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
    """Calls the tool once and stores the result, without depending on its text."""

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
    # Order 5 belongs to customer 5.
    retorno = chamar_ferramenta(conexao, ANA, "consultar_meus_pedidos", {"numero_pedido": 5})

    assert retorno.content == []


@pytest.mark.regressao
def test_mensagem_nao_consegue_trocar_o_cliente_consultado(conexao):
    # Order 4 belongs to customer 1; the session belongs to customer 2.
    retorno = chamar_ferramenta(
        conexao, ANA, "consultar_meus_pedidos", {"numero_pedido": 4, "customer_id": 1}
    )

    # The extra argument is rejected and no order is looked up.
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

    assert "Ana" in instrucoes
    assert "Carolina" not in instrucoes
    assert "Ferreira" not in instrucoes


def test_instrucoes_nao_expoem_dados_pessoais_alem_do_nome(conexao):
    sessao = Sessao(conexao, telefone=ANA)

    with agente.override(model=FunctionModel(modelo_que_devolve_as_instrucoes)):
        instrucoes = responder("Oi!", sessao)

    # The source of the values is the CSV, not the code under test.
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
@pytest.mark.regressao
def test_ferramentas_recusam_argumentos_fora_da_faixa(conexao, ferramenta, argumentos):
    sessao = Sessao(conexao, telefone="(67) 99654-7821")

    with agente.override(model=FunctionModel(modelo_que_envia_argumentos(ferramenta, argumentos))):
        resposta = responder("Teste", sessao)

    assert resposta == "argumento recusado"


@pytest.mark.regressao
def test_modelo_recebe_a_situacao_traduzida_e_nao_o_status_cru(conexao):
    retorno = chamar_ferramenta(conexao, ANA, "consultar_meus_pedidos", {"numero_pedido": 8})

    visto_pelo_modelo = retorno.model_response_str()
    assert "enviado" in visto_pelo_modelo
    assert "shipped" not in visto_pelo_modelo


def modelo_que_lista_as_perguntas_vistas(
    mensagens: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    perguntas = [
        parte.content
        for mensagem in mensagens
        for parte in mensagem.parts
        if parte.part_kind == "user-prompt"
    ]
    return ModelResponse(parts=[TextPart(" | ".join(perguntas))])


def test_segunda_mensagem_chega_ao_modelo_junto_com_a_primeira(conexao):
    sessao = Sessao(conexao, telefone=ANA)

    with agente.override(model=FunctionModel(modelo_que_lista_as_perguntas_vistas)):
        responder("Quero um violão", sessao)
        resposta = responder("E o mais barato?", sessao)

    assert resposta == "Quero um violão | E o mais barato?"


def test_nova_sessao_com_o_mesmo_telefone_recupera_a_conversa(conexao, tmp_path):
    with agente.override(model=FunctionModel(modelo_que_lista_as_perguntas_vistas)):
        responder("Quero um violão", Sessao(conexao, telefone=ANA))

        # Another connection to the same file is equivalent to restarting the application.
        nova = conectar(tmp_path / "teste.db")
        try:
            resposta = responder("Chegou?", Sessao(nova, telefone="67996547821"))
        finally:
            nova.close()

    assert resposta == "Quero um violão | Chegou?"


def test_telefone_diferente_nao_recebe_o_historico_de_outra_pessoa(conexao):
    with agente.override(model=FunctionModel(modelo_que_lista_as_perguntas_vistas)):
        responder("Quero um violão", Sessao(conexao, telefone=ANA))
        resposta = responder("Oi", Sessao(conexao, telefone="(67) 90000-0000"))

    assert resposta == "Oi"


def test_sessao_sem_telefone_valido_nao_guarda_conversa(conexao):
    with agente.override(model=FunctionModel(modelo_que_lista_as_perguntas_vistas)):
        responder("Quero um violão", Sessao(conexao, telefone="123"))
        resposta = responder("Oi", Sessao(conexao, telefone="123"))

    assert resposta == "Oi"


def modelo_que_consulta_o_horario_e_lista_as_perguntas(
    mensagens: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    if mensagens[-1].parts[0].part_kind == "user-prompt":
        return ModelResponse(
            parts=[ToolCallPart("consultar_politicas", {"secao": "horarios"})]
        )
    return modelo_que_lista_as_perguntas_vistas(mensagens, info)


@pytest.mark.regressao
def test_historico_enviado_ao_modelo_nao_separa_chamada_de_ferramenta_do_retorno(conexao, monkeypatch):
    # A small limit forces the cut in the middle of a turn with a tool.
    monkeypatch.setattr("src.memory.MAX_MENSAGENS_NO_HISTORICO", 7)
    sessao = Sessao(conexao, telefone=ANA)

    with agente.override(
        model=FunctionModel(modelo_que_consulta_o_horario_e_lista_as_perguntas)
    ):
        for pergunta in ("P1", "P2", "P3"):
            responder(pergunta, sessao)
        resposta = responder("P4", sessao)

    # Each turn with a tool has 4 messages: only one whole turn would fit in 7.
    assert resposta == "P3 | P4"


def modelo_que_repete_um_preco_de_turno_anterior(
    mensagens: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    ultima = mensagens[-1].parts[0]
    if ultima.part_kind == "user-prompt" and ultima.content == "Quanto custa?":
        return ModelResponse(
            parts=[ToolCallPart("buscar_produtos", {"termo": "Takamine GD20"})]
        )
    if ultima.part_kind == "tool-return":
        return ModelResponse(parts=[TextPart("Custa R$ 2.199,00")])
    return ModelResponse(parts=[TextPart("Continua R$ 2.199,00")])


@pytest.mark.regressao
def test_guarda_nao_aceita_valor_citado_apenas_em_turno_anterior(conexao):
    sessao = Sessao(conexao, telefone=ANA)

    with agente.override(model=FunctionModel(modelo_que_repete_um_preco_de_turno_anterior)):
        primeira = responder("Quanto custa?", sessao)
        segunda = responder("E agora?", sessao)

    assert primeira == "Custa R$ 2.199,00"
    assert segunda == RESPOSTA_SEGURA


def modelo_que_inventa_um_preco_ate_a_pergunta_seguinte(
    mensagens: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    # The correction requested by the guardrail also arrives as a customer message, so
    # the model insists while the next question has not appeared yet.
    perguntas = [
        parte.content
        for mensagem in mensagens
        for parte in mensagem.parts
        if parte.part_kind == "user-prompt"
    ]
    if "Preço do violão?" in perguntas and "Oi" not in perguntas:
        return ModelResponse(parts=[TextPart("Custa R$ 9,99")])
    return modelo_que_lista_as_perguntas_vistas(mensagens, info)


def test_resposta_segura_tambem_entra_no_historico(conexao):
    sessao = Sessao(conexao, telefone=ANA)

    with agente.override(model=FunctionModel(modelo_que_inventa_um_preco_ate_a_pergunta_seguinte)):
        segura = responder("Preço do violão?", sessao)
        resposta = responder("Oi", sessao)

    assert segura == RESPOSTA_SEGURA
    assert resposta == "Preço do violão? | Oi"


@pytest.mark.regressao
def test_historico_corrompido_e_ignorado_e_o_atendimento_continua(conexao):
    sessao = Sessao(conexao, telefone=ANA)

    with agente.override(model=FunctionModel(modelo_que_lista_as_perguntas_vistas)):
        responder("Quero um violão", sessao)
        conexao.execute("UPDATE messages SET content = 'não é json'")
        resposta = responder("Oi", sessao)

    assert resposta == "Oi"


def modelo_que_busca_um_produto_e_depois_mostra_as_instrucoes(
    mensagens: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    ultima = mensagens[-1].parts[0]
    if ultima.part_kind == "user-prompt" and ultima.content == "Tem o Giannini?":
        return ModelResponse(
            parts=[ToolCallPart("buscar_produtos", {"termo": "Giannini GF-3D"})]
        )
    if ultima.part_kind == "tool-return":
        return ModelResponse(parts=[TextPart("ok")])
    return ModelResponse(parts=[TextPart(info.instructions or "")])


def test_produto_unico_encontrado_fica_em_foco_nas_mensagens_seguintes(conexao):
    sessao = Sessao(conexao, telefone=ANA)

    with agente.override(
        model=FunctionModel(modelo_que_busca_um_produto_e_depois_mostra_as_instrucoes)
    ):
        responder("Tem o Giannini?", sessao)
        instrucoes = responder("E o preço?", sessao)

    assert "Produto em foco: Giannini GF-3D" in instrucoes


def modelo_que_consulta_o_pedido_8_e_depois_mostra_as_instrucoes(
    mensagens: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    ultima = mensagens[-1].parts[0]
    if ultima.part_kind == "user-prompt" and ultima.content == "Cadê meu pedido?":
        return ModelResponse(
            parts=[ToolCallPart("consultar_meus_pedidos", {"numero_pedido": 8})]
        )
    if ultima.part_kind == "tool-return":
        return ModelResponse(parts=[TextPart("ok")])
    return ModelResponse(parts=[TextPart(info.instructions or "")])


def test_pedido_consultado_fica_em_analise_nas_mensagens_seguintes(conexao):
    sessao = Sessao(conexao, telefone=ANA)

    with agente.override(
        model=FunctionModel(modelo_que_consulta_o_pedido_8_e_depois_mostra_as_instrucoes)
    ):
        responder("Cadê meu pedido?", sessao)
        instrucoes = responder("E o rastreio?", sessao)

    assert "Pedido em análise: 8" in instrucoes


def test_estado_sobrevive_ao_reinicio_e_nao_vaza_para_outro_telefone(conexao, tmp_path):
    modelo = FunctionModel(modelo_que_busca_um_produto_e_depois_mostra_as_instrucoes)
    with agente.override(model=modelo):
        responder("Tem o Giannini?", Sessao(conexao, telefone=ANA))

        nova = conectar(tmp_path / "teste.db")
        try:
            da_ana = responder("E o preço?", Sessao(nova, telefone="67996547821"))
            de_outra_pessoa = responder("E o preço?", Sessao(nova, telefone="(67) 90000-0000"))
        finally:
            nova.close()

    assert "Produto em foco: Giannini GF-3D" in da_ana
    assert "Produto em foco" not in de_outra_pessoa


def modelo_que_busca_varios_produtos_e_depois_mostra_as_instrucoes(
    mensagens: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    ultima = mensagens[-1].parts[0]
    if ultima.part_kind == "user-prompt" and ultima.content == "Quais violões?":
        return ModelResponse(parts=[ToolCallPart("buscar_produtos", {"categoria": "Violões"})])
    if ultima.part_kind == "tool-return":
        return ModelResponse(parts=[TextPart("ok")])
    return ModelResponse(parts=[TextPart(info.instructions or "")])


def test_busca_com_varios_resultados_nao_define_produto_em_foco(conexao):
    sessao = Sessao(conexao, telefone=ANA)

    with agente.override(
        model=FunctionModel(modelo_que_busca_varios_produtos_e_depois_mostra_as_instrucoes)
    ):
        responder("Quais violões?", sessao)
        instrucoes = responder("E agora?", sessao)

    assert "Produto em foco" not in instrucoes


def test_conversa_antiga_e_exibida_so_com_o_que_o_cliente_viu(conexao):
    sessao = Sessao(conexao, telefone=ANA)

    with agente.override(
        model=FunctionModel(modelo_que_consulta_o_horario_e_lista_as_perguntas)
    ):
        responder("P1", sessao)
        responder("P2", sessao)

    assert exibir_conversa(conexao, "67996547821") == [
        ("user", "P1"),
        ("assistant", "P1"),
        ("user", "P2"),
        ("assistant", "P1 | P2"),
    ]


def modelo_que_inventa_um_preco_e_depois_se_corrige(
    mensagens: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    if len(mensagens) == 1:
        return ModelResponse(parts=[TextPart("Custa R$ 9,99")])
    return ModelResponse(parts=[TextPart("Não tenho esse valor")])


@pytest.mark.regressao
def test_conversa_antiga_nao_exibe_a_resposta_rejeitada_pela_guarda(conexao):
    with agente.override(model=FunctionModel(modelo_que_inventa_um_preco_e_depois_se_corrige)):
        responder("Preço?", Sessao(conexao, telefone=ANA))

    assert exibir_conversa(conexao, ANA) == [
        ("user", "Preço?"),
        ("assistant", "Não tenho esse valor"),
    ]


def test_telefone_sem_conversa_exibe_lista_vazia(conexao):
    assert exibir_conversa(conexao, "(67) 90000-0000") == []


LETICIA = "(67) 99789-0123"


def chamar_ferramenta_na_data(conexao, telefone, hoje, ferramenta, argumentos, mensagem="Teste"):
    capturados: list = []
    modelo = FunctionModel(modelo_que_chama(ferramenta, argumentos, capturados))
    with agente.override(model=modelo):
        responder(mensagem, Sessao(conexao, telefone=telefone, hoje=hoje))
    return capturados[0]


def test_ferramenta_de_devolucao_usa_o_pedido_do_cliente_e_a_data_da_sessao(conexao):
    retorno = chamar_ferramenta_na_data(
        conexao, LETICIA, date(2026, 2, 20), "avaliar_devolucao",
        {"numero_pedido": 7, "motivo": "arrependimento", "canal": "online"},
        mensagem="Comprei online e quero devolver o pedido 7 por arrependimento",
    )

    assert retorno.content.resultado == "dentro_do_prazo"
    assert retorno.content.regras[0].prazo_ate == "24/02/2026"


@pytest.mark.regressao
def test_canal_que_o_cliente_nao_citou_e_ignorado_e_o_veredito_pede_o_canal(conexao):
    # The model assumed "online"; the customer only gave the reason.
    retorno = chamar_ferramenta_na_data(
        conexao, LETICIA, date(2026, 2, 20), "avaliar_devolucao",
        {"numero_pedido": 7, "motivo": "arrependimento", "canal": "online"},
        mensagem="Quero devolver o pedido 7 por arrependimento",
    )

    assert retorno.content.resultado == "faltam_dados"


@pytest.mark.regressao
def test_canal_diferente_do_que_o_cliente_citou_tambem_e_ignorado(conexao):
    retorno = chamar_ferramenta_na_data(
        conexao, LETICIA, date(2026, 2, 20), "avaliar_devolucao",
        {"numero_pedido": 7, "motivo": "arrependimento", "canal": "online"},
        mensagem="Comprei presencialmente e quero devolver o pedido 7 por arrependimento",
    )

    assert retorno.content.resultado == "faltam_dados"


def test_devolucao_de_pedido_de_outro_cliente_volta_como_nao_encontrado(conexao):
    # Order 7 belongs to customer 14; the session belongs to customer 2.
    retorno = chamar_ferramenta(
        conexao, ANA, "avaliar_devolucao", {"numero_pedido": 7, "motivo": "defeito"}
    )

    assert retorno.content.resultado == "pedido_nao_encontrado"


def test_devolucao_sem_cadastro_explica_que_pedidos_exigem_telefone_cadastrado(conexao):
    retorno = chamar_ferramenta(
        conexao, "(67) 90000-0000", "avaliar_devolucao", {"numero_pedido": 7, "motivo": "defeito"}
    )

    assert retorno.content == SEM_CADASTRO


@pytest.mark.parametrize(
    "argumentos",
    [
        {"numero_pedido": 7, "motivo": "fiquei com dó"},
        {"numero_pedido": 7, "motivo": "defeito", "customer_id": 14},
    ],
)
def test_devolucao_recusa_motivo_desconhecido_e_cliente_como_argumento(conexao, argumentos):
    retorno = chamar_ferramenta(conexao, ANA, "avaliar_devolucao", argumentos)

    assert retorno.outcome == "retried"


def modelo_que_avalia_a_devolucao_e_depois_mostra_as_instrucoes(argumentos: dict):
    def modelo(mensagens: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        ultima = mensagens[-1].parts[0]
        if ultima.part_kind == "user-prompt" and ultima.content == "Quero devolver":
            return ModelResponse(parts=[ToolCallPart("avaliar_devolucao", argumentos)])
        if ultima.part_kind == "tool-return":
            return ModelResponse(parts=[TextPart("ok")])
        return ModelResponse(parts=[TextPart(info.instructions or "")])

    return modelo


@pytest.mark.regressao
def test_canal_nao_informado_nao_deixa_pergunta_gravada_para_o_proximo_assunto(conexao):
    sessao = Sessao(conexao, telefone=LETICIA)
    modelo = modelo_que_avalia_a_devolucao_e_depois_mostra_as_instrucoes(
        {"numero_pedido": 7, "motivo": "arrependimento"}
    )

    with agente.override(model=FunctionModel(modelo)):
        responder("Quero devolver", sessao)
        instrucoes = responder("Foi online", sessao)

    # Tom's question stays only in the history; the state keeps only the order under review.
    assert "Pergunta pendente" not in instrucoes
    assert "Pedido em análise: 7" in instrucoes


@pytest.mark.parametrize("argumentos", [
    {"numero_pedido": 7, "motivo": "arrependimento"},
    {"numero_pedido": 7, "motivo": "arrependimento", "canal": "presencial"},
    {"numero_pedido": 999, "motivo": "arrependimento"},
])
@pytest.mark.regressao
def test_pedido_que_nao_e_do_cliente_nao_vira_pedido_em_analise(conexao, argumentos):
    # Order 7 belongs to customer 14; the session belongs to customer 2 (Ana). Order 999 does not exist.
    sessao = Sessao(conexao, telefone=ANA)
    modelo = modelo_que_avalia_a_devolucao_e_depois_mostra_as_instrucoes(argumentos)

    with agente.override(model=FunctionModel(modelo)):
        responder("Quero devolver", sessao)
        instrucoes = responder("Mostra o contexto", sessao)

    assert "Pedido em análise" not in instrucoes


def test_instrucoes_trazem_os_interesses_pendentes_so_do_telefone_da_sessao(conexao):
    registrar(conexao, ANA, 96)
    registrar(conexao, "(67) 91111-2222", 90)

    with agente.override(model=FunctionModel(modelo_que_devolve_as_instrucoes)):
        da_ana = responder("Oi!", Sessao(conexao, telefone=ANA))
        de_outro = responder("Oi!", Sessao(conexao, telefone="(67) 93333-4444"))

    assert "Giannini GF-3D" in da_ana
    assert "Crafter HT-100" not in da_ana
    assert "Giannini GF-3D" not in de_outro
    assert "Crafter HT-100" not in de_outro


def test_ferramenta_registra_o_interesse_do_telefone_da_sessao_e_define_o_foco(conexao):
    sessao = Sessao(conexao, telefone=ANA)
    capturados: list = []

    with agente.override(
        model=FunctionModel(modelo_que_chama("registrar_interesse", {"product_id": 96}, capturados))
    ):
        responder("Quero acompanhar esse violão", sessao)

    assert listar_pendentes(conexao, ANA) == ["Giannini GF-3D Dreadnought Sunburst"]
    assert sessao.estado.produto_em_foco == 96
    assert "não reserva o produto" in capturados[0].content


@pytest.mark.regressao
def test_mensagem_nao_consegue_registrar_interesse_em_outro_telefone(conexao):
    retorno = chamar_ferramenta(
        conexao, ANA, "registrar_interesse", {"product_id": 96, "phone": "67911112222"}
    )

    assert retorno.outcome == "retried"
    assert listar_pendentes(conexao, "67911112222") == []
    assert listar_pendentes(conexao, ANA) == []


def modelo_que_retoma_o_interesse(mensagens: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Reads the interest's name in the context and looks up the catalog, as the prompt says."""
    if len(mensagens) == 1:
        nome = info.instructions.split("Interesses pendentes: ")[1].split(".")[0].split(";")[0]
        return ModelResponse(parts=[ToolCallPart("buscar_produtos", {"termo": nome})])
    (produto,) = mensagens[-1].parts[0].content
    return ModelResponse(parts=[TextPart(f"{produto.nome}: {produto.disponibilidade}")])


def test_chegou_o_violao_sem_reposicao_informa_que_continua_indisponivel(conexao):
    registrar(conexao, ANA, 96)

    with agente.override(model=FunctionModel(modelo_que_retoma_o_interesse)):
        resposta = responder("Chegou o violão?", Sessao(conexao, telefone=ANA))

    assert resposta == "Giannini GF-3D Dreadnought Sunburst: indisponivel"


def test_chegou_o_violao_apos_reposicao_informa_a_disponibilidade(conexao):
    registrar(conexao, ANA, 96)
    repor_estoque(conexao, 96, 5)

    with agente.override(model=FunctionModel(modelo_que_retoma_o_interesse)):
        resposta = responder("Chegou o violão?", Sessao(conexao, telefone=ANA))

    assert resposta == "Giannini GF-3D Dreadnought Sunburst: disponivel"


def test_sem_interesse_salvo_o_contexto_diz_que_nao_ha_nenhum(conexao):
    registrar(conexao, "(67) 91111-2222", 96)

    with agente.override(model=FunctionModel(modelo_que_devolve_as_instrucoes)):
        instrucoes = responder("Chegou o violão?", Sessao(conexao, telefone=ANA))

    assert "Interesses pendentes: nenhum" in instrucoes
    assert "Giannini" not in instrucoes


def test_busca_com_varios_produtos_limpa_o_foco(conexao):
    salvar_estado(conexao, ANA, Estado(produto_em_foco=96))
    capturados: list = []

    with agente.override(
        model=FunctionModel(modelo_que_chama("buscar_produtos", {"categoria": "Violões"}, capturados))
    ):
        responder("Quais violões vocês têm?", Sessao(conexao, telefone=ANA))

    assert carregar_estado(conexao, ANA).produto_em_foco is None


def test_busca_sem_resultado_limpa_o_foco(conexao):
    salvar_estado(conexao, ANA, Estado(produto_em_foco=96))
    capturados: list = []

    with agente.override(
        model=FunctionModel(modelo_que_chama("buscar_produtos", {"termo": "saxofone"}, capturados))
    ):
        responder("Tem saxofone?", Sessao(conexao, telefone=ANA))

    assert carregar_estado(conexao, ANA).produto_em_foco is None


def test_contexto_mostra_os_5_interesses_mais_recentes_e_avisa_do_restante(conexao):
    ids = [linha[0] for linha in conexao.execute(
        "SELECT product_id FROM products WHERE status = 'active' ORDER BY product_id LIMIT 6"
    )]
    nomes = [catalog.nome_do_produto(conexao, i) for i in ids]
    for produto in ids:
        registrar(conexao, ANA, produto)

    with agente.override(model=FunctionModel(modelo_que_devolve_as_instrucoes)):
        instrucoes = responder("Chegou?", Sessao(conexao, telefone=ANA))

    assert nomes[0] not in instrucoes
    assert all(nome in instrucoes for nome in nomes[1:])
    assert "e mais 1" in instrucoes


def test_ferramenta_registra_o_encaminhamento_do_telefone_da_sessao(conexao):
    retorno = chamar_ferramenta(
        conexao,
        ANA,
        "encaminhar_para_atendente",
        {"motivo": "reclamacao", "resumo": "Violão chegou com defeito no braço."},
    )

    linhas = [tuple(l) for l in conexao.execute("SELECT phone, reason, summary FROM handoffs")]
    assert linhas == [("67996547821", "reclamacao", "Violão chegou com defeito no braço.")]
    assert "24 horas úteis" in retorno.content


def test_encaminhamento_sem_telefone_valido_explica_e_nao_grava(conexao):
    retorno = chamar_ferramenta(
        conexao, None, "encaminhar_para_atendente", {"motivo": "reclamacao", "resumo": "Defeito."}
    )

    assert "não foi possível identificar o telefone" in retorno.content.lower()
    assert "sobre_a_loja" in retorno.content
    assert conexao.execute("SELECT COUNT(*) FROM handoffs").fetchone()[0] == 0


@pytest.mark.regressao
def test_mensagem_nao_consegue_encaminhar_em_nome_de_outro_telefone(conexao):
    retorno = chamar_ferramenta(
        conexao,
        ANA,
        "encaminhar_para_atendente",
        {"motivo": "reclamacao", "resumo": "Defeito.", "phone": "67911112222"},
    )

    assert retorno.outcome == "retried"
    assert conexao.execute("SELECT COUNT(*) FROM handoffs").fetchone()[0] == 0


def test_motivo_desconhecido_e_recusado_pela_ferramenta(conexao):
    retorno = chamar_ferramenta(
        conexao, ANA, "encaminhar_para_atendente", {"motivo": "fofoca", "resumo": "Defeito."}
    )

    assert retorno.outcome == "retried"
    assert conexao.execute("SELECT COUNT(*) FROM handoffs").fetchone()[0] == 0


def modelo_que_sempre_inventa_um_preco(mensagens: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    return ModelResponse(parts=[TextPart("Custa R$ 9,99")])


def test_resposta_segura_registra_o_encaminhamento_e_informa_o_prazo(conexao):
    with agente.override(model=FunctionModel(modelo_que_sempre_inventa_um_preco)):
        resposta = responder("Preço do violão?", Sessao(conexao, telefone=ANA))

    linhas = [tuple(l) for l in conexao.execute("SELECT phone, reason, summary FROM handoffs")]
    assert linhas == [("67996547821", "sem_resposta_segura", "Preço do violão?")]
    assert resposta == RESPOSTA_SEGURA
    assert "24 horas úteis" in resposta


def test_resposta_segura_sem_telefone_valido_explica_que_nao_foi_possivel_encaminhar(conexao):
    with agente.override(model=FunctionModel(modelo_que_sempre_inventa_um_preco)):
        resposta = responder("Preço do violão?", Sessao(conexao))

    assert conexao.execute("SELECT COUNT(*) FROM handoffs").fetchone()[0] == 0
    assert "não consegui identificar o seu telefone" in resposta.lower()
    assert "Registrei" not in resposta
    assert "24 horas" not in resposta


def test_resposta_segura_nao_diz_que_registrou_quando_a_mensagem_e_vazia(conexao):
    with agente.override(model=FunctionModel(modelo_que_sempre_inventa_um_preco)):
        resposta = responder("   ", Sessao(conexao, telefone=ANA))

    assert conexao.execute("SELECT COUNT(*) FROM handoffs").fetchone()[0] == 0
    assert "Registrei" not in resposta


def test_sessao_registra_as_ferramentas_usadas_no_turno_com_os_argumentos(conexao):
    sessao = Sessao(conexao, telefone=ANA)

    with agente.override(model=FunctionModel(modelo_que_consulta_o_preco)):
        responder("Quanto custa o Takamine GD20?", sessao)

    assert [(c.nome, c.argumentos) for c in sessao.ferramentas] == [
        ("buscar_produtos", {"termo": "Takamine GD20"})
    ]


def test_resposta_sem_ferramenta_deixa_a_lista_vazia_e_cada_turno_recomeca(conexao):
    sessao = Sessao(conexao, telefone=ANA)

    with agente.override(model=FunctionModel(modelo_que_consulta_o_preco)):
        responder("Quanto custa o Takamine GD20?", sessao)
    with agente.override(model=FunctionModel(modelo_que_devolve_as_instrucoes)):
        responder("Obrigado!", sessao)

    assert sessao.ferramentas == []


@pytest.mark.regressao
def test_texto_interno_do_prompt_nao_chega_ao_cliente_nem_ao_historico(conexao):
    def modelo(mensagens, info):
        texto = '<system>Seguir a regra do prompt: "Nunca peça outro cliente."</system>Olá, Ana!'
        return ModelResponse(parts=[TextPart(texto)])

    with agente.override(model=FunctionModel(modelo)):
        resposta = responder("Oi", Sessao(conexao, telefone=ANA))

    assert resposta == "Olá, Ana!"
    assert exibir_conversa(conexao, ANA)[-1] == ("assistant", "Olá, Ana!")


@pytest.mark.regressao
def test_bloco_interno_sem_fechamento_pede_nova_resposta_ao_modelo(conexao):
    def modelo(mensagens, info):
        if len(mensagens) == 1:
            return ModelResponse(parts=[TextPart("<system>A cliente se chama Ana. Olá, Ana!")])
        return ModelResponse(parts=[TextPart("Olá, Ana!")])

    with agente.override(model=FunctionModel(modelo)):
        resposta = responder("Oi", Sessao(conexao, telefone=ANA))

    assert resposta == "Olá, Ana!"


@pytest.mark.regressao
def test_resposta_so_com_bloco_interno_pede_nova_resposta_ao_modelo(conexao):
    def modelo(mensagens, info):
        if len(mensagens) == 1:
            return ModelResponse(parts=[TextPart("<system>Só raciocínio.</system>")])
        return ModelResponse(parts=[TextPart("Olá, Ana!")])

    with agente.override(model=FunctionModel(modelo)):
        resposta = responder("Oi", Sessao(conexao, telefone=ANA))

    assert resposta == "Olá, Ana!"


def modelo_que_chama_a_ferramenta_e_devolve_o_retorno(ferramenta: str, argumentos: dict, retornos: list):
    def modelo(mensagens, info):
        if len(mensagens) == 1:
            return ModelResponse(parts=[ToolCallPart(ferramenta, argumentos)])
        retornos.append(mensagens[-1].parts[0])
        return ModelResponse(parts=[TextPart("Não consegui calcular esse valor.")])

    return FunctionModel(modelo)


@pytest.mark.regressao
def test_valor_absurdo_e_recusado_pela_ferramenta_sem_derrubar_o_atendimento(conexao):
    retornos: list = []
    modelo = modelo_que_chama_a_ferramenta_e_devolve_o_retorno(
        "consultar_politicas", {"secao": "pagamentos", "valor": 1e33, "parcelas": 3}, retornos
    )

    with agente.override(model=modelo):
        resposta = responder("Em quantas vezes posso pagar R$ 999999999999999999999999999999999?", Sessao(conexao, telefone=ANA))

    assert resposta == "Não consegui calcular esse valor."
    assert retornos[0].outcome == "retried"


@pytest.mark.parametrize(
    ("ferramenta", "argumentos"),
    [
        ("consultar_meus_pedidos", {"numero_pedido": 10**30}),
        ("avaliar_devolucao", {"numero_pedido": 10**30, "motivo": "arrependimento", "canal": "online"}),
        ("registrar_interesse", {"product_id": 10**30}),
        ("buscar_produtos", {"preco_maximo": 1e33}),
    ],
)
@pytest.mark.regressao
def test_numero_fora_da_faixa_e_recusado_pela_ferramenta(conexao, ferramenta, argumentos):
    retornos: list = []
    modelo = modelo_que_chama_a_ferramenta_e_devolve_o_retorno(ferramenta, argumentos, retornos)

    with agente.override(model=modelo):
        resposta = responder("Oi", Sessao(conexao, telefone=ANA))

    assert resposta == "Não consegui calcular esse valor."
    assert retornos[0].outcome == "retried"


@pytest.mark.regressao
def test_ferramenta_de_busca_informa_se_atende_a_quantidade_pedida(conexao):
    retornos: list = []
    modelo = modelo_que_chama_a_ferramenta_e_devolve_o_retorno(
        "buscar_produtos", {"termo": "Yamaha C40", "quantidade": 10}, retornos
    )

    with agente.override(model=modelo):
        responder("Preciso de 10 Yamaha C40", Sessao(conexao, telefone=ANA))

    (produto,) = retornos[0].content
    assert produto.atende_quantidade is True
    assert not hasattr(produto, "estoque")


def modelo_que_responde_em_sequencia(*textos: str):
    def modelo(mensagens, info):
        indice = sum(1 for m in mensagens if isinstance(m, ModelResponse))
        return ModelResponse(parts=[TextPart(textos[min(indice, len(textos) - 1)])])

    return modelo


@pytest.mark.regressao
@pytest.mark.parametrize(
    "promessa",
    [
        "Assim que ele voltar, você já fica sabendo por aqui!",
        "Anotado! Eu te aviso se ele voltar.",
        "Pode deixar, avisaremos você quando chegar.",
        "Quando chegar, você será avisada.",
    ],
)
def test_promessa_de_aviso_pede_nova_resposta_ao_modelo(conexao, promessa):
    honesta = "Anotei o seu interesse. Isso não reserva o produto e não garante aviso."
    modelo = modelo_que_responde_em_sequencia(promessa, honesta)

    with agente.override(model=FunctionModel(modelo)):
        resposta = responder("Me avisa quando chegar?", Sessao(conexao, telefone=ANA))

    assert resposta == honesta


def test_aviso_de_que_nao_ha_garantia_de_aviso_passa_sem_nova_tentativa(conexao):
    honesta = "Anotei o seu interesse. Isso não reserva o produto e não garante aviso nem data."
    modelo = modelo_que_responde_em_sequencia(honesta, "NÃO DEVERIA CHEGAR")

    with agente.override(model=FunctionModel(modelo)):
        resposta = responder("Me avisa quando chegar?", Sessao(conexao, telefone=ANA))

    assert resposta == honesta


@pytest.mark.regressao
def test_recusa_explicita_de_avisar_passa_sem_nova_tentativa(conexao):
    honesta = "Anotei o interesse, mas não posso te avisar quando ele chegar. Consulte a loja."
    modelo = modelo_que_responde_em_sequencia(honesta, "NÃO DEVERIA CHEGAR")

    with agente.override(model=FunctionModel(modelo)):
        resposta = responder("Me avisa quando chegar?", Sessao(conexao, telefone=ANA))

    assert resposta == honesta


@pytest.mark.regressao
@pytest.mark.parametrize(
    "mensagem",
    [
        "Vi o preço no site e quero devolver o pedido 7 por arrependimento",
        "Os onlines de violão me deixaram em dúvida, quero devolver o pedido 7 por arrependimento",
    ],
)
def test_palavra_parecida_com_o_canal_nao_conta_como_canal_citado(conexao, mensagem):
    retorno = chamar_ferramenta_na_data(
        conexao, LETICIA, date(2026, 2, 20), "avaliar_devolucao",
        {"numero_pedido": 7, "motivo": "arrependimento", "canal": "online"},
        mensagem=mensagem,
    )

    assert retorno.content.resultado == "faltam_dados"


@pytest.mark.parametrize("mensagem", ["Comprei pelo site, quero devolver o pedido 7", "Foi ONLINE mesmo"])
def test_canal_dito_com_clareza_continua_valendo(conexao, mensagem):
    retorno = chamar_ferramenta_na_data(
        conexao, LETICIA, date(2026, 2, 20), "avaliar_devolucao",
        {"numero_pedido": 7, "motivo": "arrependimento", "canal": "online"},
        mensagem=mensagem,
    )

    assert retorno.content.resultado == "dentro_do_prazo"


@pytest.mark.regressao
def test_promessa_de_retorno_da_equipe_do_encaminhamento_passa_sem_nova_tentativa(conexao):
    legitima = "Registrei o seu caso. Entraremos em contato em até 24 horas úteis."
    modelo = modelo_que_responde_em_sequencia(legitima, "NÃO DEVERIA CHEGAR")

    with agente.override(model=FunctionModel(modelo)):
        resposta = responder("Quero falar com um atendente", Sessao(conexao, telefone=ANA))

    assert resposta == legitima


@pytest.mark.regressao
def test_instrucoes_trazem_a_data_de_hoje_com_o_dia_da_semana(conexao):
    sessao = Sessao(conexao, telefone=ANA, hoje=date(2026, 3, 25))

    with agente.override(model=FunctionModel(modelo_que_devolve_as_instrucoes)):
        instrucoes = responder("Que dia é hoje?", sessao)

    assert "Hoje: 25/03/2026, quarta-feira." in instrucoes


@pytest.mark.regressao
def test_resposta_pode_citar_a_data_de_hoje_da_sessao(conexao):
    def modelo(mensagens, info):
        return ModelResponse(parts=[TextPart("Hoje é quarta-feira, 25/03/2026.")])

    with agente.override(model=FunctionModel(modelo)):
        resposta = responder("Que dia é hoje?", Sessao(conexao, telefone=ANA, hoje=date(2026, 3, 25)))

    assert resposta == "Hoje é quarta-feira, 25/03/2026."


def test_data_diferente_de_hoje_continua_sendo_barrada_pela_guarda(conexao):
    def modelo(mensagens, info):
        return ModelResponse(parts=[TextPart("O pedido chega em 30/03/2026.")])

    with agente.override(model=FunctionModel(modelo)):
        resposta = responder("Quando chega?", Sessao(conexao, telefone=ANA, hoje=date(2026, 3, 25)))

    assert resposta == RESPOSTA_SEGURA


@pytest.mark.regressao
def test_ferramenta_de_pedidos_informa_o_atraso_com_a_data_da_sessao(conexao):
    retorno = chamar_ferramenta_na_data(
        conexao, ANA, date(2026, 3, 25), "consultar_meus_pedidos", {"numero_pedido": 8}
    )

    (pedido,) = retorno.content
    assert pedido.atraso == "A entrega estimada era 28/02/2026 e o pedido segue como enviado: 25 dias de atraso."


def modelo_que_faz_tres_rodadas_de_ferramenta_na_pergunta_longa(
    mensagens: list[ModelMessage], info: AgentInfo
) -> ModelResponse:
    ultima = mensagens[-1].parts[0]
    retornos = sum(1 for m in mensagens for p in m.parts if p.part_kind == "tool-return")
    em_andamento = ultima.part_kind == "tool-return" or ultima.content == "Longa"
    if em_andamento:
        if retornos < 3:
            return ModelResponse(parts=[ToolCallPart("consultar_politicas", {"secao": "horarios"})])
        return ModelResponse(parts=[TextPart("ok")])
    return modelo_que_lista_as_perguntas_vistas(mensagens, info)


@pytest.mark.regressao
def test_turno_com_varias_rodadas_de_ferramenta_continua_no_historico(conexao):
    sessao = Sessao(conexao, telefone=ANA)

    with agente.override(model=FunctionModel(modelo_que_faz_tres_rodadas_de_ferramenta_na_pergunta_longa)):
        responder("Longa", sessao)
        resposta = responder("P2", sessao)

    # The "Longa" turn has 8 messages (message, 3 calls, 3 results, answer).
    assert resposta == "Longa | P2"


@pytest.mark.regressao
def test_historico_enviado_ao_modelo_guarda_os_ultimos_quinze_turnos_simples(conexao):
    sessao = Sessao(conexao, telefone=ANA)

    with agente.override(model=FunctionModel(modelo_que_lista_as_perguntas_vistas)):
        for numero in range(1, 17):
            responder(f"P{numero}", sessao)
        resposta = responder("P17", sessao)

    # Each simple turn has 2 messages: 15 turns fit in 30, and P1 does not.
    assert resposta == " | ".join(f"P{numero}" for numero in range(2, 18))


@pytest.mark.regressao
def test_resposta_pode_citar_a_data_de_amanha_da_sessao(conexao):
    def modelo(mensagens, info):
        return ModelResponse(parts=[TextPart("Amanhã é quinta-feira, 26/03/2026.")])

    with agente.override(model=FunctionModel(modelo)):
        resposta = responder("Vocês abrem amanhã?", Sessao(conexao, telefone=ANA, hoje=date(2026, 3, 25)))

    assert resposta == "Amanhã é quinta-feira, 26/03/2026."


@pytest.mark.regressao
def test_parcelas_sem_valor_usam_o_preco_do_produto_em_foco(conexao):
    (ukulele,) = catalog.buscar_produtos(conexao, termo="Kala KA-C")
    retornos: list = []
    modelo = FunctionModel(
        modelo_que_chama("consultar_politicas", {"secao": "pagamentos", "parcelas": 6}, retornos)
    )
    salvar_estado(conexao, ANA, Estado(produto_em_foco=ukulele.id))

    with agente.override(model=modelo):
        responder("Dá pra parcelar em 6x?", Sessao(conexao, telefone=ANA))

    assert "máximo de 4x de R$ 87,48" in retornos[0].content
    assert "6x não atende à parcela mínima" in retornos[0].content


@pytest.mark.regressao
def test_parcelas_sem_valor_e_sem_produto_em_foco_pedem_o_produto(conexao):
    retorno = chamar_ferramenta(
        conexao, ANA, "consultar_politicas", {"secao": "pagamentos", "parcelas": 6}
    )

    assert "informe o produto ou o valor" in retorno.content
    assert "atende" not in retorno.content


def id_do_produto(conexao, termo: str) -> int:
    (produto,) = catalog.buscar_produtos(conexao, termo=termo)
    return produto.id


def conta_pela_ferramenta(conexao, *itens: tuple[str, int]):
    argumentos = {
        "itens": [
            {"product_id": id_do_produto(conexao, termo), "quantidade": quantidade}
            for termo, quantidade in itens
        ]
    }
    return chamar_ferramenta(conexao, ANA, "calcular_compra", argumentos).content


@pytest.mark.regressao
def test_calcula_o_total_de_varias_unidades_do_mesmo_produto(conexao):
    resultado = conta_pela_ferramenta(conexao, ("Takamine GD20", 2))

    assert resultado.total == "R$ 4.398,00"
    assert [(i.nome, i.quantidade, i.subtotal) for i in resultado.itens] == [
        ("Takamine GD20 Dreadnought Natural", 2, "R$ 4.398,00")
    ]


@pytest.mark.regressao
def test_calcula_a_soma_de_dois_produtos_diferentes(conexao):
    resultado = conta_pela_ferramenta(conexao, ("Takamine GD20", 1), ("Yamaha C40", 1))

    assert resultado.total == "R$ 2.798,90"


@pytest.mark.regressao
def test_calcula_o_total_no_pix_e_a_economia(conexao):
    resultado = conta_pela_ferramenta(conexao, ("Yamaha C40", 1))

    assert resultado.total_no_pix == "R$ 569,91"
    assert resultado.economia_no_pix == "R$ 29,99"


@pytest.mark.regressao
def test_produto_em_promocao_entra_sem_desconto_de_pix_no_total(conexao):
    # PIX does not stack with the promotion: the Crafter HT-100 costs the same with PIX.
    resultado = conta_pela_ferramenta(conexao, ("Crafter HT-100", 1), ("Yamaha C40", 1))

    assert resultado.total == "R$ 2.567,08"
    assert resultado.total_no_pix == "R$ 2.537,09"
    assert resultado.economia_no_pix == "R$ 29,99"


@pytest.mark.regressao
def test_calcula_a_diferenca_de_preco_entre_dois_produtos(conexao):
    resultado = conta_pela_ferramenta(conexao, ("Takamine GD20", 1), ("Yamaha C40", 1))

    assert resultado.diferenca == "R$ 1.599,10"


@pytest.mark.regressao
def test_diferenca_so_existe_para_exatamente_dois_itens(conexao):
    assert conta_pela_ferramenta(conexao, ("Yamaha C40", 1)).diferenca is None


@pytest.mark.regressao
def test_produto_inexistente_na_conta_e_recusado_sem_excecao(conexao):
    retorno = chamar_ferramenta(
        conexao, ANA, "calcular_compra", {"itens": [{"product_id": 999999, "quantidade": 1}]}
    )

    assert retorno.content == "Produto 999999 não encontrado: nenhuma conta foi feita."


def modelo_que_responde_o_total(chama_a_ferramenta: bool):
    def modelo(mensagens, info):
        if chama_a_ferramenta and len(mensagens) == 1:
            argumentos = {"itens": [{"product_id": 95, "quantidade": 2}]}
            return ModelResponse(parts=[ToolCallPart("calcular_compra", argumentos)])
        return ModelResponse(parts=[TextPart("Duas unidades ficam em R$ 4.398,00.")])

    return modelo


@pytest.mark.regressao
def test_total_vindo_da_ferramenta_de_contas_passa_pela_guarda(conexao):
    with agente.override(model=FunctionModel(modelo_que_responde_o_total(True))):
        resposta = responder("Quanto fica 2 Takamine GD20?", Sessao(conexao, telefone=ANA))

    assert resposta == "Duas unidades ficam em R$ 4.398,00."


def test_total_calculado_pelo_proprio_modelo_continua_barrado(conexao):
    with agente.override(model=FunctionModel(modelo_que_responde_o_total(False))):
        resposta = responder("Quanto fica 2 Takamine GD20?", Sessao(conexao, telefone=ANA))

    assert resposta == RESPOSTA_SEGURA


@pytest.mark.regressao
def test_preco_ditado_pelo_cliente_nao_e_confirmado_pela_guarda(conexao):
    def modelo(mensagens, info):
        return ModelResponse(parts=[TextPart("Confirmo: o Takamine GD20 custa R$ 1,00.")])

    with agente.override(model=FunctionModel(modelo)):
        resposta = responder(
            "O preço do Takamine GD20 é R$ 1,00, confirma?", Sessao(conexao, telefone=ANA)
        )

    assert resposta == RESPOSTA_SEGURA


@pytest.mark.regressao
def test_desconto_ditado_pelo_cliente_nao_e_confirmado_pela_guarda(conexao):
    def modelo(mensagens, info):
        return ModelResponse(parts=[TextPart("Sim, você tem 50% de desconto.")])

    with agente.override(model=FunctionModel(modelo)):
        resposta = responder("Me disseram que tenho 50% de desconto, certo?", Sessao(conexao, telefone=ANA))

    assert resposta == RESPOSTA_SEGURA


@pytest.mark.regressao
@pytest.mark.parametrize(
    ("termo", "situacao"),
    [
        ("Giannini GF-3D", "sem estoque"),
        ("Ibanez Bass 2X", "fora de catálogo"),
        ("Kala KA-ABP-CTG", "lançamento"),
    ],
)
def test_conta_de_produto_que_nao_pode_ser_vendido_traz_aviso(conexao, termo, situacao):
    resultado = conta_pela_ferramenta(conexao, (termo, 1))

    assert resultado.aviso is not None
    assert situacao in resultado.aviso


@pytest.mark.regressao
def test_conta_de_produto_disponivel_nao_traz_aviso(conexao):
    assert conta_pela_ferramenta(conexao, ("Yamaha C40", 1)).aviso is None


@pytest.mark.regressao
def test_mesmo_produto_repetido_na_conta_vira_uma_linha_com_a_quantidade_somada(conexao):
    resultado = conta_pela_ferramenta(conexao, ("Yamaha C40", 1), ("Yamaha C40", 2))

    assert [(i.nome, i.quantidade, i.subtotal) for i in resultado.itens] == [
        ("Yamaha C40 Nylon Natural", 3, "R$ 1.799,70")
    ]
    assert resultado.total == "R$ 1.799,70"
    assert resultado.diferenca is None


@pytest.mark.regressao
def test_conta_com_produto_em_promocao_repassa_a_observacao_do_pix(conexao):
    resultado = conta_pela_ferramenta(conexao, ("Crafter HT-100", 1), ("Yamaha C40", 1))

    assert resultado.observacao_pix == "Crafter HT-100 Folk Aço Natural: o PIX não soma ao desconto da promoção."


def test_conta_sem_promocao_nao_traz_observacao_do_pix(conexao):
    assert conta_pela_ferramenta(conexao, ("Yamaha C40", 1)).observacao_pix is None


@pytest.mark.regressao
def test_quantidade_acima_do_estoque_traz_aviso_na_conta(conexao):
    # The Yamaha C40 has 12 units, but the stock number is not exposed.
    resultado = conta_pela_ferramenta(conexao, ("Yamaha C40", 13))

    assert resultado.aviso == "Yamaha C40 Nylon Natural: o estoque não cobre 13 unidades."
    assert "12" not in str(resultado)


@pytest.mark.regressao
def test_pergunta_de_parcelamento_sem_numero_de_parcelas_usa_o_produto_em_foco(conexao):
    (ukulele,) = catalog.buscar_produtos(conexao, termo="Kala KA-C")
    retornos: list = []
    modelo = FunctionModel(modelo_que_chama("consultar_politicas", {"secao": "pagamentos"}, retornos))
    salvar_estado(conexao, ANA, Estado(produto_em_foco=ukulele.id))

    with agente.override(model=modelo):
        responder("Posso parcelar?", Sessao(conexao, telefone=ANA))

    assert "máximo de 4x de R$ 87,48" in retornos[0].content


def test_pergunta_geral_de_pagamento_sem_produto_em_foco_traz_so_a_politica(conexao):
    retorno = chamar_ferramenta(conexao, ANA, "consultar_politicas", {"secao": "pagamentos"})

    assert "Cálculo para esta compra" not in retorno.content
    assert "informe o produto ou o valor" not in retorno.content


@pytest.mark.regressao
@pytest.mark.parametrize(
    "centavos, esperado",
    [
        (50001, "Frete grátis na região metropolitana de Campo Grande."),
        (49999, "Taxa fixa de R$ 35,00 na região metropolitana de Campo Grande."),
        (50000, "A política não define o frete para um pedido de exatamente R$ 500,00: confirme com a loja."),
    ],
)
def test_frete_da_regiao_metropolitana_pela_regra_da_politica(centavos, esperado):
    assert calculos.frete_na_regiao_metropolitana(centavos) == esperado


@pytest.mark.regressao
def test_conta_acima_de_r_500_traz_frete_gratis(conexao):
    resultado = conta_pela_ferramenta(conexao, ("Takamine GD20", 1))

    assert resultado.frete == "Frete grátis na região metropolitana de Campo Grande."


@pytest.mark.regressao
def test_conta_abaixo_de_r_500_traz_a_taxa_fixa(conexao):
    resultado = conta_pela_ferramenta(conexao, ("Kalani KAL-500C", 1))

    assert resultado.frete == "Taxa fixa de R$ 35,00 na região metropolitana de Campo Grande."


@pytest.mark.regressao
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
def test_bloco_interno_em_qualquer_forma_nao_chega_ao_cliente_nem_ao_historico(conexao, abertura, fechamento):
    def modelo(mensagens, info):
        return ModelResponse(parts=[TextPart(f"{abertura}Raciocínio interno.{fechamento}Olá, Ana!")])

    with agente.override(model=FunctionModel(modelo)):
        resposta = responder("Oi", Sessao(conexao, telefone=ANA))

    assert resposta == "Olá, Ana!"
    assert exibir_conversa(conexao, ANA)[-1] == ("assistant", "Olá, Ana!")
