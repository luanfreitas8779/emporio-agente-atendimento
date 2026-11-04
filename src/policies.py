from functools import cache
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from src.catalog import format_price
from src.config import DATA_DIR

POLICIES_FILE = DATA_DIR / "politicas.md"

SECTIONS = (
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

MAX_INSTALLMENTS = 12


@cache
def read_sections(file: Path) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = None
    for row in file.read_text(encoding="utf-8").splitlines():
        if row.startswith("## "):
            current = row[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(row)
    return {name: "\n".join(rows).strip() for name, rows in sections.items()}


def minimum_installment_cents(installments: int) -> int:
    if installments <= 3:
        return 5000
    if installments <= 6:
        return 8000
    return 10000


def meets_minimum_installment(amount_in_cents: int, installments: int) -> bool:
    return amount_in_cents >= minimum_installment_cents(installments) * installments


def installment_amount(amount_in_cents: int, installments: int) -> str:
    cents = (Decimal(amount_in_cents) / installments).quantize(Decimal(1), ROUND_HALF_UP)
    return format_price(int(cents))


def describe_installments(amount: float, installments: int | None) -> str:
    if amount <= 0 or (installments is not None and installments < 1):
        raise ValueError("The amount and the number of installments must be positive.")
    cents = int((Decimal(str(amount)) * 100).quantize(Decimal(1), ROUND_HALF_UP))
    maximum = max(
        (n for n in range(1, MAX_INSTALLMENTS + 1) if n == 1 or meets_minimum_installment(cents, n)),
    )
    rows = [
        f"Para {format_price(cents)}, o parcelamento sem juros tem "
        f"máximo de {maximum}x de {installment_amount(cents, maximum)}."
    ]
    if installments is not None:
        if installments > MAX_INSTALLMENTS:
            rows.append(
                f"{installments}x não é possível: o parcelamento vai até {MAX_INSTALLMENTS}x."
            )
        elif installments == 1 or meets_minimum_installment(cents, installments):
            rows.append(f"{installments}x atende à parcela mínima.")
        else:
            minimum = format_price(minimum_installment_cents(installments))
            rows.append(f"{installments}x não atende à parcela mínima de {minimum}.")
    return "\n".join(rows)


def get_policies(
    section: str, amount: float | None = None, installments: int | None = None
) -> str:
    if section not in SECTIONS:
        raise ValueError(f"Unknown section: {section}. Use one of {', '.join(SECTIONS)}.")
    text = read_sections(POLICIES_FILE)[section]
    if section == "pagamentos" and amount is not None:
        text += "\n\nCálculo para esta compra:\n" + describe_installments(amount, installments)
    return text
