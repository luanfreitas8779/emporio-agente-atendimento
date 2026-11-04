import re
from collections import defaultdict
from datetime import date
from decimal import Decimal

from src.catalog import normalize

PADRAO_DINHEIRO = re.compile(r"R\$\s*(\d[\d.]*(?:,\d+)?)")
# Amounts written with the word "reais" ("2.199 reais", "2 mil reais") are also money.
PADRAO_REAIS = re.compile(r"(\d[\d.]*(?:,\d+)?)\s*reais\b")
PADRAO_MIL_REAIS = re.compile(r"(?:(\d+(?:,\d+)?)\s*)?\bmil\s*reais\b")
MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}
PADRAO_DATA_EXTENSO = re.compile(r"\b(\d{1,2})º?\s+de\s+(" + "|".join(MESES) + r")(?:\s+de\s+(\d{4}))?\b")
PADRAO_PERCENTUAL = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:%|por cento)")
PADRAO_PERCENTUAL_JSON = re.compile(r'percent(?:ual)?"?\s*:\s*(\d+(?:\.\d+)?)')
PADRAO_RASTREIO = re.compile(r"\b[A-Z]{2,4}\d{7,9}[A-Z]{2}\b")
PADRAO_DATA_BR = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
PADRAO_DATA_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
# "15/12" without a year: we check only the day and the month, as for a date written out.
PADRAO_DATA_CURTA = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?![\d/])")
# "7 horas" means "07:00".
PADRAO_HORAS = re.compile(r"\b([01]?\d|2[0-3])\s*horas\b")
# Times such as "9h", "9h30", "09:00", and "18:00", compared by hour and minute ("HH:MM").
PADRAO_HORARIO = re.compile(r"\b([01]?\d|2[0-3])(?:h([0-5]\d)?|:([0-5]\d))(?!\w)")
# Phone numbers with a hyphen ("3341-4444", "(67) 99654-7821"), compared by the last 8 digits
# so they count with or without the area code.
PADRAO_TELEFONE = re.compile(r"(?:\(?\d{2}\)?[\s.]*)?9?\d{4}-\d{4}")
# "3 unidades", "6 parcelas", "6 vezes", "4x"/"4 x", "restam 3", and "3 em estoque" in the answer;
# "quantidade": 2 in the calculation result.
PADRAO_QUANTIDADE = re.compile(
    r"\b(\d+)\s*(?:unidades?|parcelas?|vezes)\b|\b(\d+)\s*x\b|(?:quantidade|quantity)\W{1,3}(\d+)"
)
# "Restam 3" and "3 em estoque" state the stock, which no tool reports and the customer does not
# confirm: asking for 3 units does not prove that there are 3.
PADRAO_ESTOQUE = re.compile(r"\brestam?\s+(\d+)\b|\b(\d+)\s+(?:no|em)\s+estoque\b")
# "até R$ 1.000": the amount stated as a limit, which the search applied and the answer may repeat.
PADRAO_LIMITE = re.compile(
    r"\b(?:ate|abaixo de|no maximo|maximo de|menos de)\s+r\$\s*(\d[\d.]*(?:,\d+)?)"
)
# Whole number outside amounts in reais and decimals.
PADRAO_NUMERO_SOLTO = re.compile(r"(?<![\d.,$])\b\d+\b(?![.,]?\d)")
# "Semana que vem" and "próxima semana" mean the same; the system does not calculate these dates.
EXPRESSOES_RELATIVAS = {
    "semana que vem": "próxima semana",
    "proxima semana": "próxima semana",
    "mes que vem": "próximo mês",
    "proximo mes": "próximo mês",
}
PADRAO_DATA_RELATIVA = re.compile(r"\b(" + "|".join(EXPRESSOES_RELATIVAS) + r")\b")

# Notice promises the system does not keep (ADR-016): the interest notifies no one.
PADRAO_PROMESSA_DE_AVISO = re.compile(
    r"\bte avis\w*|\bpara avisar\b|\bavis(?:ar|aremos|amos)\s+(?:voce|vc)\b|\bavisaremos\b|\bavisarei\b"
    r"|\bfica(?:ra|r)?\s+sabendo\b|\bvoce\s+(?:sera|vai ser)\s+avisad\w+"
    r"|\bte notific\w*|\bte mando\s+(?:uma\s+)?(?:mensagem|aviso|notificacao)\b"
    r"|\bvamos te\s+(?:informar|comunicar)\s+(?:assim que|quando)\b"
    r"|\bvoce\s+(?:recebera|vai receber)\s+(?:um\s+)?(?:aviso|mensagem|notificacao)\b"
)
# How many characters before the promise to look for a negation ("não posso te avisar").
JANELA_DA_NEGACAO = 25
# The negation only counts next to the promise: "Não se preocupe, te aviso" is still a promise.
PADRAO_NEGACAO = re.compile(r"\b(?:nao|sem)\b[^.,;:!?]*$")


def promete_aviso(resposta: str) -> bool:
    """Says whether the answer promises to notify the customer, not counting when it denies the promise.

    The team's reply after a handoff ("entraremos em contato") is not a notice promise.
    """
    text = normalize(resposta)
    for achado in PADRAO_PROMESSA_DE_AVISO.finditer(text):
        antes = text[max(0, achado.start() - JANELA_DA_NEGACAO) : achado.start()]
        if not PADRAO_NEGACAO.search(antes):
            return True
    return False


def number(text: str) -> Decimal:
    """Reads "2.199,00" or "18,5" as a number."""
    return Decimal(text.replace(".", "").replace(",", "."))


def valores(text: str) -> dict[str, set]:
    """Values in the text by type, in canonical form to compare with the sources.

    Money, time, phone number, and tracking code use the text as it came; dates written out, quantities,
    and relative dates use the text without accents and in lowercase.
    """
    normalizado = normalize(text)
    # In percentages the period and the comma are decimal: "18.5%" and "18,5%" mean 18.5.
    percentuais = {Decimal(p.replace(",", ".")) for p in PADRAO_PERCENTUAL.findall(text)}
    percentuais |= {Decimal(p) for p in PADRAO_PERCENTUAL_JSON.findall(text)}
    found_dates = set()
    for dia, mes, ano in PADRAO_DATA_BR.findall(text):
        found_dates.add(_data(ano, mes, dia))
    for ano, mes, dia in PADRAO_DATA_ISO.findall(text):
        found_dates.add(_data(ano, mes, dia))
    dinheiro = {number(v) for v in PADRAO_DINHEIRO.findall(text)}
    dinheiro |= {number(v) for v in PADRAO_REAIS.findall(text)}
    # "mil reais" without a number means 1.000.
    dinheiro |= {number(v) * 1000 if v else Decimal(1000) for v in PADRAO_MIL_REAIS.findall(text)}
    # "15 de dezembro" has no year: we check only the day and the month ("DD/MM").
    # With the year ("3 de março de 2026"), the full date is checked.
    por_extenso = set()
    for dia, mes, ano in PADRAO_DATA_EXTENSO.findall(normalizado):
        if ano:
            found_dates.add(_data(ano, str(MESES[mes]), dia))
        else:
            por_extenso.add(f"{int(dia):02d}/{MESES[mes]:02d}")
    for dia, mes in PADRAO_DATA_CURTA.findall(text):
        if _data(2000, mes, dia):
            por_extenso.add(f"{int(dia):02d}/{int(mes):02d}")
    horarios = {
        f"{int(hora):02d}:{minuto or minuto_com_pontos or '00'}"
        for hora, minuto, minuto_com_pontos in PADRAO_HORARIO.findall(text)
    }
    horarios |= {f"{int(hora):02d}:00" for hora in PADRAO_HORAS.findall(text)}
    telefones = {"".join(c for c in t if c.isdigit())[-8:] for t in PADRAO_TELEFONE.findall(text)}
    quantities = {
        int(numero_) for achado in PADRAO_QUANTIDADE.findall(normalizado) for numero_ in achado if numero_
    }
    stock = {int(n) for achado in PADRAO_ESTOQUE.findall(normalizado) for n in achado if n}
    relativas = {EXPRESSOES_RELATIVAS[achado] for achado in PADRAO_DATA_RELATIVA.findall(normalizado)}
    return {
        "dinheiro": dinheiro,
        "data_relativa": relativas,
        "quantity": quantities,
        "estoque": stock,
        "horario": horarios,
        "phone": telefones,
        "dia_mes": por_extenso,
        "percentual": percentuais,
        "data": found_dates - {None},
        "rastreio": set(PADRAO_RASTREIO.findall(text)),
    }


def _data(ano: str, mes: str, dia: str) -> date | None:
    try:
        return date(int(ano), int(mes), int(dia))
    except ValueError:
        return None


# These only count if they come from the system: the customer may "state" a price, a discount, opening
# hours, a store phone number, or the stock. Dates, tracking codes, quantities, and relative dates
# stated by the customer may be repeated.
TIPOS_QUE_O_CLIENTE_NAO_CONFIRMA = ("dinheiro", "percentual", "horario", "phone", "estoque")


def valores_nao_confirmados(
    resposta: str,
    fontes: list[str],
    fontes_do_cliente: list[str] | None = None,
    limites_da_busca: list[Decimal] | None = None,
) -> list[str]:
    """Lists the values in the answer that do not appear in the sources.

    The customer's sources do not confirm the types in `TIPOS_QUE_O_CLIENTE_NAO_CONFIRMA`. A price limit
    applied by the search only confirms the amount stated as a limit ("até R$ 1.000,00"), never
    as a price.
    """
    confirmados: defaultdict[str, set] = defaultdict(set)
    for fonte in fontes:
        for tipo, encontrados in valores(fonte).items():
            confirmados[tipo] |= encontrados
    for fonte in fontes_do_cliente or []:
        for tipo, encontrados in valores(fonte).items():
            if tipo not in TIPOS_QUE_O_CLIENTE_NAO_CONFIRMA:
                confirmados[tipo] |= encontrados
        # "Tem 13 Yamaha C40? E 12?": the loose number is also the quantity the customer asked for.
        confirmados["quantity"] |= {int(n) for n in PADRAO_NUMERO_SOLTO.findall(fonte)}
    confirmados["dia_mes"] |= {found_date.strftime("%d/%m") for found_date in confirmados["data"]}
    citados = valores(resposta)
    limites_citados = {number(v) for v in PADRAO_LIMITE.findall(normalize(resposta))}
    confirmados["dinheiro"] |= limites_citados & set(limites_da_busca or [])
    return [
        str(amount)
        for tipo, encontrados in citados.items()
        for amount in sorted(encontrados - confirmados[tipo], key=str)
    ]
