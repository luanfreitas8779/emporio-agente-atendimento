import json
import sqlite3
import unicodedata
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

DISPONIVEL = "disponivel"
INDISPONIVEL = "indisponivel"
FORA_DE_CATALOGO = "fora_de_catalogo"
LANCAMENTO = "lancamento"
PERCENTUAL_PIX = 5
OBSERVACAO_PIX_EM_PROMOCAO = "O PIX não soma ao desconto da promoção."
# Fields that the record contradicts in another column (DQ-05); the model must not state them.
CAMPOS_DIVERGENTES = {137: {"strings"}}
# The record has the `specs` keys and some values in English; the customer reads Portuguese.
NOMES_DAS_ESPECIFICACOES = {
    "top": "tampo",
    "back_sides": "fundo e laterais",
    "neck": "braço",
    "strings": "cordas",
    "scale": "escala",
    "electronics": "eletrônica",
    "color": "cor",
    "body": "corpo",
    "shells": "cascos",
    "pieces": "peças",
    "hardware": "ferragens",
    "keys": "teclas",
    "type": "tipo",
    "polyphony": "polifonia",
}
VALORES_DAS_ESPECIFICACOES = {
    "yes": "sim",
    "no": "não",
    "steel": "aço",
    "nylon": "náilon",
    "included": "incluídas",
}
TAMANHO_MINIMO_PARA_ERRO_DE_DIGITACAO = 5
# Connecting words the customer writes that are not part of any name.
PALAVRAS_DE_LIGACAO = frozenset(
    "a as o os um uma e ou da das de do dos com para pra no na em".split()
)


@dataclass(frozen=True)
class Filtros:
    """What the customer asked for in the search, already normalized."""

    palavras: list[str]
    categoria: str
    preco_maximo: float | None
    somente_disponiveis: bool
    quantidade: int | None
    somente_promocao: bool


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
    especificacoes: dict[str, str]
    # Only present when the customer asked for a quantity; the exact stock is never exposed.
    atende_quantidade: bool | None = None
    # Only present when there is an active promotion, which does not stack with the PIX discount.
    observacao_pix: str | None = None
    # The PIX discount ("5%"), present together with preco_pix; the answer may cite it.
    percentual_pix: str | None = None


def formatar_preco(centavos: int) -> str:
    reais, resto = divmod(centavos, 100)
    return f"R$ {reais:,}".replace(",", ".") + f",{resto:02d}"


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFD", texto.casefold())
    return "".join(c for c in sem_acento if not unicodedata.combining(c))


def singularizar(texto: str) -> str:
    """Reduces each normalized word to the singular, so that "violão" matches "Violões"."""
    palavras = []
    for palavra in texto.split():
        if len(palavra) > 3:
            for plural, singular in (("oes", "ao"), ("aes", "ao"), ("ns", "m"), ("s", "")):
                if palavra.endswith(plural):
                    palavra = palavra.removesuffix(plural) + singular
                    break
        palavras.append(palavra)
    return " ".join(palavras)


def _difere_em_ate_um_caractere(a: str, b: str) -> bool:
    """Says whether two words differ by at most one insertion, deletion, or substitution."""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    curta, longa = sorted((a, b), key=len)
    return any(longa[:i] + longa[i + 1 :] == curta for i in range(len(longa)))


def _contem(palavra: str, nome: str) -> bool:
    return palavra in nome


def _palavra_aproximada(palavra: str, nome: str) -> bool:
    """Accepts a typo only in long names; model codes stay exact."""
    if palavra in nome:
        return True
    comprida = len(palavra) >= TAMANHO_MINIMO_PARA_ERRO_DE_DIGITACAO
    return palavra.isalpha() and comprida and any(
        _difere_em_ate_um_caractere(palavra, parte) for parte in nome.split()
    )


def classificar(status: str, estoque: int) -> str:
    # The status takes precedence over the stock.
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


def montar_produto(linha: sqlite3.Row, quantidade: int | None = None) -> Produto:
    desconto = linha["discount_percent"]
    centavos = linha["price_cents"]
    # PIX applies to the list price and does not stack with promotions.
    pix = None if desconto else formatar_preco(aplicar_desconto(centavos, PERCENTUAL_PIX))
    disponibilidade = classificar(linha["status"], linha["stock_quantity"])
    atende = None
    if quantidade is not None:
        atende = disponibilidade == DISPONIVEL and linha["stock_quantity"] >= quantidade
    return Produto(
        linha["product_id"],
        linha["name"],
        linha["categoria"],
        formatar_preco(centavos),
        desconto,
        formatar_preco(calcular_preco_final(linha)),
        pix,
        disponibilidade,
        {
            NOMES_DAS_ESPECIFICACOES.get(chave, chave): VALORES_DAS_ESPECIFICACOES.get(valor, valor)
            for chave, valor in json.loads(linha["specs"]).items()
            if chave not in CAMPOS_DIVERGENTES.get(linha["product_id"], ())
        },
        atende,
        OBSERVACAO_PIX_EM_PROMOCAO if desconto else None,
        None if desconto else f"{PERCENTUAL_PIX}%",
    )


def buscar_produtos(
    connection: sqlite3.Connection,
    termo: str | None = None,
    categoria: str | None = None,
    preco_maximo: float | None = None,
    somente_disponiveis: bool = False,
    quantidade: int | None = None,
    somente_promocao: bool = False,
) -> list[Produto]:
    linhas = connection.execute(
        """
        SELECT p.product_id, p.name, c.name AS categoria, p.price_cents,
               p.stock_quantity, p.status, p.specs, pr.discount_percent
        FROM products p
        JOIN categories c ON c.category_id = p.category_id
        LEFT JOIN promotions pr ON pr.product_id = p.product_id AND pr.is_active = 1
        ORDER BY p.name
        """
    ).fetchall()

    palavras_do_cliente = normalizar(termo or "").split()
    palavras = [p for p in palavras_do_cliente if p not in PALAVRAS_DE_LIGACAO]
    if palavras_do_cliente and not palavras:
        # Only connecting words do not say what the customer is looking for.
        return []
    categoria_normalizada = singularizar(normalizar(categoria or ""))
    filtros = Filtros(
        palavras, categoria_normalizada, preco_maximo, somente_disponiveis, quantidade, somente_promocao
    )
    produtos = _filtrar(linhas, filtros)
    if not produtos and (palavras or categoria_normalizada):
        produtos = _filtrar(linhas, filtros, aproximado=True)
    return produtos


def _filtrar(linhas, filtros: Filtros, aproximado: bool = False):
    produtos = []
    for linha in linhas:
        nome = normalizar(linha["name"])
        categoria_do_produto = singularizar(normalizar(linha["categoria"]))
        palavras_da_categoria = set(categoria_do_produto.split())
        casa = _palavra_aproximada if aproximado else _contem
        # "violão takamine": the category word is not in the product name.
        # "GF3D" and "GF-3D" are the same model: the hyphen does not count in the exact comparison.
        nome_sem_hifen = nome.replace("-", "")
        if not all(
            casa(palavra, nome)
            or _contem(palavra.replace("-", ""), nome_sem_hifen)
            or singularizar(palavra) in palavras_da_categoria
            for palavra in filtros.palavras
        ):
            continue
        # The category also tolerates a typo, but only after the exact comparison.
        if filtros.categoria not in categoria_do_produto and not (
            aproximado
            and all(_palavra_aproximada(palavra, categoria_do_produto) for palavra in filtros.categoria.split())
        ):
            continue
        if filtros.somente_promocao and not linha["discount_percent"]:
            continue
        if (
            filtros.preco_maximo is not None
            and calcular_preco_final(linha) > Decimal(str(filtros.preco_maximo)) * 100
        ):
            continue
        produto = montar_produto(linha, filtros.quantidade)
        if filtros.somente_disponiveis and produto.disponibilidade != DISPONIVEL:
            continue
        produtos.append(produto)
    return produtos


def _linha_de_preco(connection: sqlite3.Connection, produto_id: int) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT p.name, p.price_cents, p.stock_quantity, p.status, pr.discount_percent
        FROM products p
        LEFT JOIN promotions pr ON pr.product_id = p.product_id AND pr.is_active = 1
        WHERE p.product_id = ?
        """,
        (produto_id,),
    ).fetchone()


def preco_final_em_centavos(connection: sqlite3.Connection, produto_id: int) -> int | None:
    linha = _linha_de_preco(connection, produto_id)
    return calcular_preco_final(linha) if linha else None


@dataclass(frozen=True)
class DadosParaConta:
    nome: str
    preco_final: int
    # Paying with PIX: the discount applies to the list price and does not stack with the promotion.
    preco_no_pix: int
    em_promocao: bool
    disponibilidade: str
    estoque: int


def dados_para_conta(connection: sqlite3.Connection, produto_id: int) -> DadosParaConta | None:
    linha = _linha_de_preco(connection, produto_id)
    if linha is None:
        return None
    em_promocao = bool(linha["discount_percent"])
    preco_final = calcular_preco_final(linha)
    return DadosParaConta(
        linha["name"],
        preco_final,
        preco_final if em_promocao else aplicar_desconto(linha["price_cents"], PERCENTUAL_PIX),
        em_promocao,
        classificar(linha["status"], linha["stock_quantity"]),
        linha["stock_quantity"],
    )


def nome_do_produto(connection: sqlite3.Connection, produto_id: int) -> str | None:
    linha = connection.execute(
        "SELECT name FROM products WHERE product_id = ?", (produto_id,)
    ).fetchone()
    return linha["name"] if linha else None
