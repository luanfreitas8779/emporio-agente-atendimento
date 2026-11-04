from datetime import datetime, timedelta, timezone

import pytest

from src.handoffs import Reason, Result, register

PHONE = "(67) 99654-7821"
SUMMARY = "Cliente relata que o violão chegou com defeito no braço."


def handoff_rows(connection):
    return [
        tuple(row)
        for row in connection.execute("SELECT phone, reason, summary FROM handoffs ORDER BY id")
    ]


def test_registers_the_complaint_with_phone_reason_and_summary(connection):
    result = register(connection, PHONE, Reason.COMPLAINT, SUMMARY)

    assert result == Result.REGISTERED
    assert handoff_rows(connection) == [("67996547821", "reclamacao", SUMMARY)]


@pytest.mark.parametrize("summary", ["", "   ", "\n\t"])
def test_empty_summary_does_not_write_a_handoff(connection, summary):
    result = register(connection, PHONE, Reason.COMPLAINT, summary)

    assert result == Result.INVALID_SUMMARY
    assert handoff_rows(connection) == []


@pytest.mark.parametrize("phone", ["", "12345", "abc"])
def test_invalid_phone_does_not_write_a_handoff(connection, phone):
    result = register(connection, phone, Reason.COMPLAINT, SUMMARY)

    assert result == Result.INVALID_PHONE
    assert handoff_rows(connection) == []


def test_repeating_the_same_handoff_does_not_duplicate(connection):
    register(connection, PHONE, Reason.COMPLAINT, SUMMARY)

    result = register(connection, "67996547821", Reason.COMPLAINT, f"  {SUMMARY} ")

    assert result == Result.ALREADY_REGISTERED
    assert len(handoff_rows(connection)) == 1


def test_different_reason_creates_a_new_handoff(connection):
    register(connection, PHONE, Reason.COMPLAINT, SUMMARY)

    register(connection, PHONE, Reason.AGENT_REQUESTED, SUMMARY)

    assert len(handoff_rows(connection)) == 2


def test_another_customer_with_the_same_reason_creates_a_new_handoff(connection):
    register(connection, PHONE, Reason.COMPLAINT, SUMMARY)

    register(connection, "(67) 99789-0123", Reason.COMPLAINT, "Outro assunto.")

    assert len(handoff_rows(connection)) == 2


def test_summary_above_500_characters_is_truncated(connection):
    result = register(connection, PHONE, Reason.COMPLAINT, "a" * 600)

    assert result == Result.REGISTERED
    assert handoff_rows(connection)[0][2] == "a" * 500


@pytest.fixture
def clock(monkeypatch):
    """Controlled clock: `relogio.em(minutos)` sets the moment of the next registration."""
    start = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)

    class Clock:
        def at(self, minutes: int) -> None:
            moment = (start + timedelta(minutes=minutes)).isoformat()
            monkeypatch.setattr("src.handoffs.now_iso", lambda: moment)

    return Clock()


@pytest.mark.regression
def test_same_reason_from_the_same_customer_in_the_window_creates_no_record_with_a_different_summary(connection, clock):
    clock.at(0)
    register(connection, PHONE, Reason.AGENT_REQUESTED, "Cliente quer falar com humano sobre o pedido 7.")

    clock.at(30)
    result = register(connection, PHONE, Reason.AGENT_REQUESTED, "Cliente exige atendente por causa do atraso.")

    assert result == Result.ALREADY_REGISTERED
    assert len(handoff_rows(connection)) == 1


@pytest.mark.regression
def test_after_the_window_the_same_reason_creates_a_new_record(connection, clock):
    clock.at(0)
    register(connection, PHONE, Reason.COMPLAINT, "Violão chegou com defeito.")

    clock.at(61)
    result = register(connection, PHONE, Reason.COMPLAINT, "Cabo veio sem o conector.")

    assert result == Result.REGISTERED
    assert len(handoff_rows(connection)) == 2


@pytest.mark.regression
def test_complaint_about_another_subject_in_the_window_creates_a_new_record(connection, clock):
    clock.at(0)
    register(connection, PHONE, Reason.COMPLAINT, "Cliente reclama que o pedido 8 atrasou.")

    clock.at(10)
    result = register(
        connection, PHONE, Reason.COMPLAINT, "Cliente diz que o vendedor da loja a destratou ontem."
    )

    assert result == Result.REGISTERED
    assert len(handoff_rows(connection)) == 2


@pytest.mark.regression
def test_complaint_about_another_order_in_the_window_creates_a_new_record(connection, clock):
    clock.at(0)
    register(connection, PHONE, Reason.COMPLAINT, "Cliente insatisfeita: o pedido 8 chegou atrasado.")

    clock.at(10)
    result = register(connection, PHONE, Reason.COMPLAINT, "Cliente insatisfeita: o pedido 12 chegou atrasado.")

    assert result == Result.REGISTERED
    assert len(handoff_rows(connection)) == 2


@pytest.mark.regression
def test_rewritten_complaint_about_the_same_order_in_the_window_creates_no_other_record(connection, clock):
    clock.at(0)
    register(connection, PHONE, Reason.COMPLAINT, "Cliente insatisfeita: o pedido 8 atrasou.")

    clock.at(10)
    result = register(connection, PHONE, Reason.COMPLAINT, "Reclamação do pedido 8, que chegou fora do prazo.")

    assert result == Result.ALREADY_REGISTERED
    assert len(handoff_rows(connection)) == 1


@pytest.mark.regression
def test_agent_requested_with_unrelated_summaries_in_the_window_stays_one_record(connection, clock):
    clock.at(0)
    register(connection, PHONE, Reason.AGENT_REQUESTED, "Cliente quer falar com um atendente.")

    clock.at(5)
    result = register(connection, PHONE, Reason.AGENT_REQUESTED, "Solicitação de contato humano sobre troca de violão.")

    assert result == Result.ALREADY_REGISTERED
    assert len(handoff_rows(connection)) == 1


@pytest.mark.regression
def test_shared_complaint_verb_does_not_merge_two_subjects(connection, clock):
    clock.at(0)
    register(connection, PHONE, Reason.COMPLAINT, "Cliente reclama que o pedido 8 atrasou.")

    clock.at(10)
    result = register(connection, PHONE, Reason.COMPLAINT, "Cliente reclama que o vendedor a destratou.")

    assert result == Result.REGISTERED
