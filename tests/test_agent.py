import asyncio
from datetime import date

import pytest
from pydantic_ai import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from src import catalog
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

    assert "Ana" in instrucoes
    assert "Carolina" not in instrucoes
    assert "Ferreira" not in instrucoes


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

        # Outra conexão ao mesmo arquivo equivale a reiniciar a aplicação.
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


def test_historico_enviado_ao_modelo_nao_separa_chamada_de_ferramenta_do_retorno(conexao):
    sessao = Sessao(conexao, telefone=ANA)

    with agente.override(
        model=FunctionModel(modelo_que_consulta_o_horario_e_lista_as_perguntas)
    ):
        for pergunta in ("P1", "P2", "P3"):
            responder(pergunta, sessao)
        resposta = responder("P4", sessao)

    # Cada turno com ferramenta tem 4 mensagens: caberia só um turno inteiro em 7.
    assert resposta == "P3 | P4"


def test_historico_enviado_ao_modelo_tem_no_maximo_7_mensagens(conexao):
    sessao = Sessao(conexao, telefone=ANA)

    with agente.override(model=FunctionModel(modelo_que_lista_as_perguntas_vistas)):
        for pergunta in ("P1", "P2", "P3", "P4", "P5"):
            responder(pergunta, sessao)
        resposta = responder("P6", sessao)

    # Cada turno simples tem 2 mensagens: 3 turnos cabem em 7, e o P2 não.
    assert resposta == "P3 | P4 | P5 | P6"


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
    # A correção pedida pela guarda também chega como fala do cliente, por isso
    # o modelo insiste enquanto a pergunta seguinte ainda não apareceu.
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


def chamar_ferramenta_na_data(conexao, telefone, hoje, ferramenta, argumentos):
    capturados: list = []
    modelo = FunctionModel(modelo_que_chama(ferramenta, argumentos, capturados))
    with agente.override(model=modelo):
        responder("Teste", Sessao(conexao, telefone=telefone, hoje=hoje))
    return capturados[0]


def test_ferramenta_de_devolucao_usa_o_pedido_do_cliente_e_a_data_da_sessao(conexao):
    retorno = chamar_ferramenta_na_data(
        conexao, LETICIA, date(2026, 2, 20), "avaliar_devolucao",
        {"numero_pedido": 7, "motivo": "arrependimento", "canal": "online"},
    )

    assert retorno.content.resultado == "dentro_do_prazo"
    assert retorno.content.regras[0].prazo_ate == "24/02/2026"


def test_devolucao_de_pedido_de_outro_cliente_volta_como_nao_encontrado(conexao):
    # O pedido 7 é da cliente 14; a sessão é da cliente 2.
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


def test_canal_nao_informado_nao_deixa_pergunta_gravada_para_o_proximo_assunto(conexao):
    sessao = Sessao(conexao, telefone=LETICIA)
    modelo = modelo_que_avalia_a_devolucao_e_depois_mostra_as_instrucoes(
        {"numero_pedido": 7, "motivo": "arrependimento"}
    )

    with agente.override(model=FunctionModel(modelo)):
        responder("Quero devolver", sessao)
        instrucoes = responder("Foi online", sessao)

    # A pergunta do Tom fica só no histórico; o estado guarda apenas o pedido em análise.
    assert "Pergunta pendente" not in instrucoes
    assert "Pedido em análise: 7" in instrucoes


@pytest.mark.parametrize("argumentos", [
    {"numero_pedido": 7, "motivo": "arrependimento"},
    {"numero_pedido": 7, "motivo": "arrependimento", "canal": "presencial"},
    {"numero_pedido": 999, "motivo": "arrependimento"},
])
def test_pedido_que_nao_e_do_cliente_nao_vira_pedido_em_analise(conexao, argumentos):
    # O pedido 7 é da cliente 14; a sessão é da cliente 2 (Ana). O 999 não existe.
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


def test_mensagem_nao_consegue_registrar_interesse_em_outro_telefone(conexao):
    retorno = chamar_ferramenta(
        conexao, ANA, "registrar_interesse", {"product_id": 96, "phone": "67911112222"}
    )

    assert retorno.outcome == "retried"
    assert listar_pendentes(conexao, "67911112222") == []
    assert listar_pendentes(conexao, ANA) == []


def modelo_que_retoma_o_interesse(mensagens: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Lê o nome do interesse no contexto e consulta o catálogo, como manda o prompt."""
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
