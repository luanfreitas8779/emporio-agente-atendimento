import pytest

from src.phone import formatar_telefone


@pytest.mark.parametrize(
    "digitado, esperado",
    [
        ("67996547821", "(67) 99654-7821"),
        ("(67) 99654-7821", "(67) 99654-7821"),
        ("+55 67 99654-7821", "(67) 99654-7821"),
        ("6733414444", "(67) 3341-4444"),
        ("123", ""),
        ("", ""),
    ],
)
def test_formata_o_telefone_a_partir_de_qualquer_forma_digitada(digitado, esperado):
    assert formatar_telefone(digitado) == esperado
