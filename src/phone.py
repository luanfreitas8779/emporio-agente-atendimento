CODIGO_DO_PAIS = "55"


def normalizar_telefone(telefone: str) -> str | None:
    """Returns the area code and number as digits only, or None if it is not a Brazilian phone number."""
    digitos = "".join(c for c in telefone if c.isdigit())
    if len(digitos) in (12, 13) and digitos.startswith(CODIGO_DO_PAIS):
        digitos = digitos[len(CODIGO_DO_PAIS) :]
    return digitos if len(digitos) in (10, 11) else None


def formatar_telefone(telefone: str) -> str:
    """"(67) 99654-7821" from any typed form, or empty if it is not a phone number."""
    digitos = normalizar_telefone(telefone)
    return f"({digitos[:2]}) {digitos[2:-4]}-{digitos[-4:]}" if digitos else ""
