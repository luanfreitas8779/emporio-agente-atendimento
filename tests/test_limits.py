import json

from pydantic_ai.exceptions import ModelHTTPError, ModelRateLimitError

from src.limits import registrar_limite

CORPO_DO_GEMINI = {
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


def erro_429(corpo, retry_after=None):
    return ModelHTTPError.for_category(
        ModelRateLimitError,
        status_code=429,
        model_name="gemini-3.5-flash-lite",
        body=corpo,
        retry_after=retry_after,
    )


def rows(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]


def test_registra_o_limite_efetivo_informado_pelo_provedor(tmp_path):
    path = tmp_path / "limites.log"

    registrar_limite(erro_429(CORPO_DO_GEMINI, retry_after=27), path)

    (evento,) = rows(path)
    assert evento["modelo"] == "gemini-3.5-flash-lite"
    assert evento["status"] == 429
    assert evento["limite"] == "20"
    assert evento["metrica"].endswith("generate_content_free_tier_requests")
    assert evento["cota"] == "GenerateRequestsPerDayPerProjectPerModel-FreeTier"
    assert evento["retry_after"] == 27
    assert evento["data"]


def test_sem_detalhes_do_provedor_os_campos_ficam_nulos_e_cada_evento_ganha_uma_linha(tmp_path):
    path = tmp_path / "limites.log"

    registrar_limite(erro_429(None), path)
    registrar_limite(erro_429("texto solto"), path)

    eventos = rows(path)
    assert len(eventos) == 2
    for evento in eventos:
        assert evento["status"] == 429
        assert evento["limite"] is None
        assert evento["metrica"] is None
        assert evento["retry_after"] is None
