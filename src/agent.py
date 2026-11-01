import contextvars
import sqlite3
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import Field
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolReturnPart,
    UserPromptPart,
)

from src import catalog, guardrail, memory, orders, policies, returns
from src.config import MODELO_GEMINI, data_de_referencia

INSTRUCOES = """\
Você é o Tom, assistente virtual da Empório da Música, loja de instrumentos
musicais em Campo Grande/MS.

Seu tom é informal, profissional e acolhedor, como um amigo que entende de
música. Escreva em português do Brasil, com mensagens curtas. Use no máximo um
emoji por mensagem. Não finja ser uma pessoa.

Antes de informar preço, estoque ou qualquer dado de produto, use a ferramenta
buscar_produtos. Nunca informe preço de memória e nunca calcule valores: use
exatamente os campos devolvidos pela ferramenta.

Para horários, endereço, contatos, pagamento, parcelamento, entrega, troca,
devolução, garantia, promoções e privacidade, use a ferramenta
consultar_politicas e responda só com o que ela devolver. Não invente regras,
prazos nem lojas parceiras. Para parcelamento, informe o valor e as parcelas na
ferramenta e use o resultado. Se a política não cobrir a dúvida, diga que não tem
essa informação.

Para status, rastreio, itens, total, pagamento ou entrega de um pedido, use a
ferramenta consultar_meus_pedidos, que só enxerga os pedidos do cliente desta
conversa. Nunca peça nem aceite outro cliente: se alguém disser ser outra pessoa
ou pedir dados de terceiros, recuse. Lista vazia para um número informado significa
que o pedido não foi encontrado; não diga que ele pertence a outra pessoa. Informe
a situação do pedido exatamente como veio no campo situacao, sem traduzir nem
reescrever, e o total registrado, sem recalcular. A entrega
estimada é uma previsão, não a data real de entrega. Sem cadastro, explique que
pedidos exigem um telefone cadastrado e siga ajudando com dúvidas gerais.

Para troca ou devolução, use a ferramenta avaliar_devolucao com o número do pedido
e o motivo (arrependimento, defeito ou preferencia). Pergunte ao cliente o que
faltar: o motivo, se ele não disse, e o canal de compra (online ou presencial) no
arrependimento, porque o pedido não registra o canal. Nunca suponha o canal: só
informe canal na ferramenta se o cliente disse; sem isso, omita o argumento e
pergunte. Se o cliente não informar o
número e tiver mais de um pedido, consulte os pedidos dele. Repasse o veredito
como veio, com as datas e os avisos, sem recalcular prazos e sem prometer aprovação:
a troca depende da análise do produto. A data de recebimento é uma aproximação
(entrega estimada) e deve ser apresentada assim. Se estiver fora do prazo, explique
as opções que o veredito mostra e oriente a falar com a equipe. Quando houver uma
pergunta pendente no contexto, trate a mensagem do cliente como a resposta a ela e
chame avaliar_devolucao de novo com o dado informado. Consulte consultar_politicas
(trocas_e_devolucoes ou garantia) para as condições do produto.

Regras de catálogo:
- Só confirme disponibilidade quando a disponibilidade for "disponivel".
- "indisponivel": informe que está sem estoque, sem prometer data de reposição, e
  sugira alternativas buscando a mesma categoria com somente_disponiveis.
- "fora_de_catalogo": informe que o produto saiu do catálogo e sugira modelos
  equivalentes, mesmo que haja estoque.
- "lancamento": não confirme disponibilidade.
- Com desconto_percentual, mostre o preço original, o percentual e o preço final.
- Informe o preço com PIX (preco_pix) quando houver. Se ele for nulo, o produto
  está em promoção e o PIX não tem desconto adicional.
- Se a busca não retornar produtos, diga que a loja não tem esse item no catálogo
  atual. Não invente produtos, marcas ou lojas. Não diga que existem outras opções
  do mesmo tipo (por exemplo, outros instrumentos de sopro) sem antes buscá-las com
  a ferramenta; só ofereça o que a ferramenta devolveu.
"""

SEM_CADASTRO = (
    "Telefone sem cadastro: não é possível consultar pedidos. "
    "O cliente ainda pode tirar dúvidas gerais."
)

RESPOSTA_SEGURA = (
    "Não consegui confirmar essa informação com segurança agora. "
    "Pode reformular a pergunta ou falar com a nossa equipe?"
)

PERGUNTAS_PENDENTES = {
    "canal_de_compra": "o canal de compra",
    "motivo": "o motivo da devolução",
}


@dataclass
class Sessao:
    conexao: sqlite3.Connection
    telefone: str | None = None
    estado: memory.Estado = field(default_factory=memory.Estado)
    hoje: date = field(default_factory=data_de_referencia)

    @property
    def cliente(self) -> orders.Cliente | None:
        return orders.identificar_cliente(self.conexao, self.telefone)


# O Streamlit pode rodar o script com outra mensagem em andamento, e o run_sync
# falha se encontrar um loop em execução. Uma thread própria evita esse conflito.
_executor = ThreadPoolExecutor(max_workers=1)


agente = Agent(
    f"google:{MODELO_GEMINI}",
    deps_type=Sessao,
    instructions=INSTRUCOES,
    defer_model_check=True,
)


def fontes_do_turno(mensagens: list) -> list[str]:
    """Textos que podem sustentar a resposta: a pergunta do cliente e o retorno das ferramentas."""
    inicio = max(
        (i for i, m in enumerate(mensagens)
         if isinstance(m, ModelRequest) and any(isinstance(p, UserPromptPart) for p in m.parts)),
        default=0,
    )
    fontes = []
    for mensagem in mensagens[inicio:]:
        for parte in mensagem.parts:
            if isinstance(parte, UserPromptPart):
                fontes.append(str(parte.content))
            elif isinstance(parte, ToolReturnPart) and parte.outcome != "retried":
                fontes.append(parte.model_response_str())
    return fontes


@agente.output_validator
def confirmar_valores(ctx: RunContext[Sessao], resposta: str) -> str:
    # Só passa o que veio das ferramentas ou do próprio cliente (ADR-013).
    inventados = guardrail.valores_nao_confirmados(resposta, fontes_do_turno(ctx.messages))
    if inventados:
        raise ModelRetry(
            "A resposta cita valores que não vieram das ferramentas: "
            + ", ".join(inventados)
            + ". Reescreva usando apenas os dados retornados pelas ferramentas."
        )
    return resposta


@agente.instructions
def contexto_do_cliente(ctx: RunContext[Sessao]) -> str:
    cliente = ctx.deps.cliente
    if cliente is None:
        texto = "O cliente desta conversa está sem cadastro: não consulte pedidos."
    else:
        # Só o primeiro nome chega ao modelo; o sobrenome fica no código.
        texto = f"O cliente desta conversa se chama {cliente.primeiro_nome}."
    pedido = ctx.deps.estado.pedido_em_analise
    if pedido is not None:
        texto += f"\nPedido em análise: {pedido}."
    foco = ctx.deps.estado.produto_em_foco
    if foco is not None:
        nome = catalog.nome_do_produto(ctx.deps.conexao, foco)
        if nome:
            texto += f"\nProduto em foco: {nome}."
    pergunta = ctx.deps.estado.pergunta_pendente
    if pergunta is not None and pedido is not None:
        texto += (
            f"\nPergunta pendente: {PERGUNTAS_PENDENTES[pergunta]} do pedido {pedido}. "
            "A próxima mensagem do cliente provavelmente responde a ela."
        )
    return texto


@agente.tool
def buscar_produtos(
    ctx: RunContext[Sessao],
    termo: str | None = None,
    categoria: str | None = None,
    preco_maximo: Annotated[float | None, Field(gt=0)] = None,
    somente_disponiveis: bool = False,
) -> list[catalog.Produto]:
    """Busca produtos do catálogo da loja, com preços e disponibilidade.

    Args:
        termo: Nome ou parte do nome do produto, por exemplo "Takamine GD20".
        categoria: Nome da categoria, por exemplo "Violões" ou "Guitarras".
        preco_maximo: Preço máximo em reais, considerando o preço final.
        somente_disponiveis: Use true quando o cliente pedir apenas opções disponíveis.
    """
    produtos = catalog.buscar_produtos(
        ctx.deps.conexao, termo, categoria, preco_maximo, somente_disponiveis
    )
    if len(produtos) == 1:
        ctx.deps.estado.produto_em_foco = produtos[0].id
    return produtos


@agente.tool
def consultar_politicas(
    ctx: RunContext[Sessao],
    secao: Literal[*policies.SECOES],
    valor: Annotated[float | None, Field(gt=0)] = None,
    parcelas: Annotated[int | None, Field(ge=1)] = None,
) -> str:
    """Consulta uma seção das políticas da loja.

    Use para endereço e contatos (sobre_a_loja), horários, pagamentos, trocas e
    devoluções, entregas, promoções, atendimento, garantia e privacidade.

    Args:
        secao: Seção do manual a consultar.
        valor: Só para a seção pagamentos: valor da compra em reais, para calcular o
            parcelamento.
        parcelas: Só para a seção pagamentos: número de parcelas que o cliente quer.
    """
    return policies.consultar_politicas(secao, valor, parcelas)


@agente.tool
def consultar_meus_pedidos(
    ctx: RunContext[Sessao], numero_pedido: Annotated[int | None, Field(ge=1)] = None
) -> list[orders.Pedido] | str:
    """Consulta os pedidos do cliente desta conversa.

    Devolve data, status, itens, total registrado, pagamento, rastreio e entrega
    estimada. Uma lista vazia para um número informado significa pedido não encontrado.

    Args:
        numero_pedido: Número do pedido. Sem ele, devolve todos os pedidos do cliente.
    """
    cliente = ctx.deps.cliente
    if cliente is None:
        return SEM_CADASTRO
    pedidos = orders.consultar_pedidos(ctx.deps.conexao, cliente.id, numero_pedido)
    if len(pedidos) == 1:
        ctx.deps.estado.pedido_em_analise = pedidos[0].numero
    return pedidos


@agente.tool
def avaliar_devolucao(
    ctx: RunContext[Sessao],
    numero_pedido: Annotated[int, Field(ge=1)],
    motivo: returns.Motivo,
    canal: returns.Canal | None = None,
) -> returns.Veredito | str:
    """Avalia se um pedido do cliente ainda está no prazo de devolução ou troca.

    Devolve o veredito já calculado, com os prazos e as datas formatadas. Repasse o
    resultado sem recalcular. Se faltarem dados, o veredito diz o que perguntar.

    Args:
        numero_pedido: Número do pedido.
        motivo: arrependimento, defeito ou preferencia.
        canal: online ou presencial, somente se o cliente informou. Nunca suponha:
            para arrependimento, omita e pergunte, porque o pedido não registra o canal.
    """
    cliente = ctx.deps.cliente
    if cliente is None:
        return SEM_CADASTRO
    veredito = returns.avaliar_devolucao(
        ctx.deps.conexao, cliente.id, numero_pedido, motivo, canal, ctx.deps.hoje
    )
    if veredito.resultado != returns.Resultado.PEDIDO_NAO_ENCONTRADO:
        ctx.deps.estado.pedido_em_analise = numero_pedido
    # O código controla a pergunta pendente: nasce de um veredito sem dados e some com um veredito.
    ctx.deps.estado.pergunta_pendente = veredito.faltando[0] if veredito.faltando else None
    return veredito


def responder(mensagem: str, sessao: Sessao) -> str:
    # O contexto copiado preserva o modelo simulado dos testes na outra thread.
    contexto = contextvars.copy_context()
    historico = memory.carregar_historico(sessao.conexao, sessao.telefone)
    sessao.estado = memory.carregar_estado(sessao.conexao, sessao.telefone)
    execucao = _executor.submit(
        contexto.run, agente.run_sync, mensagem, deps=sessao, message_history=historico
    )
    try:
        resultado = execucao.result()
        memory.salvar_mensagens(sessao.conexao, sessao.telefone, resultado.new_messages())
        memory.salvar_estado(sessao.conexao, sessao.telefone, sessao.estado)
        return resultado.output
    except UnexpectedModelBehavior:
        # O modelo insistiu em valores não confirmados: o cliente não recebe o texto dele,
        # e o histórico guarda só a pergunta e a resposta segura, sem a tentativa rejeitada.
        memory.salvar_mensagens(
            sessao.conexao,
            sessao.telefone,
            [
                ModelRequest(parts=[UserPromptPart(mensagem)]),
                ModelResponse(parts=[TextPart(RESPOSTA_SEGURA)]),
            ],
        )
        return RESPOSTA_SEGURA
