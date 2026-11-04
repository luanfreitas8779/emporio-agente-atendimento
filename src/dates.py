from datetime import date


def format_date(value: date | str | None) -> str | None:
    """Dates shown to the customer are formatted in code, in the Brazilian format (ADR-012)."""
    if value is None:
        return None
    if isinstance(value, str):
        value = date.fromisoformat(value)
    return value.strftime("%d/%m/%Y")


WEEKDAYS = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)


def weekday_name(value: date) -> str:
    return WEEKDAYS[value.weekday()]
