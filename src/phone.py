CODIGO_DO_PAIS = "55"


def normalizar_telefone(telefone: str) -> str | None:
    """Devolve DDD e número só com dígitos, ou None se não for um telefone brasileiro."""
    digitos = "".join(c for c in telefone if c.isdigit())
    if len(digitos) in (12, 13) and digitos.startswith(CODIGO_DO_PAIS):
        digitos = digitos[len(CODIGO_DO_PAIS) :]
    return digitos if len(digitos) in (10, 11) else None


def formatar_telefone(telefone: str) -> str:
    """"(67) 99654-7821" a partir de qualquer forma digitada, ou vazio se não for um telefone."""
    digitos = normalizar_telefone(telefone)
    return f"({digitos[:2]}) {digitos[2:-4]}-{digitos[-4:]}" if digitos else ""
