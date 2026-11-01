import re
from datetime import date
from decimal import Decimal

from src.catalog import normalizar

PADRAO_DINHEIRO = re.compile(r"R\$\s*(\d[\d.]*(?:,\d+)?)")
PADRAO_PERCENTUAL = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
PADRAO_PERCENTUAL_JSON = re.compile(r'percentual"?\s*:\s*(\d+(?:\.\d+)?)')
PADRAO_RASTREIO = re.compile(r"\b[A-Z]{2,4}\d{7,9}[A-Z]{2}\b")
PADRAO_DATA_BR = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
PADRAO_DATA_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

# Promessas de aviso que o sistema não cumpre (ADR-016): o interesse não notifica ninguém.
PADRAO_PROMESSA_DE_AVISO = re.compile(
    r"\bte avis\w*|\bavis(?:ar|aremos|amos)\s+(?:voce|vc)\b|\bavisaremos\b"
    r"|\bfica(?:ra|r)?\s+sabendo\b|\bvoce\s+(?:sera|vai ser)\s+avisad\w+"
    r"|\bentra(?:remos|mos)\s+em\s+contato\b"
)


def promete_aviso(resposta: str) -> bool:
    """Diz se a resposta promete avisar o cliente, sem contar quando nega a promessa."""
    texto = normalizar(resposta)
    for achado in PADRAO_PROMESSA_DE_AVISO.finditer(texto):
        antes = texto[max(0, achado.start() - 25) : achado.start()]
        if not re.search(r"\b(?:nao|sem)\b", antes):
            return True
    return False


def numero(texto: str) -> Decimal:
    """Lê "2.199,00" ou "18,5" como número."""
    return Decimal(texto.replace(".", "").replace(",", "."))


def valores(texto: str) -> dict[str, set]:
    percentuais = {numero(p) for p in PADRAO_PERCENTUAL.findall(texto)}
    percentuais |= {Decimal(p) for p in PADRAO_PERCENTUAL_JSON.findall(texto)}
    datas = set()
    for dia, mes, ano in PADRAO_DATA_BR.findall(texto):
        datas.add(_data(ano, mes, dia))
    for ano, mes, dia in PADRAO_DATA_ISO.findall(texto):
        datas.add(_data(ano, mes, dia))
    return {
        "dinheiro": {numero(v) for v in PADRAO_DINHEIRO.findall(texto)},
        "percentual": percentuais,
        "data": datas - {None},
        "rastreio": set(PADRAO_RASTREIO.findall(texto)),
    }


def _data(ano: str, mes: str, dia: str) -> date | None:
    try:
        return date(int(ano), int(mes), int(dia))
    except ValueError:
        return None


def valores_nao_confirmados(resposta: str, fontes: list[str]) -> list[str]:
    """Lista os valores da resposta que não aparecem em nenhuma das fontes."""
    confirmados: dict[str, set] = {tipo: set() for tipo in ("dinheiro", "percentual", "data", "rastreio")}
    for fonte in fontes:
        for tipo, encontrados in valores(fonte).items():
            confirmados[tipo] |= encontrados
    citados = valores(resposta)
    return [
        str(valor)
        for tipo, encontrados in citados.items()
        for valor in sorted(encontrados - confirmados[tipo], key=str)
    ]
