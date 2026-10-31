import sqlite3
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

Antes de informar preço ou qualquer dado de produto, use a ferramenta
buscar_produtos. Nunca informe preço de memória. Se a ferramenta não encontrar o
produto, diga isso com clareza e não invente informações.
"""


@dataclass
class Sessao:
    conexao: sqlite3.Connection


agente = Agent(
    f"google:{MODELO_GEMINI}",
    deps_type=Sessao,
    instructions=INSTRUCOES,
    defer_model_check=True,
)


@agente.tool
def buscar_produtos(ctx: RunContext[Sessao], termo: str) -> list[catalog.Produto]:
    """Busca produtos do catálogo da loja pelo nome.

    Args:
        termo: Nome ou parte do nome do produto, por exemplo "Takamine GD20".
    """
    return catalog.buscar_produtos(ctx.deps.conexao, termo)


def responder(mensagem: str, sessao: Sessao) -> str:
    return agente.run_sync(mensagem, deps=sessao).output
