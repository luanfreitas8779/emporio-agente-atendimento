CODIGO_DO_PAIS = "55"


def normalizar_telefone(telefone: str) -> str | None:
    """Devolve DDD e número só com dígitos, ou None se não for um telefone brasileiro."""
    digitos = "".join(c for c in telefone if c.isdigit())
    if len(digitos) in (12, 13) and digitos.startswith(CODIGO_DO_PAIS):
        digitos = digitos[len(CODIGO_DO_PAIS) :]
    return digitos if len(digitos) in (10, 11) else None
