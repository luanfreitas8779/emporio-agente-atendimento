from functools import cache
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from src.catalog import formatar_preco
from src.config import PASTA_DADOS

ARQUIVO_POLITICAS = PASTA_DADOS / "politicas.md"

SECOES = (
    "sobre_a_loja",
    "horarios",
    "pagamentos",
    "trocas_e_devolucoes",
    "entregas",
    "promocoes",
    "atendimento",
    "garantia",
    "privacidade",
)

MAXIMO_DE_PARCELAS = 12


@cache
def ler_secoes(arquivo: Path) -> dict[str, str]:
    secoes: dict[str, list[str]] = {}
    atual = None
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        if linha.startswith("## "):
            atual = linha[3:].strip()
            secoes[atual] = []
        elif atual is not None:
            secoes[atual].append(linha)
    return {nome: "\n".join(linhas).strip() for nome, linhas in secoes.items()}


def parcela_minima_em_centavos(parcelas: int) -> int:
    if parcelas <= 3:
        return 5000
    if parcelas <= 6:
        return 8000
    return 10000


def atende_parcela_minima(valor_em_centavos: int, parcelas: int) -> bool:
    return valor_em_centavos >= parcela_minima_em_centavos(parcelas) * parcelas


def valor_da_parcela(valor_em_centavos: int, parcelas: int) -> str:
    centavos = (Decimal(valor_em_centavos) / parcelas).quantize(Decimal(1), ROUND_HALF_UP)
    return formatar_preco(int(centavos))


def descrever_parcelamento(valor: float, parcelas: int | None) -> str:
    if valor <= 0 or (parcelas is not None and parcelas < 1):
        raise ValueError("O valor e o número de parcelas devem ser positivos.")
    centavos = int((Decimal(str(valor)) * 100).quantize(Decimal(1), ROUND_HALF_UP))
    maximo = max(
        (n for n in range(1, MAXIMO_DE_PARCELAS + 1) if n == 1 or atende_parcela_minima(centavos, n)),
    )
    linhas = [
        f"Para {formatar_preco(centavos)}, o parcelamento sem juros tem "
        f"máximo de {maximo}x de {valor_da_parcela(centavos, maximo)}."
    ]
    if parcelas is not None:
        if parcelas > MAXIMO_DE_PARCELAS:
            linhas.append(
                f"{parcelas}x não é possível: o parcelamento vai até {MAXIMO_DE_PARCELAS}x."
            )
        elif parcelas == 1 or atende_parcela_minima(centavos, parcelas):
            linhas.append(f"{parcelas}x atende à parcela mínima.")
        else:
            minima = formatar_preco(parcela_minima_em_centavos(parcelas))
            linhas.append(f"{parcelas}x não atende à parcela mínima de {minima}.")
    return "\n".join(linhas)


def consultar_politicas(
    secao: str, valor: float | None = None, parcelas: int | None = None
) -> str:
    if secao not in SECOES:
        raise ValueError(f"Seção desconhecida: {secao}. Use uma de {', '.join(SECOES)}.")
    texto = ler_secoes(ARQUIVO_POLITICAS)[secao]
    if secao == "pagamentos" and valor is not None:
        texto += "\n\nCálculo para esta compra:\n" + descrever_parcelamento(valor, parcelas)
    return texto
