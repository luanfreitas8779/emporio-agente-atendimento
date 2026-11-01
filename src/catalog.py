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
# Campos que o cadastro contradiz em outra coluna (DQ-05); o modelo não deve afirmá-los.
CAMPOS_DIVERGENTES = {137: {"strings"}}
TAMANHO_MINIMO_PARA_ERRO_DE_DIGITACAO = 5
# Palavras de ligação que o cliente escreve e que não fazem parte de nenhum nome.
PALAVRAS_DE_LIGACAO = {"a", "as", "o", "os", "um", "uma", "da", "das", "de", "do", "dos", "com", "para", "pra", "no", "na", "em"}


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
    # Só existe quando o cliente pediu uma quantidade; o estoque exato nunca é exposto.
    atende_quantidade: bool | None = None


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


def _difere_em_ate_um_caractere(a: str, b: str) -> bool:
    """Diz se duas palavras diferem em no máximo uma inserção, remoção ou troca."""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    curta, longa = sorted((a, b), key=len)
    return any(longa[:i] + longa[i + 1 :] == curta for i in range(len(longa)))


def _contem(palavra: str, nome: str) -> bool:
    return palavra in nome


def _palavra_aproximada(palavra: str, nome: str) -> bool:
    """Aceita um erro de digitação só em nomes longos; códigos de modelo ficam exatos."""
    if palavra in nome:
        return True
    comprida = len(palavra) >= TAMANHO_MINIMO_PARA_ERRO_DE_DIGITACAO
    return palavra.isalpha() and comprida and any(
        _difere_em_ate_um_caractere(palavra, parte) for parte in nome.split()
    )


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


def montar_produto(linha: sqlite3.Row, quantidade: int | None = None) -> Produto:
    desconto = linha["discount_percent"]
    centavos = linha["price_cents"]
    # O PIX incide sobre o preço de tabela e não se soma a promoções.
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
            chave: valor
            for chave, valor in json.loads(linha["specs"]).items()
            if chave not in CAMPOS_DIVERGENTES.get(linha["product_id"], ())
        },
        atende,
    )


def buscar_produtos(
    conexao: sqlite3.Connection,
    termo: str | None = None,
    categoria: str | None = None,
    preco_maximo: float | None = None,
    somente_disponiveis: bool = False,
    quantidade: int | None = None,
) -> list[Produto]:
    linhas = conexao.execute(
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
        # Só palavras de ligação não dizem o que o cliente procura.
        return []
    categoria_normalizada = singularizar(normalizar(categoria or ""))
    produtos = _filtrar(
        linhas, palavras, categoria_normalizada, preco_maximo, somente_disponiveis, quantidade
    )
    if not produtos and palavras:
        produtos = _filtrar(
            linhas, palavras, categoria_normalizada, preco_maximo, somente_disponiveis, quantidade, aproximado=True
        )
    return produtos


def _filtrar(
    linhas, palavras, categoria_normalizada, preco_maximo, somente_disponiveis, quantidade, aproximado=False
):
    produtos = []
    for linha in linhas:
        nome = normalizar(linha["name"])
        categoria_do_produto = singularizar(normalizar(linha["categoria"]))
        casa = _palavra_aproximada if aproximado else _contem
        # "violão takamine": a palavra da categoria não está no nome do produto.
        # "GF3D" e "GF-3D" são o mesmo modelo: o hífen não conta na comparação exata.
        nome_sem_hifen = nome.replace("-", "")
        if not all(
            casa(palavra, nome)
            or _contem(palavra.replace("-", ""), nome_sem_hifen)
            or singularizar(palavra) in categoria_do_produto
            for palavra in palavras
        ):
            continue
        if categoria_normalizada not in categoria_do_produto:
            continue
        if preco_maximo is not None and calcular_preco_final(linha) > Decimal(str(preco_maximo)) * 100:
            continue
        produto = montar_produto(linha, quantidade)
        if somente_disponiveis and produto.disponibilidade != DISPONIVEL:
            continue
        produtos.append(produto)
    return produtos


def nome_do_produto(conexao: sqlite3.Connection, produto_id: int) -> str | None:
    linha = conexao.execute(
        "SELECT name FROM products WHERE product_id = ?", (produto_id,)
    ).fetchone()
    return linha["name"] if linha else None
