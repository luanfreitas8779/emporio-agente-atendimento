import sqlite3
import unicodedata
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

DISPONIVEL = "disponivel"
INDISPONIVEL = "indisponivel"
FORA_DE_CATALOGO = "fora_de_catalogo"
LANCAMENTO = "lancamento"
PERCENTUAL_PIX = 5


@dataclass(frozen=True)
class Produto:
    id: int
    nome: str
    categoria: str
    preco: str
    desconto_percentual: int | None
    preco_final: str
    preco_pix: str | None
    disponibilidade: str


def formatar_preco(centavos: int) -> str:
    reais, resto = divmod(centavos, 100)
    return f"R$ {reais:,}".replace(",", ".") + f",{resto:02d}"


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFD", texto.casefold())
    return "".join(c for c in sem_acento if not unicodedata.combining(c))


def singularizar(texto: str) -> str:
    """Reduz cada palavra normalizada ao singular, para "violão" casar com "Violões"."""
    palavras = []
    for palavra in texto.split():
        if len(palavra) > 3:
            for plural, singular in (("oes", "ao"), ("aes", "ao"), ("ns", "m"), ("s", "")):
                if palavra.endswith(plural):
                    palavra = palavra.removesuffix(plural) + singular
                    break
        palavras.append(palavra)
    return " ".join(palavras)


def classificar(status: str, estoque: int) -> str:
    # O status tem prioridade sobre o estoque.
    if status == "discontinued":
        return FORA_DE_CATALOGO
    if status == "coming_soon":
        return LANCAMENTO
    return DISPONIVEL if estoque > 0 else INDISPONIVEL


def aplicar_desconto(centavos: int, percentual: int) -> int:
    return int((Decimal(centavos) * (100 - percentual) / 100).quantize(Decimal(1), ROUND_HALF_UP))


def calcular_preco_final(linha: sqlite3.Row) -> int:
    desconto = linha["discount_percent"]
    return aplicar_desconto(linha["price_cents"], desconto) if desconto else linha["price_cents"]


def montar_produto(linha: sqlite3.Row) -> Produto:
    desconto = linha["discount_percent"]
    centavos = linha["price_cents"]
    # O PIX incide sobre o preço de tabela e não se soma a promoções.
    pix = None if desconto else formatar_preco(aplicar_desconto(centavos, PERCENTUAL_PIX))
    return Produto(
        linha["product_id"],
        linha["name"],
        linha["categoria"],
        formatar_preco(centavos),
        desconto,
        formatar_preco(calcular_preco_final(linha)),
        pix,
        classificar(linha["status"], linha["stock_quantity"]),
    )


def buscar_produtos(
    conexao: sqlite3.Connection,
    termo: str | None = None,
    categoria: str | None = None,
    preco_maximo: float | None = None,
    somente_disponiveis: bool = False,
) -> list[Produto]:
    linhas = conexao.execute(
        """
        SELECT p.product_id, p.name, c.name AS categoria, p.price_cents,
               p.stock_quantity, p.status, pr.discount_percent
        FROM products p
        JOIN categories c ON c.category_id = p.category_id
        LEFT JOIN promotions pr ON pr.product_id = p.product_id AND pr.is_active = 1
        ORDER BY p.name
        """
    ).fetchall()

    palavras = normalizar(termo or "").split()
    categoria_normalizada = singularizar(normalizar(categoria or ""))
    produtos = []
    for linha in linhas:
        nome = normalizar(linha["name"])
        if not all(palavra in nome for palavra in palavras):
            continue
        if categoria_normalizada not in singularizar(normalizar(linha["categoria"])):
            continue
        if preco_maximo is not None and calcular_preco_final(linha) > Decimal(str(preco_maximo)) * 100:
            continue
        produto = montar_produto(linha)
        if somente_disponiveis and produto.disponibilidade != DISPONIVEL:
            continue
        produtos.append(produto)
    return produtos
