import re
from collections import defaultdict
from datetime import date
from decimal import Decimal

from src.catalog import normalize

MONEY_PATTERN = re.compile(r"R\$\s*(\d[\d.]*(?:,\d+)?)")
# Amounts written with the word "reais" ("2.199 reais", "2 mil reais") are also money.
REAIS_PATTERN = re.compile(r"(\d[\d.]*(?:,\d+)?)\s*reais\b")
THOUSAND_REAIS_PATTERN = re.compile(r"(?:(\d+(?:,\d+)?)\s*)?\bmil\s*reais\b")
MONTHS = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}
WRITTEN_DATE_PATTERN = re.compile(r"\b(\d{1,2})º?\s+de\s+(" + "|".join(MONTHS) + r")(?:\s+de\s+(\d{4}))?\b")
PERCENT_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:%|por cento)")
JSON_PERCENT_PATTERN = re.compile(r'percent(?:ual)?"?\s*:\s*(\d+(?:\.\d+)?)')
TRACKING_PATTERN = re.compile(r"\b[A-Z]{2,4}\d{7,9}[A-Z]{2}\b")
BR_DATE_PATTERN = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
ISO_DATE_PATTERN = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
# "15/12" without a year: we check only the day and the month, as for a date written out.
SHORT_DATE_PATTERN = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?![\d/])")
# "7 horas" means "07:00".
HOURS_PATTERN = re.compile(r"\b([01]?\d|2[0-3])\s*horas\b")
# Times such as "9h", "9h30", "09:00", and "18:00", compared by hour and minute ("HH:MM").
TIME_PATTERN = re.compile(r"\b([01]?\d|2[0-3])(?:h([0-5]\d)?|:([0-5]\d))(?!\w)")
# Phone numbers with a hyphen ("3341-4444", "(67) 99654-7821"), compared by the last 8 digits
# so they count with or without the area code.
PHONE_PATTERN = re.compile(r"(?:\(?\d{2}\)?[\s.]*)?9?\d{4}-\d{4}")
# "3 unidades", "6 parcelas", "6 vezes", "4x"/"4 x", "restam 3", and "3 em estoque" in the answer;
# "quantidade": 2 in the calculation result.
QUANTITY_PATTERN = re.compile(
    r"\b(\d+)\s*(?:unidades?|parcelas?|vezes)\b|\b(\d+)\s*x\b|(?:quantidade|quantity)\W{1,3}(\d+)"
)
# "Restam 3" and "3 em estoque" state the stock, which no tool reports and the customer does not
# confirm: asking for 3 units does not prove that there are 3.
STOCK_PATTERN = re.compile(r"\brestam?\s+(\d+)\b|\b(\d+)\s+(?:no|em)\s+estoque\b")
# "até R$ 1.000": the amount stated as a limit, which the search applied and the answer may repeat.
LIMIT_PATTERN = re.compile(
    r"\b(?:ate|abaixo de|no maximo|maximo de|menos de)\s+r\$\s*(\d[\d.]*(?:,\d+)?)"
)
# Whole number outside amounts in reais and decimals.
LOOSE_NUMBER_PATTERN = re.compile(r"(?<![\d.,$])\b\d+\b(?![.,]?\d)")
# "Semana que vem" and "próxima semana" mean the same; the system does not calculate these dates.
RELATIVE_EXPRESSIONS = {
    "semana que vem": "próxima semana",
    "proxima semana": "próxima semana",
    "mes que vem": "próximo mês",
    "proximo mes": "próximo mês",
}
RELATIVE_DATE_PATTERN = re.compile(r"\b(" + "|".join(RELATIVE_EXPRESSIONS) + r")\b")

# Notice promises the system does not keep (ADR-016): the interest notifies no one.
NOTICE_PROMISE_PATTERN = re.compile(
    r"\bte avis\w*|\bpara avisar\b|\bavis(?:ar|aremos|amos)\s+(?:voce|vc)\b|\bavisaremos\b|\bavisarei\b"
    r"|\bfica(?:ra|r)?\s+sabendo\b|\bvoce\s+(?:sera|vai ser)\s+avisad\w+"
    r"|\bte notific\w*|\bte mando\s+(?:uma\s+)?(?:mensagem|aviso|notificacao)\b"
    r"|\bvamos te\s+(?:informar|comunicar)\s+(?:assim que|quando)\b"
    r"|\bvoce\s+(?:recebera|vai receber)\s+(?:um\s+)?(?:aviso|mensagem|notificacao)\b"
)
# How many characters before the promise to look for a negation ("não posso te avisar").
NEGATION_WINDOW = 25
# The negation only counts next to the promise: "Não se preocupe, te aviso" is still a promise.
NEGATION_PATTERN = re.compile(r"\b(?:nao|sem)\b[^.,;:!?]*$")


def promises_notice(answer: str) -> bool:
    """Says whether the answer promises to notify the customer, not counting when it denies the promise.

    The team's reply after a handoff ("entraremos em contato") is not a notice promise.
    """
    text = normalize(answer)
    for found in NOTICE_PROMISE_PATTERN.finditer(text):
        before = text[max(0, found.start() - NEGATION_WINDOW) : found.start()]
        if not NEGATION_PATTERN.search(before):
            return True
    return False


def number(text: str) -> Decimal:
    """Reads "2.199,00" or "18,5" as a number."""
    return Decimal(text.replace(".", "").replace(",", "."))


def extract_values(text: str) -> dict[str, set]:
    """Values in the text by type, in canonical form to compare with the sources.

    Money, time, phone number, and tracking code use the text as it came; dates written out, quantities,
    and relative dates use the text without accents and in lowercase.
    """
    normalized = normalize(text)
    # In percentages the period and the comma are decimal: "18.5%" and "18,5%" mean 18.5.
    percentages = {Decimal(p.replace(",", ".")) for p in PERCENT_PATTERN.findall(text)}
    percentages |= {Decimal(p) for p in JSON_PERCENT_PATTERN.findall(text)}
    found_dates = set()
    for day, month, year in BR_DATE_PATTERN.findall(text):
        found_dates.add(_date(year, month, day))
    for year, month, day in ISO_DATE_PATTERN.findall(text):
        found_dates.add(_date(year, month, day))
    money = {number(v) for v in MONEY_PATTERN.findall(text)}
    money |= {number(v) for v in REAIS_PATTERN.findall(text)}
    # "mil reais" without a number means 1.000.
    money |= {number(v) * 1000 if v else Decimal(1000) for v in THOUSAND_REAIS_PATTERN.findall(text)}
    # "15 de dezembro" has no year: we check only the day and the month ("DD/MM").
    # With the year ("3 de março de 2026"), the full date is checked.
    written_out = set()
    for day, month, year in WRITTEN_DATE_PATTERN.findall(normalized):
        if year:
            found_dates.add(_date(year, str(MONTHS[month]), day))
        else:
            written_out.add(f"{int(day):02d}/{MONTHS[month]:02d}")
    for day, month in SHORT_DATE_PATTERN.findall(text):
        if _date(2000, month, day):
            written_out.add(f"{int(day):02d}/{int(month):02d}")
    opening_hours = {
        f"{int(hour):02d}:{minute or minute_with_colon or '00'}"
        for hour, minute, minute_with_colon in TIME_PATTERN.findall(text)
    }
    opening_hours |= {f"{int(hour):02d}:00" for hour in HOURS_PATTERN.findall(text)}
    phones = {"".join(c for c in t if c.isdigit())[-8:] for t in PHONE_PATTERN.findall(text)}
    quantities = {
        int(number_) for found in QUANTITY_PATTERN.findall(normalized) for number_ in found if number_
    }
    stock = {int(n) for found in STOCK_PATTERN.findall(normalized) for n in found if n}
    relative = {RELATIVE_EXPRESSIONS[found] for found in RELATIVE_DATE_PATTERN.findall(normalized)}
    return {
        "money": money,
        "relative_date": relative,
        "quantity": quantities,
        "stock": stock,
        "time": opening_hours,
        "phone": phones,
        "day_month": written_out,
        "percent": percentages,
        "date": found_dates - {None},
        "tracking": set(TRACKING_PATTERN.findall(text)),
    }


def _date(year: str, month: str, day: str) -> date | None:
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


# These only count if they come from the system: the customer may "state" a price, a discount, opening
# hours, a store phone number, or the stock. Dates, tracking codes, quantities, and relative dates
# stated by the customer may be repeated.
TYPES_THE_CUSTOMER_CANNOT_CONFIRM = ("money", "percent", "time", "phone", "stock")


def unconfirmed_values(
    answer: str,
    sources: list[str],
    customer_sources: list[str] | None = None,
    search_limits: list[Decimal] | None = None,
) -> list[str]:
    """Lists the values in the answer that do not appear in the sources.

    The customer's sources do not confirm the types in `TYPES_THE_CUSTOMER_CANNOT_CONFIRM`. A price limit
    applied by the search only confirms the amount stated as a limit ("até R$ 1.000,00"), never
    as a price.
    """
    confirmed: defaultdict[str, set] = defaultdict(set)
    for source in sources:
        for kind, found_values in extract_values(source).items():
            confirmed[kind] |= found_values
    for source in customer_sources or []:
        for kind, found_values in extract_values(source).items():
            if kind not in TYPES_THE_CUSTOMER_CANNOT_CONFIRM:
                confirmed[kind] |= found_values
        # "Tem 13 Yamaha C40? E 12?": the loose number is also the quantity the customer asked for.
        confirmed["quantity"] |= {int(n) for n in LOOSE_NUMBER_PATTERN.findall(source)}
    confirmed["day_month"] |= {found_date.strftime("%d/%m") for found_date in confirmed["date"]}
    cited = extract_values(answer)
    cited_limits = {number(v) for v in LIMIT_PATTERN.findall(normalize(answer))}
    confirmed["money"] |= cited_limits & set(search_limits or [])
    return [
        str(amount)
        for kind, found_values in cited.items()
        for amount in sorted(found_values - confirmed[kind], key=str)
    ]
