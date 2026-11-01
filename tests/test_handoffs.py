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


@pytest.mark.parametrize("telefone", ["", "12345", "abc"])
def test_telefone_invalido_nao_grava_encaminhamento(conexao, telefone):
    resultado = registrar(conexao, telefone, Motivo.RECLAMACAO, RESUMO)

    assert resultado == Resultado.TELEFONE_INVALIDO
    assert encaminhamentos(conexao) == []


def test_repetir_o_mesmo_encaminhamento_nao_duplica(conexao):
    registrar(conexao, TELEFONE, Motivo.RECLAMACAO, RESUMO)

    resultado = registrar(conexao, "67996547821", Motivo.RECLAMACAO, f"  {RESUMO} ")

    assert resultado == Resultado.JA_REGISTRADO
    assert len(encaminhamentos(conexao)) == 1


def test_motivo_ou_resumo_diferente_gera_novo_encaminhamento(conexao):
    registrar(conexao, TELEFONE, Motivo.RECLAMACAO, RESUMO)

    registrar(conexao, TELEFONE, Motivo.ATENDENTE_SOLICITADO, RESUMO)
    registrar(conexao, TELEFONE, Motivo.RECLAMACAO, "Outro assunto.")

    assert len(encaminhamentos(conexao)) == 3
