from datetime import datetime, timedelta, timezone

import pytest

from src.handoffs import Motivo, Resultado, registrar

TELEFONE = "(67) 99654-7821"
RESUMO = "Cliente relata que o violão chegou com defeito no braço."


def encaminhamentos(connection):
    return [
        tuple(row)
        for row in connection.execute("SELECT phone, reason, summary FROM handoffs ORDER BY id")
    ]


def test_registra_a_reclamacao_com_telefone_motivo_e_resumo(connection):
    resultado = registrar(connection, TELEFONE, Motivo.RECLAMACAO, RESUMO)

    assert resultado == Resultado.REGISTRADO
    assert encaminhamentos(connection) == [("67996547821", "reclamacao", RESUMO)]


@pytest.mark.parametrize("resumo", ["", "   ", "\n\t"])
def test_resumo_vazio_nao_grava_encaminhamento(connection, resumo):
    resultado = registrar(connection, TELEFONE, Motivo.RECLAMACAO, resumo)

    assert resultado == Resultado.RESUMO_INVALIDO
    assert encaminhamentos(connection) == []


@pytest.mark.parametrize("phone", ["", "12345", "abc"])
def test_telefone_invalido_nao_grava_encaminhamento(connection, phone):
    resultado = registrar(connection, phone, Motivo.RECLAMACAO, RESUMO)

    assert resultado == Resultado.TELEFONE_INVALIDO
    assert encaminhamentos(connection) == []


def test_repetir_o_mesmo_encaminhamento_nao_duplica(connection):
    registrar(connection, TELEFONE, Motivo.RECLAMACAO, RESUMO)

    resultado = registrar(connection, "67996547821", Motivo.RECLAMACAO, f"  {RESUMO} ")

    assert resultado == Resultado.JA_REGISTRADO
    assert len(encaminhamentos(connection)) == 1


def test_motivo_diferente_gera_novo_encaminhamento(connection):
    registrar(connection, TELEFONE, Motivo.RECLAMACAO, RESUMO)

    registrar(connection, TELEFONE, Motivo.ATENDENTE_SOLICITADO, RESUMO)

    assert len(encaminhamentos(connection)) == 2


def test_outro_cliente_com_o_mesmo_motivo_gera_novo_encaminhamento(connection):
    registrar(connection, TELEFONE, Motivo.RECLAMACAO, RESUMO)

    registrar(connection, "(67) 99789-0123", Motivo.RECLAMACAO, "Outro assunto.")

    assert len(encaminhamentos(connection)) == 2


def test_resumo_acima_de_500_caracteres_e_cortado(connection):
    resultado = registrar(connection, TELEFONE, Motivo.RECLAMACAO, "a" * 600)

    assert resultado == Resultado.REGISTRADO
    assert encaminhamentos(connection)[0][2] == "a" * 500


@pytest.fixture
def relogio(monkeypatch):
    """Controlled clock: `relogio.em(minutos)` sets the moment of the next registration."""
    inicio = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)

    class Relogio:
        def em(self, minutos: int) -> None:
            instante = (inicio + timedelta(minutes=minutos)).isoformat()
            monkeypatch.setattr("src.handoffs.agora", lambda: instante)

    return Relogio()


@pytest.mark.regression
def test_mesmo_motivo_do_mesmo_cliente_na_janela_nao_gera_outro_registro_com_resumo_diferente(connection, relogio):
    relogio.em(0)
    registrar(connection, TELEFONE, Motivo.ATENDENTE_SOLICITADO, "Cliente quer falar com humano sobre o pedido 7.")

    relogio.em(30)
    resultado = registrar(connection, TELEFONE, Motivo.ATENDENTE_SOLICITADO, "Cliente exige atendente por causa do atraso.")

    assert resultado == Resultado.JA_REGISTRADO
    assert len(encaminhamentos(connection)) == 1


@pytest.mark.regression
def test_depois_da_janela_o_mesmo_motivo_gera_novo_registro(connection, relogio):
    relogio.em(0)
    registrar(connection, TELEFONE, Motivo.RECLAMACAO, "Violão chegou com defeito.")

    relogio.em(61)
    resultado = registrar(connection, TELEFONE, Motivo.RECLAMACAO, "Cabo veio sem o conector.")

    assert resultado == Resultado.REGISTRADO
    assert len(encaminhamentos(connection)) == 2


@pytest.mark.regression
def test_reclamacao_sobre_outro_assunto_na_janela_gera_novo_registro(connection, relogio):
    relogio.em(0)
    registrar(connection, TELEFONE, Motivo.RECLAMACAO, "Cliente reclama que o pedido 8 atrasou.")

    relogio.em(10)
    resultado = registrar(
        connection, TELEFONE, Motivo.RECLAMACAO, "Cliente diz que o vendedor da loja a destratou ontem."
    )

    assert resultado == Resultado.REGISTRADO
    assert len(encaminhamentos(connection)) == 2


@pytest.mark.regression
def test_reclamacao_sobre_outro_pedido_na_janela_gera_novo_registro(connection, relogio):
    relogio.em(0)
    registrar(connection, TELEFONE, Motivo.RECLAMACAO, "Cliente insatisfeita: o pedido 8 chegou atrasado.")

    relogio.em(10)
    resultado = registrar(connection, TELEFONE, Motivo.RECLAMACAO, "Cliente insatisfeita: o pedido 12 chegou atrasado.")

    assert resultado == Resultado.REGISTRADO
    assert len(encaminhamentos(connection)) == 2


@pytest.mark.regression
def test_reclamacao_reescrita_sobre_o_mesmo_pedido_na_janela_nao_gera_outro_registro(connection, relogio):
    relogio.em(0)
    registrar(connection, TELEFONE, Motivo.RECLAMACAO, "Cliente insatisfeita: o pedido 8 atrasou.")

    relogio.em(10)
    resultado = registrar(connection, TELEFONE, Motivo.RECLAMACAO, "Reclamação do pedido 8, que chegou fora do prazo.")

    assert resultado == Resultado.JA_REGISTRADO
    assert len(encaminhamentos(connection)) == 1


@pytest.mark.regression
def test_atendente_solicitado_com_resumos_sem_relacao_na_janela_continua_um_registro(connection, relogio):
    relogio.em(0)
    registrar(connection, TELEFONE, Motivo.ATENDENTE_SOLICITADO, "Cliente quer falar com um atendente.")

    relogio.em(5)
    resultado = registrar(connection, TELEFONE, Motivo.ATENDENTE_SOLICITADO, "Solicitação de contato humano sobre troca de violão.")

    assert resultado == Resultado.JA_REGISTRADO
    assert len(encaminhamentos(connection)) == 1


@pytest.mark.regression
def test_verbo_de_reclamacao_em_comum_nao_faz_dois_assuntos_virarem_um(connection, relogio):
    relogio.em(0)
    registrar(connection, TELEFONE, Motivo.RECLAMACAO, "Cliente reclama que o pedido 8 atrasou.")

    relogio.em(10)
    resultado = registrar(connection, TELEFONE, Motivo.RECLAMACAO, "Cliente reclama que o vendedor a destratou.")

    assert resultado == Resultado.REGISTRADO
