import decimal
import json
import sqlite3

import pytest
from pydantic_ai import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.exceptions import (
    ModelAPIError,
    ModelAuthenticationError,
    ModelConnectionError,
    ModelHTTPError,
    ModelOverloadedError,
    ModelQuotaExceededError,
    ModelRateLimitError,
    ModelRequestTimeout,
    ModelServerError,
    ModelTimeoutError,
    ModelUnavailableError,
)
from pydantic_ai.models.function import FunctionModel

from src.agent import (
    TECHNICAL_ERROR_MESSAGE,
    RATE_LIMIT_MESSAGE,
    DAILY_LIMIT_MESSAGE,
    TIMEOUT_MESSAGE,
    ToolCall,
    SAFE_ANSWER_WITHOUT_REGISTRATION,
    Session,
    agent,
    respond,
)
from src.database import connect
from src.memory import load_state, conversation_for_display

ANA = "(67) 99654-7821"


def limit_reached(retry_after: float | None = None) -> ModelRateLimitError:
    return ModelRateLimitError("modelo", "limite de uso", retry_after=retry_after)


def model_that_fails_before_answering(failures: list[Exception], attempts: list[int]):
    """Raises each error in the list, one per call, and then answers."""

    def model(messages, info):
        attempts.append(1)
        if failures:
            raise failures.pop(0)
        return ModelResponse(parts=[TextPart("Resposta do Tom")])

    return FunctionModel(model)


@pytest.fixture
def waits(monkeypatch):
    registered_rows: list[float] = []
    monkeypatch.setattr("src.agent._wait", registered_rows.append)
    return registered_rows


def test_rate_limit_error_triggers_a_retry(connection, waits):
    attempts: list[int] = []
    model = model_that_fails_before_answering([limit_reached()], attempts)

    with agent.override(model=model):
        answer = respond("Oi", Session(connection, phone=ANA))

    assert answer == "Resposta do Tom"
    assert len(attempts) == 2


@pytest.mark.parametrize(
    "retry_after, expected",
    [(7, [7]), (300, [15]), (None, [2])],
)
def test_waits_the_time_requested_by_the_provider_capped_at_15_seconds(
    connection, waits, retry_after, expected
):
    model = model_that_fails_before_answering([limit_reached(retry_after)], [])

    with agent.override(model=model):
        respond("Oi", Session(connection, phone=ANA))

    assert waits == expected


def test_persistent_limit_produces_a_clear_message_after_3_attempts(connection, waits):
    attempts: list[int] = []
    model = model_that_fails_before_answering([limit_reached() for _ in range(5)], attempts)

    with agent.override(model=model):
        answer = respond("Oi", Session(connection, phone=ANA))

    assert answer == RATE_LIMIT_MESSAGE
    assert len(attempts) == 3
    assert waits == [2, 5]


def test_the_conversation_is_not_lost_when_the_limit_persists(connection, waits):
    model = model_that_fails_before_answering([limit_reached() for _ in range(5)], [])

    with agent.override(model=model):
        respond("Quanto custa o Takamine GD20?", Session(connection, phone=ANA))

    assert conversation_for_display(connection, ANA) == [
        ("user", "Quanto custa o Takamine GD20?"),
        ("assistant", RATE_LIMIT_MESSAGE),
    ]


@pytest.mark.parametrize(
    "error",
    [ModelTimeoutError("modelo", "sem resposta"), ModelRequestTimeout("modelo", 40)],
)
def test_call_without_provider_response_produces_a_clear_message_without_retry(
    connection, waits, error
):
    attempts: list[int] = []
    model = model_that_fails_before_answering([error], attempts)

    with agent.override(model=model):
        answer = respond("Oi", Session(connection, phone=ANA))

    assert answer == TIMEOUT_MESSAGE
    assert len(attempts) == 1
    assert conversation_for_display(connection, ANA) == [("user", "Oi"), ("assistant", TIMEOUT_MESSAGE)]


@pytest.mark.parametrize(
    "error",
    [
        ModelConnectionError("modelo", "sem rede"),
        ModelAuthenticationError("modelo", "chave inválida"),
        ModelAPIError("modelo", "erro qualquer"),
        sqlite3.OperationalError("no such table: products"),
    ],
)
def test_technical_error_produces_a_friendly_message_without_details(connection, waits, error):
    model = model_that_fails_before_answering([error], [])

    with agent.override(model=model):
        answer = respond("Oi", Session(connection, phone=ANA))

    assert answer == TECHNICAL_ERROR_MESSAGE
    for detail in ("sem rede", "chave inválida", "erro qualquer", "products"):
        assert detail not in answer
    assert conversation_for_display(connection, ANA)[-1] == ("assistant", TECHNICAL_ERROR_MESSAGE)


@pytest.mark.regression
@pytest.mark.parametrize("error", [
        ModelUnavailableError("modelo", "indisponível"),
        ModelOverloadedError("modelo", "sobrecarga"),
        ModelServerError("modelo", "erro 504"),
    ])
def test_temporary_provider_unavailability_also_triggers_a_retry(connection, waits, error):
    attempts: list[int] = []
    model = model_that_fails_before_answering([error], attempts)

    with agent.override(model=model):
        answer = respond("Oi", Session(connection, phone=ANA))

    assert answer == "Resposta do Tom"
    assert len(attempts) == 2


def test_exhausted_quota_does_not_retry_and_reports_the_limit(connection, waits):
    attempts: list[int] = []
    model = model_that_fails_before_answering([ModelQuotaExceededError("modelo", "cota")], attempts)

    with agent.override(model=model):
        answer = respond("Oi", Session(connection, phone=ANA))

    assert answer == DAILY_LIMIT_MESSAGE
    assert len(attempts) == 1
    assert waits == []


def test_database_without_tables_produces_a_friendly_message_instead_of_a_traceback(tmp_path):
    empty = connect(tmp_path / "vazio.db")

    answer = respond("Oi", Session(empty, phone=ANA))

    assert answer == TECHNICAL_ERROR_MESSAGE
    empty.close()


def test_failure_to_register_the_safe_answer_handoff_does_not_bring_down_the_service(connection):
    connection.execute("DROP TABLE handoffs")

    def model(messages, info):
        return ModelResponse(parts=[TextPart("Custa R$ 9,99")])

    with agent.override(model=FunctionModel(model)):
        answer = respond("Preço do violão?", Session(connection, phone=ANA))

    assert answer == SAFE_ANSWER_WITHOUT_REGISTRATION


def test_persistent_limit_is_logged_with_what_the_provider_reported(
    connection, waits, temporary_limits_log
):
    body = {"error": {"details": [{"violations": [{"quotaValue": "20", "quotaId": "PorDia"}]}]}}
    error = ModelHTTPError.for_category(
        ModelRateLimitError, status_code=429, model_name="gemini-3.5-flash-lite", body=body
    )
    model = model_that_fails_before_answering([error, error, error], [])

    with agent.override(model=model):
        respond("Oi", Session(connection, phone=ANA))

    events = [json.loads(l) for l in temporary_limits_log.read_text(encoding="utf-8").splitlines()]
    assert [(e["status"], e["limit"], e["quota"]) for e in events] == [(429, "20", "PorDia")]


def test_failure_to_write_the_limits_log_does_not_prevent_the_message(connection, waits, tmp_path, monkeypatch):
    # A directory in place of the file makes the write fail.
    monkeypatch.setattr("src.config.LIMITS_LOG_PATH", tmp_path)
    model = model_that_fails_before_answering([limit_reached() for _ in range(5)], [])

    with agent.override(model=model):
        answer = respond("Oi", Session(connection, phone=ANA))

    assert answer == RATE_LIMIT_MESSAGE


def test_turn_with_error_does_not_inherit_the_previous_turn_tools(connection, waits):
    session = Session(connection, phone=ANA)
    session.tools = [ToolCall("search_products", {"search_term": "x"})]
    model = model_that_fails_before_answering([limit_reached() for _ in range(5)], [])

    with agent.override(model=model):
        respond("Oi", session)

    assert session.tools == []


def test_retry_does_not_inherit_the_state_of_the_failed_attempt(connection, waits):
    calls: list[int] = []

    def model(messages, info):
        calls.append(1)
        if len(calls) == 1:
            return ModelResponse(
                parts=[ToolCallPart("search_products", {"search_term": "Takamine GD20"})]
            )
        if len(calls) == 2:
            raise limit_reached()
        return ModelResponse(parts=[TextPart("Resposta do Tom")])

    with agent.override(model=FunctionModel(model)):
        respond("Quanto custa o Takamine GD20?", Session(connection, phone=ANA))

    assert load_state(connection, ANA).product_in_focus is None


@pytest.mark.regression
@pytest.mark.parametrize("error", [ValueError("data inválida"), decimal.InvalidOperation(), OverflowError("grande")])
def test_unexpected_exception_produces_a_friendly_message_and_stores_the_conversation(connection, waits, error):
    model = model_that_fails_before_answering([error], [])

    with agent.override(model=model):
        answer = respond("Oi", Session(connection, phone=ANA))

    assert answer == TECHNICAL_ERROR_MESSAGE
    assert conversation_for_display(connection, ANA)[-1] == ("assistant", TECHNICAL_ERROR_MESSAGE)


@pytest.mark.regression
def test_persistent_server_error_produces_the_technical_message_not_the_rate_limit_one(connection, waits):
    attempts: list[int] = []
    errors = [ModelServerError("modelo", "erro 504")] * 3
    model = model_that_fails_before_answering(errors, attempts)

    with agent.override(model=model):
        answer = respond("Oi", Session(connection, phone=ANA))

    assert answer == TECHNICAL_ERROR_MESSAGE
    assert len(attempts) == 3


def provider_limit(quota: str, retry_delay: str | None = None) -> ModelRateLimitError:
    """429 in the Gemini format: the quota violation and, sometimes, the RetryInfo."""
    details = [{"violations": [{"quotaId": quota, "quotaValue": "15"}]}]
    if retry_delay:
        details.append({"retryDelay": retry_delay})
    return ModelHTTPError.for_category(
        ModelRateLimitError,
        status_code=429,
        model_name="gemini-3.5-flash-lite",
        body={"error": {"details": details}},
    )


@pytest.mark.regression
def test_daily_limit_does_not_retry_and_says_the_service_returns_tomorrow(connection, waits):
    attempts: list[int] = []
    error = provider_limit("GenerateRequestsPerDayPerProjectPerModel-FreeTier")
    model = model_that_fails_before_answering([error, error, error], attempts)

    with agent.override(model=model):
        answer = respond("Oi", Session(connection, phone=ANA))

    assert len(attempts) == 1
    assert waits == []
    assert answer == DAILY_LIMIT_MESSAGE


@pytest.mark.regression
@pytest.mark.parametrize("retry_delay, expected", [("27s", [15]), ("7.5s", [7.5]), ("lixo", [2])])
def test_wait_uses_the_body_retry_delay_when_retry_after_is_empty(
    connection, waits, retry_delay, expected
):
    error = provider_limit("GenerateRequestsPerMinutePerProjectPerModel-FreeTier", retry_delay)
    model = model_that_fails_before_answering([error], [])

    with agent.override(model=model):
        respond("Oi", Session(connection, phone=ANA))

    assert waits == expected


@pytest.mark.regression
def test_rate_limit_message_does_not_mention_the_ai_service_or_the_provider(connection, waits):
    error = provider_limit("GenerateRequestsPerMinutePerProjectPerModel-FreeTier", "20s")
    model = model_that_fails_before_answering([error, error, error], [])

    with agent.override(model=model):
        answer = respond("Oi", Session(connection, phone=ANA))

    assert answer == "Estamos com muitos atendimentos ao mesmo tempo. Tente novamente em alguns minutos."


@pytest.mark.regression
def test_daily_limit_is_recognized_even_after_the_per_minute_violation(connection, waits):
    violations = [
        {"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"},
        {"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"},
    ]
    error = ModelHTTPError.for_category(
        ModelRateLimitError,
        status_code=429,
        model_name="gemini-3.5-flash-lite",
        body={"error": {"details": [{"violations": violations}]}},
    )
    attempts: list[int] = []
    model = model_that_fails_before_answering([error, error, error], attempts)

    with agent.override(model=model):
        answer = respond("Oi", Session(connection, phone=ANA))

    assert len(attempts) == 1
    assert answer == DAILY_LIMIT_MESSAGE


@pytest.mark.regression
def test_exhausted_quota_says_the_service_returns_tomorrow(connection, waits):
    model = model_that_fails_before_answering([ModelQuotaExceededError("modelo", "cota")], [])

    with agent.override(model=model):
        answer = respond("Oi", Session(connection, phone=ANA))

    assert answer == DAILY_LIMIT_MESSAGE


@pytest.mark.regression
@pytest.mark.parametrize("error", [ValueError("dado inválido"), OSError("disco cheio")])
def test_any_failure_to_store_the_technical_message_does_not_prevent_the_answer(connection, waits, monkeypatch, error):
    def write_with_failure(*arguments, **named):
        raise error

    monkeypatch.setattr("src.agent.memory.save_messages", write_with_failure)
    model = model_that_fails_before_answering([ModelQuotaExceededError("modelo", "cota")], [])

    with agent.override(model=model):
        answer = respond("Oi", Session(connection, phone=ANA))

    assert answer == DAILY_LIMIT_MESSAGE
