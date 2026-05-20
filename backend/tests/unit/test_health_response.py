import pytest
from pydantic import ValidationError

from coffer.main import HealthResponse


def test_health_response_constructs_with_required_fields() -> None:
    response = HealthResponse(status="ok", version="0.1.0")
    assert response.status == "ok"
    assert response.version == "0.1.0"


def test_health_response_serializes_to_dict() -> None:
    response = HealthResponse(status="ok", version="0.1.0")
    assert response.model_dump() == {"status": "ok", "version": "0.1.0"}


def test_health_response_serializes_to_json() -> None:
    response = HealthResponse(status="ok", version="0.1.0")
    assert response.model_dump_json() == '{"status":"ok","version":"0.1.0"}'


def test_health_response_rejects_missing_fields() -> None:
    with pytest.raises(ValidationError):
        HealthResponse.model_validate({"status": "ok"})  # missing version
