from datetime import datetime, timedelta, timezone

import pytest

from src.handoffs import Reason, Result, register

PHONE = "(67) 99654-7821"
RESUMO = "Cliente relata que o violão chegou com defeito no braço."


def encaminhamentos(connection):
    return [
        tuple(row)
        for row in connection.execute("SELECT phone, reason, summary FROM handoffs ORDER BY id")
    ]


def test_registra_a_reclamacao_com_telefone_motivo_e_resumo(connection):
    result = register(connection, PHONE, Reason.RECLAMACAO, RESUMO)

    assert result == Result.REGISTERED
    assert encaminhamentos(connection) == [("67996547821", "reclamacao", RESUMO)]


@pytest.mark.parametrize("resumo", ["", "   ", "\n\t"])
def test_resumo_vazio_nao_grava_encaminhamento(connection, resumo):
    result = register(connection, PHONE, Reason.RECLAMACAO, resumo)

    assert result == Result.RESUMO_INVALIDO
    assert encaminhamentos(connection) == []


@pytest.mark.parametrize("phone", ["", "12345", "abc"])
def test_telefone_invalido_nao_grava_encaminhamento(connection, phone):
    result = register(connection, phone, Reason.RECLAMACAO, RESUMO)

    assert result == Result.INVALID_PHONE
    assert encaminhamentos(connection) == []


def test_repetir_o_mesmo_encaminhamento_nao_duplica(connection):
    register(connection, PHONE, Reason.RECLAMACAO, RESUMO)

    result = register(connection, "67996547821", Reason.RECLAMACAO, f"  {RESUMO} ")

    assert result == Result.ALREADY_REGISTERED
    assert len(encaminhamentos(connection)) == 1


def test_motivo_diferente_gera_novo_encaminhamento(connection):
    register(connection, PHONE, Reason.RECLAMACAO, RESUMO)

    register(connection, PHONE, Reason.ATENDENTE_SOLICITADO, RESUMO)

    assert len(encaminhamentos(connection)) == 2


def test_outro_cliente_com_o_mesmo_motivo_gera_novo_encaminhamento(connection):
    register(connection, PHONE, Reason.RECLAMACAO, RESUMO)

    register(connection, "(67) 99789-0123", Reason.RECLAMACAO, "Outro assunto.")

    assert len(encaminhamentos(connection)) == 2


def test_resumo_acima_de_500_caracteres_e_cortado(connection):
    result = register(connection, PHONE, Reason.RECLAMACAO, "a" * 600)

    assert result == Result.REGISTERED
    assert encaminhamentos(connection)[0][2] == "a" * 500


@pytest.fixture
def relogio(monkeypatch):
    """Controlled clock: `relogio.em(minutos)` sets the moment of the next registration."""
    start = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)

    class Relogio:
        def em(self, minutos: int) -> None:
            instante = (start + timedelta(minutes=minutos)).isoformat()
            monkeypatch.setattr("src.handoffs.now_iso", lambda: instante)

    return Relogio()


@pytest.mark.regression
def test_mesmo_motivo_do_mesmo_cliente_na_janela_nao_gera_outro_registro_com_resumo_diferente(connection, relogio):
    relogio.em(0)
    register(connection, PHONE, Reason.ATENDENTE_SOLICITADO, "Cliente quer falar com humano sobre o pedido 7.")

    relogio.em(30)
    result = register(connection, PHONE, Reason.ATENDENTE_SOLICITADO, "Cliente exige atendente por causa do atraso.")

    assert result == Result.ALREADY_REGISTERED
    assert len(encaminhamentos(connection)) == 1


@pytest.mark.regression
def test_depois_da_janela_o_mesmo_motivo_gera_novo_registro(connection, relogio):
    relogio.em(0)
    register(connection, PHONE, Reason.RECLAMACAO, "Violão chegou com defeito.")

    relogio.em(61)
    result = register(connection, PHONE, Reason.RECLAMACAO, "Cabo veio sem o conector.")

    assert result == Result.REGISTERED
    assert len(encaminhamentos(connection)) == 2


@pytest.mark.regression
def test_reclamacao_sobre_outro_assunto_na_janela_gera_novo_registro(connection, relogio):
    relogio.em(0)
    register(connection, PHONE, Reason.RECLAMACAO, "Cliente reclama que o pedido 8 atrasou.")

    relogio.em(10)
    result = register(
        connection, PHONE, Reason.RECLAMACAO, "Cliente diz que o vendedor da loja a destratou ontem."
    )

    assert result == Result.REGISTERED
    assert len(encaminhamentos(connection)) == 2


@pytest.mark.regression
def test_reclamacao_sobre_outro_pedido_na_janela_gera_novo_registro(connection, relogio):
    relogio.em(0)
    register(connection, PHONE, Reason.RECLAMACAO, "Cliente insatisfeita: o pedido 8 chegou atrasado.")

    relogio.em(10)
    result = register(connection, PHONE, Reason.RECLAMACAO, "Cliente insatisfeita: o pedido 12 chegou atrasado.")

    assert result == Result.REGISTERED
    assert len(encaminhamentos(connection)) == 2


@pytest.mark.regression
def test_reclamacao_reescrita_sobre_o_mesmo_pedido_na_janela_nao_gera_outro_registro(connection, relogio):
    relogio.em(0)
    register(connection, PHONE, Reason.RECLAMACAO, "Cliente insatisfeita: o pedido 8 atrasou.")

    relogio.em(10)
    result = register(connection, PHONE, Reason.RECLAMACAO, "Reclamação do pedido 8, que chegou fora do prazo.")

    assert result == Result.ALREADY_REGISTERED
    assert len(encaminhamentos(connection)) == 1


@pytest.mark.regression
def test_atendente_solicitado_com_resumos_sem_relacao_na_janela_continua_um_registro(connection, relogio):
    relogio.em(0)
    register(connection, PHONE, Reason.ATENDENTE_SOLICITADO, "Cliente quer falar com um atendente.")

    relogio.em(5)
    result = register(connection, PHONE, Reason.ATENDENTE_SOLICITADO, "Solicitação de contato humano sobre troca de violão.")

    assert result == Result.ALREADY_REGISTERED
    assert len(encaminhamentos(connection)) == 1


@pytest.mark.regression
def test_verbo_de_reclamacao_em_comum_nao_faz_dois_assuntos_virarem_um(connection, relogio):
    relogio.em(0)
    register(connection, PHONE, Reason.RECLAMACAO, "Cliente reclama que o pedido 8 atrasou.")

    relogio.em(10)
    result = register(connection, PHONE, Reason.RECLAMACAO, "Cliente reclama que o vendedor a destratou.")

    assert result == Result.REGISTERED
