import json

from pydantic_ai.exceptions import ModelHTTPError, ModelRateLimitError

from src.limits import log_limit

GEMINI_BODY = {
    "error": {
        "code": 429,
        "status": "RESOURCE_EXHAUSTED",
        "details": [
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [
                    {
                        "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
                        "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                        "quotaValue": "20",
                    }
                ],
            },
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "27s"},
        ],
    }
}


def error_429(body, retry_after=None):
    return ModelHTTPError.for_category(
        ModelRateLimitError,
        status_code=429,
        model_name="gemini-3.5-flash-lite",
        body=body,
        retry_after=retry_after,
    )


def rows(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]


def test_logs_the_effective_limit_reported_by_the_provider(tmp_path):
    path = tmp_path / "limites.log"

    log_limit(error_429(GEMINI_BODY, retry_after=27), path)

    (event,) = rows(path)
    assert event["model"] == "gemini-3.5-flash-lite"
    assert event["status"] == 429
    assert event["limit"] == "20"
    assert event["metric"].endswith("generate_content_free_tier_requests")
    assert event["quota"] == "GenerateRequestsPerDayPerProjectPerModel-FreeTier"
    assert event["retry_after"] == 27
    assert event["date"]


def test_without_provider_details_the_fields_are_null_and_each_event_gets_a_line(tmp_path):
    path = tmp_path / "limites.log"

    log_limit(error_429(None), path)
    log_limit(error_429("texto solto"), path)

    events = rows(path)
    assert len(events) == 2
    for event in events:
        assert event["status"] == 429
        assert event["limit"] is None
        assert event["metric"] is None
        assert event["retry_after"] is None
