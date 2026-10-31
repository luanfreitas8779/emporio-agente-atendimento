import contextvars
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from pydantic_ai import Agent, RunContext

from src import catalog
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
  atual. Não invente produtos, marcas ou lojas.
"""


@dataclass
class Sessao:
    conexao: sqlite3.Connection


# O Streamlit pode rodar o script com outra mensagem em andamento, e o run_sync
# falha se encontrar um loop em execução. Uma thread própria evita esse conflito.
_executor = ThreadPoolExecutor(max_workers=1)


agente = Agent(
    f"google:{MODELO_GEMINI}",
    deps_type=Sessao,
    instructions=INSTRUCOES,
    defer_model_check=True,
)


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


def responder(mensagem: str, sessao: Sessao) -> str:
    # O contexto copiado preserva o modelo simulado dos testes na outra thread.
    contexto = contextvars.copy_context()
    execucao = _executor.submit(contexto.run, agente.run_sync, mensagem, deps=sessao)
    return execucao.result().output
