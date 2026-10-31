import contextvars
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Literal

from pydantic_ai import Agent, RunContext

from src import catalog, orders, policies
from src.config import MODELO_GEMINI

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


@dataclass
class Sessao:
    conexao: sqlite3.Connection
    telefone: str | None = None


# O Streamlit pode rodar o script com outra mensagem em andamento, e o run_sync
# falha se encontrar um loop em execução. Uma thread própria evita esse conflito.
_executor = ThreadPoolExecutor(max_workers=1)


agente = Agent(
    f"google:{MODELO_GEMINI}",
    deps_type=Sessao,
    instructions=INSTRUCOES,
    defer_model_check=True,
)


@agente.instructions
def contexto_do_cliente(ctx: RunContext[Sessao]) -> str:
    cliente = (
        orders.identificar_cliente(ctx.deps.conexao, ctx.deps.telefone)
        if ctx.deps.telefone
        else None
    )
    if cliente is None:
        return "O cliente desta conversa está sem cadastro: não consulte pedidos."
    return f"O cliente desta conversa se chama {cliente.nome}. Chame-o pelo primeiro nome."


@agente.tool
def buscar_produtos(
    ctx: RunContext[Sessao],
    termo: str | None = None,
    categoria: str | None = None,
    preco_maximo: float | None = None,
    somente_disponiveis: bool = False,
) -> list[catalog.Produto]:
    """Busca produtos do catálogo da loja, com preços e disponibilidade.

    Args:
        termo: Nome ou parte do nome do produto, por exemplo "Takamine GD20".
        categoria: Nome da categoria, por exemplo "Violões" ou "Guitarras".
        preco_maximo: Preço máximo em reais, considerando o preço final.
        somente_disponiveis: Use true quando o cliente pedir apenas opções disponíveis.
    """
    return catalog.buscar_produtos(
        ctx.deps.conexao, termo, categoria, preco_maximo, somente_disponiveis
    )


@agente.tool
def consultar_politicas(
    ctx: RunContext[Sessao],
    secao: Literal[
        "sobre_a_loja",
        "horarios",
        "pagamentos",
        "trocas_e_devolucoes",
        "entregas",
        "promocoes",
        "atendimento",
        "garantia",
        "privacidade",
    ],
    valor: float | None = None,
    parcelas: int | None = None,
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
    ctx: RunContext[Sessao], numero_pedido: int | None = None
) -> list[orders.Pedido] | str:
    """Consulta os pedidos do cliente desta conversa.

    Devolve data, status, itens, total registrado, pagamento, rastreio e entrega
    estimada. Uma lista vazia para um número informado significa pedido não encontrado.

    Args:
        numero_pedido: Número do pedido. Sem ele, devolve todos os pedidos do cliente.
    """
    cliente = (
        orders.identificar_cliente(ctx.deps.conexao, ctx.deps.telefone)
        if ctx.deps.telefone
        else None
    )
    if cliente is None:
        return SEM_CADASTRO
    return orders.consultar_pedidos(ctx.deps.conexao, cliente.id, numero_pedido)


def responder(mensagem: str, sessao: Sessao) -> str:
    # O contexto copiado preserva o modelo simulado dos testes na outra thread.
    contexto = contextvars.copy_context()
    execucao = _executor.submit(contexto.run, agente.run_sync, mensagem, deps=sessao)
    return execucao.result().output
