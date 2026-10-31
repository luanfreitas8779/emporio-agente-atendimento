import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import ValidationError
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolReturnPart,
    UserPromptPart,
)

from src.phone import normalizar_telefone

# Diferente das tabelas de origem, estas nunca são recriadas pela carga: guardam
# o que os clientes disseram. Por isso o esquema é idempotente.
ESQUEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY,
    phone TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations (id),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation_state (
    phone TEXT PRIMARY KEY,
    pedido_em_analise INTEGER CHECK (pedido_em_analise > 0),
    produto_em_foco INTEGER CHECK (produto_em_foco > 0),
    pergunta_pendente TEXT CHECK (pergunta_pendente IN ('canal_de_compra', 'motivo')),
    updated_at TEXT NOT NULL
);
"""

MAX_MENSAGENS_NO_HISTORICO = 7


@dataclass
class Estado:
    """O que precisa atravessar mensagens, guardado em código e não na memória do modelo."""

    pedido_em_analise: int | None = None
    produto_em_foco: int | None = None
    # Pergunta feita ao cliente que a próxima mensagem deve responder.
    pergunta_pendente: str | None = None


def criar_tabelas(conexao: sqlite3.Connection) -> None:
    conexao.executescript(ESQUEMA)


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _inicia_um_turno(mensagem: ModelMessage) -> bool:
    # Um pedido com a fala do cliente e sem retorno de ferramenta não responde a
    # nenhuma chamada anterior: é um ponto seguro para começar o histórico.
    return isinstance(mensagem, ModelRequest) and (
        any(isinstance(p, UserPromptPart) for p in mensagem.parts)
        and not any(isinstance(p, ToolReturnPart) for p in mensagem.parts)
    )


def limitar_historico(mensagens: list[ModelMessage]) -> list[ModelMessage]:
    """Mantém as últimas mensagens sem separar uma chamada de ferramenta do retorno.

    O corte começa no primeiro turno inteiro que cabe no limite; um turno que
    estoura o limite é descartado por completo.
    """
    inicio = max(0, len(mensagens) - MAX_MENSAGENS_NO_HISTORICO)
    for i in range(inicio, len(mensagens)):
        if _inicia_um_turno(mensagens[i]):
            return mensagens[i:]
    return []


def _ler_mensagens(conexao: sqlite3.Connection, telefone: str | None) -> list[ModelMessage]:
    chave = normalizar_telefone(telefone or "")
    if chave is None:
        return []
    linhas = conexao.execute(
        """
        SELECT m.content FROM messages m
        JOIN conversations c ON c.id = m.conversation_id
        WHERE c.phone = ? ORDER BY m.id
        """,
        (chave,),
    ).fetchall()
    mensagens: list[ModelMessage] = []
    for linha in linhas:
        try:
            mensagens.extend(ModelMessagesTypeAdapter.validate_json(linha["content"]))
        except ValidationError:
            # Uma linha ilegível não pode travar o atendimento nem deixar um turno
            # pela metade: o histórico recomeça depois dela.
            mensagens = []
    return mensagens


def carregar_historico(conexao: sqlite3.Connection, telefone: str | None) -> list[ModelMessage]:
    return limitar_historico(_ler_mensagens(conexao, telefone))


def exibir_conversa(conexao: sqlite3.Connection, telefone: str | None) -> list[tuple[str, str]]:
    """Fala do cliente e resposta final de cada turno, como o cliente as viu."""
    conversa: list[tuple[str, str]] = []
    resposta: str | None = None
    for mensagem in _ler_mensagens(conexao, telefone):
        if _inicia_um_turno(mensagem):
            if resposta is not None:
                conversa.append(("assistant", resposta))
                resposta = None
            texto = " ".join(
                str(p.content) for p in mensagem.parts if isinstance(p, UserPromptPart)
            )
            conversa.append(("user", texto))
        elif isinstance(mensagem, ModelResponse):
            textos = [p.content for p in mensagem.parts if isinstance(p, TextPart)]
            if textos:
                # Respostas rejeitadas pela guarda são sobrescritas pela seguinte.
                resposta = " ".join(textos)
    if resposta is not None:
        conversa.append(("assistant", resposta))
    return conversa


def salvar_mensagens(
    conexao: sqlite3.Connection, telefone: str | None, mensagens: list[ModelMessage]
) -> None:
    chave = normalizar_telefone(telefone or "")
    if chave is None:
        return
    agora = _agora()
    conexao.execute(
        "INSERT INTO conversations (phone, created_at, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT (phone) DO UPDATE SET updated_at = excluded.updated_at",
        (chave, agora, agora),
    )
    conversa = conexao.execute("SELECT id FROM conversations WHERE phone = ?", (chave,)).fetchone()
    conexao.executemany(
        "INSERT INTO messages (conversation_id, content, created_at) VALUES (?, ?, ?)",
        [
            (conversa["id"], ModelMessagesTypeAdapter.dump_json([m]).decode(), agora)
            for m in mensagens
        ],
    )
    conexao.commit()


def carregar_estado(conexao: sqlite3.Connection, telefone: str | None) -> Estado:
    chave = normalizar_telefone(telefone or "")
    linha = conexao.execute(
        "SELECT pedido_em_analise, produto_em_foco, pergunta_pendente "
        "FROM conversation_state WHERE phone = ?",
        (chave,),
    ).fetchone()
    return Estado(
        linha["pedido_em_analise"], linha["produto_em_foco"], linha["pergunta_pendente"]
    ) if linha else Estado()


def salvar_estado(conexao: sqlite3.Connection, telefone: str | None, estado: Estado) -> None:
    chave = normalizar_telefone(telefone or "")
    if chave is None:
        return
    conexao.execute(
        """
        INSERT INTO conversation_state (
            phone, pedido_em_analise, produto_em_foco, pergunta_pendente, updated_at
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (phone) DO UPDATE SET
            pedido_em_analise = excluded.pedido_em_analise,
            produto_em_foco = excluded.produto_em_foco,
            pergunta_pendente = excluded.pergunta_pendente,
            updated_at = excluded.updated_at
        """,
        (chave, estado.pedido_em_analise, estado.produto_em_foco, estado.pergunta_pendente, _agora()),
    )
    conexao.commit()
