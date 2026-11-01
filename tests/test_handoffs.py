import pytest

from src.handoffs import Motivo, Resultado, registrar

TELEFONE = "(67) 99654-7821"
RESUMO = "Cliente relata que o violão chegou com defeito no braço."


def encaminhamentos(conexao):
    return [
        tuple(linha)
        for linha in conexao.execute("SELECT phone, reason, summary FROM handoffs ORDER BY id")
    ]


def test_registra_a_reclamacao_com_telefone_motivo_e_resumo(conexao):
    resultado = registrar(conexao, TELEFONE, Motivo.RECLAMACAO, RESUMO)

    assert resultado == Resultado.REGISTRADO
    assert encaminhamentos(conexao) == [("67996547821", "reclamacao", RESUMO)]


@pytest.mark.parametrize("resumo", ["", "   ", "\n\t"])
def test_resumo_vazio_nao_grava_encaminhamento(conexao, resumo):
    resultado = registrar(conexao, TELEFONE, Motivo.RECLAMACAO, resumo)

    assert resultado == Resultado.RESUMO_INVALIDO
    assert encaminhamentos(conexao) == []
