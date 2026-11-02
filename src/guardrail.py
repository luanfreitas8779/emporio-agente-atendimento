import re
from collections import defaultdict
from datetime import date
from decimal import Decimal

from src.catalog import normalizar

PADRAO_DINHEIRO = re.compile(r"R\$\s*(\d[\d.]*(?:,\d+)?)")
# Valores escritos com a palavra "reais" ("2.199 reais", "2 mil reais") também são dinheiro.
PADRAO_REAIS = re.compile(r"(\d[\d.]*(?:,\d+)?)\s*reais\b")
PADRAO_MIL_REAIS = re.compile(r"(?:(\d+(?:,\d+)?)\s*)?\bmil\s*reais\b")
MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}
PADRAO_DATA_EXTENSO = re.compile(r"\b(\d{1,2})º?\s+de\s+(" + "|".join(MESES) + r")(?:\s+de\s+(\d{4}))?\b")
PADRAO_PERCENTUAL = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:%|por cento)")
PADRAO_PERCENTUAL_JSON = re.compile(r'percentual"?\s*:\s*(\d+(?:\.\d+)?)')
PADRAO_RASTREIO = re.compile(r"\b[A-Z]{2,4}\d{7,9}[A-Z]{2}\b")
PADRAO_DATA_BR = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
PADRAO_DATA_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
# "15/12" sem ano: conferimos só o dia e o mês, como na data por extenso.
PADRAO_DATA_CURTA = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?![\d/])")
# "7 horas" vale "07:00".
PADRAO_HORAS = re.compile(r"\b([01]?\d|2[0-3])\s*horas\b")
# Horários como "9h", "9h30", "09:00" e "18:00", comparados por hora e minuto ("HH:MM").
PADRAO_HORARIO = re.compile(r"\b([01]?\d|2[0-3])(?:h([0-5]\d)?|:([0-5]\d))(?!\w)")
# Telefones com hífen ("3341-4444", "(67) 99654-7821"), comparados pelos 8 últimos dígitos
# para valer com ou sem DDD.
PADRAO_TELEFONE = re.compile(r"(?:\(?\d{2}\)?[\s.]*)?9?\d{4}-\d{4}")
# "3 unidades", "6 parcelas", "6 vezes", "4x"/"4 x", "restam 3" e "3 em estoque" na resposta;
# "quantidade": 2 no retorno da conta.
PADRAO_QUANTIDADE = re.compile(
    r"\b(\d+)\s*(?:unidades?|parcelas?|vezes)\b|\b(\d+)\s*x\b|quantidade\W{1,3}(\d+)"
    r"|\brestam?\s+(\d+)\b|\b(\d+)\s+(?:no|em)\s+estoque\b"
)
# "Semana que vem" e "próxima semana" valem o mesmo; o sistema não calcula essas datas.
EXPRESSOES_RELATIVAS = {
    "semana que vem": "próxima semana",
    "proxima semana": "próxima semana",
    "mes que vem": "próximo mês",
    "proximo mes": "próximo mês",
}
PADRAO_DATA_RELATIVA = re.compile(r"\b(" + "|".join(EXPRESSOES_RELATIVAS) + r")\b")

# Promessas de aviso que o sistema não cumpre (ADR-016): o interesse não notifica ninguém.
PADRAO_PROMESSA_DE_AVISO = re.compile(
    r"\bte avis\w*|\bavis(?:ar|aremos|amos)\s+(?:voce|vc)\b|\bavisaremos\b"
    r"|\bfica(?:ra|r)?\s+sabendo\b|\bvoce\s+(?:sera|vai ser)\s+avisad\w+"
)
# Quantos caracteres antes da promessa procurar uma negação ("não posso te avisar").
JANELA_DA_NEGACAO = 25


def promete_aviso(resposta: str) -> bool:
    """Diz se a resposta promete avisar o cliente, sem contar quando nega a promessa.

    O retorno da equipe após um encaminhamento ("entraremos em contato") não é promessa de aviso.
    """
    texto = normalizar(resposta)
    for achado in PADRAO_PROMESSA_DE_AVISO.finditer(texto):
        antes = texto[max(0, achado.start() - JANELA_DA_NEGACAO) : achado.start()]
        if not re.search(r"\b(?:nao|sem)\b", antes):
            return True
    return False


def numero(texto: str) -> Decimal:
    """Lê "2.199,00" ou "18,5" como número."""
    return Decimal(texto.replace(".", "").replace(",", "."))


def valores(texto: str) -> dict[str, set]:
    """Valores do texto por tipo, em formato canônico para comparar com as fontes.

    Dinheiro, horário, telefone e rastreio usam o texto como veio; datas por extenso, quantidades
    e datas relativas usam o texto sem acento e em minúsculas.
    """
    normalizado = normalizar(texto)
    # Em percentual o ponto e a vírgula são decimais: "18.5%" e "18,5%" valem 18,5.
    percentuais = {Decimal(p.replace(",", ".")) for p in PADRAO_PERCENTUAL.findall(texto)}
    percentuais |= {Decimal(p) for p in PADRAO_PERCENTUAL_JSON.findall(texto)}
    datas = set()
    for dia, mes, ano in PADRAO_DATA_BR.findall(texto):
        datas.add(_data(ano, mes, dia))
    for ano, mes, dia in PADRAO_DATA_ISO.findall(texto):
        datas.add(_data(ano, mes, dia))
    dinheiro = {numero(v) for v in PADRAO_DINHEIRO.findall(texto)}
    dinheiro |= {numero(v) for v in PADRAO_REAIS.findall(texto)}
    # "mil reais" sem número vale 1.000.
    dinheiro |= {numero(v) * 1000 if v else Decimal(1000) for v in PADRAO_MIL_REAIS.findall(texto)}
    # "15 de dezembro" não traz o ano: conferimos só o dia e o mês ("DD/MM").
    # Com o ano ("3 de março de 2026"), a data inteira é conferida.
    por_extenso = set()
    for dia, mes, ano in PADRAO_DATA_EXTENSO.findall(normalizado):
        if ano:
            datas.add(_data(ano, str(MESES[mes]), dia))
        else:
            por_extenso.add(f"{int(dia):02d}/{MESES[mes]:02d}")
    for dia, mes in PADRAO_DATA_CURTA.findall(texto):
        if _data(2000, mes, dia):
            por_extenso.add(f"{int(dia):02d}/{int(mes):02d}")
    horarios = {
        f"{int(hora):02d}:{minuto or minuto_com_pontos or '00'}"
        for hora, minuto, minuto_com_pontos in PADRAO_HORARIO.findall(texto)
    }
    horarios |= {f"{int(hora):02d}:00" for hora in PADRAO_HORAS.findall(texto)}
    telefones = {"".join(c for c in t if c.isdigit())[-8:] for t in PADRAO_TELEFONE.findall(texto)}
    quantidades = {
        int(numero_) for achado in PADRAO_QUANTIDADE.findall(normalizado) for numero_ in achado if numero_
    }
    relativas = {EXPRESSOES_RELATIVAS[achado] for achado in PADRAO_DATA_RELATIVA.findall(normalizado)}
    return {
        "dinheiro": dinheiro,
        "data_relativa": relativas,
        "quantidade": quantidades,
        "horario": horarios,
        "telefone": telefones,
        "dia_mes": por_extenso,
        "percentual": percentuais,
        "data": datas - {None},
        "rastreio": set(PADRAO_RASTREIO.findall(texto)),
    }


def _data(ano: str, mes: str, dia: str) -> date | None:
    try:
        return date(int(ano), int(mes), int(dia))
    except ValueError:
        return None


# Só valem se vierem do sistema: o cliente pode "ditar" um preço, um desconto, um horário de
# funcionamento ou um telefone da loja. Datas, rastreios, quantidades e datas relativas ditados
# por ele podem ser repetidos.
TIPOS_QUE_O_CLIENTE_NAO_CONFIRMA = ("dinheiro", "percentual", "horario", "telefone")


def valores_nao_confirmados(
    resposta: str, fontes: list[str], fontes_do_cliente: list[str] | None = None
) -> list[str]:
    """Lista os valores da resposta que não aparecem nas fontes.

    As fontes do cliente não confirmam os tipos de `TIPOS_QUE_O_CLIENTE_NAO_CONFIRMA`.
    """
    confirmados: defaultdict[str, set] = defaultdict(set)
    for fonte in fontes:
        for tipo, encontrados in valores(fonte).items():
            confirmados[tipo] |= encontrados
    for fonte in fontes_do_cliente or []:
        for tipo, encontrados in valores(fonte).items():
            if tipo not in TIPOS_QUE_O_CLIENTE_NAO_CONFIRMA:
                confirmados[tipo] |= encontrados
    confirmados["dia_mes"] |= {data.strftime("%d/%m") for data in confirmados["data"]}
    citados = valores(resposta)
    return [
        str(valor)
        for tipo, encontrados in citados.items()
        for valor in sorted(encontrados - confirmados[tipo], key=str)
    ]
