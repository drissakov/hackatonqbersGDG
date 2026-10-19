"""Transport compatibility never changes authoritative D03 URL validation."""

import copy
import json
from datetime import datetime
from typing import Annotated

import httpx
import pytest
from pydantic import Field, ValidationError

from backend.app.event_extraction import EventExtractionBatch
from backend.app.openai_client import ProviderError
from backend.app.services.events.models import CandidateBatch
from backend.tests.test_openai_client import run_with_transport


def formats(value):
    found = []
    if isinstance(value, dict):
        if "format" in value:
            found.append(value["format"])
        for item in value.values():
            found.extend(formats(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(formats(item))
    return found


def test_transport_projection_preserves_all_schema_constraints_and_original_d03_model():
    original = CandidateBatch.model_json_schema()
    before = copy.deepcopy(original)
    projected = EventExtractionBatch.model_json_schema()
    assert "uri" in formats(original) and "uri" not in formats(projected)
    assert original == before == CandidateBatch.model_json_schema()
    assert projected["properties"] == original["properties"]
    assert projected["additionalProperties"] is False
    assert projected["$defs"]["CandidateEvent"]["additionalProperties"] is False
    original_urls = original["$defs"]["CandidateEvent"]["properties"]["source_url"]
    projected_urls = projected["$defs"]["CandidateEvent"]["properties"]["source_url"]
    assert projected_urls == {key: value for key, value in original_urls.items() if key != "format"}
    assert (
        projected["$defs"]["SessionFacts"]["properties"]["price_from"]
        == (original["$defs"]["SessionFacts"]["properties"]["price_from"])
    )
    assert projected["$defs"]["CandidateEvent"]["properties"]["sessions"]["maxItems"] == 20
    assert projected["properties"]["events"]["maxItems"] == 10
    inherited = EventExtractionBatch.model_fields["events"]
    original_field = CandidateBatch.model_fields["events"]
    assert inherited.annotation == original_field.annotation
    assert inherited.metadata == original_field.metadata
    assert EventExtractionBatch.model_validate({"events": []}).events == []


def test_other_formats_and_schema_generation_options_are_preserved():
    class ExtendedBatch(EventExtractionBatch):
        observed_at: datetime
        label: Annotated[str, Field(alias="labelAlias")]

    schema = ExtendedBatch.model_json_schema(by_alias=False, mode="serialization")
    assert "date-time" in formats(schema)
    assert "uri" not in formats(schema)
    assert "label" in schema["properties"] and "labelAlias" not in schema["properties"]


def output(text):
    return {
        "id": "resp_synthetic",
        "object": "response",
        "created_at": 0,
        "model": "gpt-6-luna",
        "status": "completed",
        "output": [
            {
                "id": "msg_synthetic",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ],
    }


def test_actual_sdk_sends_uri_free_strict_schema_and_parses_inherited_batch():
    def handler(request):
        body = json.loads(request.content)
        transport = body["text"]["format"]
        assert transport["type"] == "json_schema" and transport["strict"] is True
        assert "uri" not in formats(transport["schema"])
        assert transport["schema"]["additionalProperties"] is False
        properties = transport["schema"]["$defs"]["CandidateEvent"]["properties"]
        required = transport["schema"]["$defs"]["CandidateEvent"]["required"]
        assert set(required) == set(properties)
        assert body["max_output_tokens"] == 4096 and body["store"] is False
        return httpx.Response(200, json=output('{"events":[]}'))

    result = run_with_transport(
        handler,
        lambda client: client.parse_response(
            "Return an empty synthetic batch", EventExtractionBatch, max_output_tokens=4096
        ),
    )
    assert isinstance(result, CandidateBatch) and result.events == []


@pytest.mark.parametrize("url", ["not-a-url", "file:///private.txt", "ftp://ticketon.kz/synthetic"])
def test_inherited_http_url_validators_still_reject_invalid_source_urls(url):
    data = {"events": [{"title": "SYNTHETIC TEST ONLY", "source_url": url, "page_kind": "listing"}]}
    with pytest.raises(ValidationError):
        EventExtractionBatch.model_validate(data)

    def handler(request):
        return httpx.Response(200, json=output(json.dumps(data)))

    with pytest.raises(ProviderError, match="invalid_structured_response"):
        run_with_transport(
            handler, lambda client: client.parse_response("Synthetic", EventExtractionBatch)
        )


def test_nullable_session_url_uses_original_validation_and_defaults():
    result = EventExtractionBatch.model_validate(
        {
            "events": [
                {
                    "title": "SYNTHETIC TEST ONLY",
                    "source_url": "https://ticketon.kz/synthetic",
                    "page_kind": "event",
                    "sessions": [{}],
                }
            ]
        }
    )
    assert result.events[0].sessions[0].source_url is None
    assert result.events[0].sessions[0].status == "unknown"
    assert result.events[0].city is None
    data = result.model_dump(mode="json")
    data["events"][0]["sessions"][0]["source_url"] = "invalid-session-url"
    with pytest.raises(ValidationError):
        EventExtractionBatch.model_validate(data)
