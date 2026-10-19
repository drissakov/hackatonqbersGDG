"""Validate the complete Responses envelope before trusting structured output."""

import copy
import json

import httpx
import pytest

from backend.app.openai_client import ProviderError
from backend.tests.test_web_search_client import StructuredProbe, receipt, run_client

PRIVATE_MARKER = "synthetic-private-provider-value"


def structured_receipt():
    data = receipt()
    data["output"].pop(0)
    data["output"][0]["content"] = [
        {"type": "output_text", "text": '{"answer":"synthetic"}', "annotations": []}
    ]
    return data


def parse(client):
    return client.parse_response(
        "Synthetic extraction", StructuredProbe, instructions="Synthetic fixed policy"
    )


def assert_rejected(data, code, capsys, recwarn):
    def handler(request):
        return httpx.Response(200, json=data)

    with pytest.raises(ProviderError) as error:
        run_client(handler, parse)
    assert str(error.value) == code
    assert PRIVATE_MARKER not in str(error.value)
    assert not recwarn
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_structured_request_keeps_public_schema_wire_format_without_tools():
    def handler(request):
        body = json.loads(request.content)
        assert request.url.path == "/v1/responses"
        assert body["input"] == "Synthetic extraction"
        assert body["instructions"] == "Synthetic fixed policy"
        assert body["model"] == "gpt-6-luna"
        assert body["max_output_tokens"] == 2000 and body["store"] is False
        assert "tools" not in body and "tool_choice" not in body
        assert body["text"]["format"] == {
            "type": "json_schema",
            "name": "StructuredProbe",
            "strict": True,
            "schema": {
                "additionalProperties": False,
                "properties": {"answer": {"title": "Answer", "type": "string"}},
                "required": ["answer"],
                "title": "StructuredProbe",
                "type": "object",
            },
        }
        return httpx.Response(200, json=structured_receipt())

    assert run_client(handler, parse).answer == "synthetic"


@pytest.mark.parametrize("status", ["incomplete", "failed", "in_progress", "queued", None])
def test_valid_json_cannot_hide_incomplete_top_level(status, capsys, recwarn):
    data = structured_receipt()
    data["status"] = status
    assert_rejected(data, "response_incomplete_or_refused", capsys, recwarn)


@pytest.mark.parametrize("field", ["error", "incomplete_details"])
def test_completed_status_cannot_hide_error_or_incomplete_details(field, capsys, recwarn):
    data = structured_receipt()
    data[field] = (
        {"code": "server_error", "message": PRIVATE_MARKER}
        if field == "error"
        else {"reason": "max_output_tokens", "details": PRIVATE_MARKER}
    )
    assert_rejected(data, "response_incomplete_or_refused", capsys, recwarn)


@pytest.mark.parametrize("status", ["incomplete", "in_progress", "unknown", None])
def test_valid_json_cannot_hide_unfinished_message(status, capsys, recwarn):
    data = structured_receipt()
    data["output"][0]["status"] = status
    assert_rejected(data, "response_incomplete_or_refused", capsys, recwarn)


@pytest.mark.parametrize("kind", ["only_refusal", "refusal_with_json", "second_message"])
def test_any_refusal_prevents_acceptance_of_otherwise_valid_json(kind, capsys, recwarn):
    data = structured_receipt()
    refusal = {"type": "refusal", "refusal": PRIVATE_MARKER}
    if kind == "only_refusal":
        data["output"][0]["content"] = [refusal]
    elif kind == "refusal_with_json":
        data["output"][0]["content"].append(refusal)
    else:
        second = copy.deepcopy(data["output"][0])
        second["content"] = [refusal]
        data["output"].append(second)
    assert_rejected(data, "response_incomplete_or_refused", capsys, recwarn)


@pytest.mark.parametrize("output", [None, PRIVATE_MARKER, 3, {}, [], [None], [PRIVATE_MARKER]])
def test_malformed_output_shape_is_safe_provider_error(output, capsys, recwarn):
    data = structured_receipt()
    data["output"] = output
    assert_rejected(data, "invalid_structured_response", capsys, recwarn)


@pytest.mark.parametrize("data", [None, PRIVATE_MARKER, [], 3])
def test_malformed_top_level_shape_never_raises_attribute_error(data, capsys, recwarn):
    assert_rejected(data, "invalid_structured_response", capsys, recwarn)


@pytest.mark.parametrize(
    "content",
    [
        None,
        PRIVATE_MARKER,
        [],
        [None],
        [PRIVATE_MARKER],
        [{"type": "unknown", "text": PRIVATE_MARKER}],
    ],
)
def test_malformed_content_shape_never_prints_provider_values(content, capsys, recwarn):
    data = structured_receipt()
    data["output"][0]["content"] = content
    assert_rejected(data, "invalid_structured_response", capsys, recwarn)


@pytest.mark.parametrize("text", [None, 1, {}, "", " ", PRIVATE_MARKER, "{}"])
def test_missing_empty_or_invalid_schema_text_is_rejected(text, capsys, recwarn):
    data = structured_receipt()
    data["output"][0]["content"][0]["text"] = text
    assert_rejected(data, "invalid_structured_response", capsys, recwarn)


@pytest.mark.parametrize("kind", ["second_message", "second_content", "wrong_role"])
def test_ambiguous_or_non_assistant_json_is_rejected(kind, capsys, recwarn):
    data = structured_receipt()
    if kind == "second_message":
        data["output"].append(copy.deepcopy(data["output"][0]))
    elif kind == "second_content":
        data["output"][0]["content"].append(copy.deepcopy(data["output"][0]["content"][0]))
    else:
        data["output"][0]["role"] = "user"
    assert_rejected(data, "invalid_structured_response", capsys, recwarn)


@pytest.mark.parametrize("kind", ["unknown", "web_search_call", "function_call"])
def test_unrequested_or_unknown_outputs_are_rejected_without_serializer_warnings(
    kind, capsys, recwarn
):
    data = structured_receipt()
    data["output"].insert(0, {"type": kind, "data": PRIVATE_MARKER})
    assert_rejected(data, "invalid_structured_response", capsys, recwarn)


@pytest.mark.parametrize("status", [None, "completed"])
def test_reasoning_blocks_are_permitted_without_using_their_content(status, capsys, recwarn):
    data = structured_receipt()
    data["output"].insert(
        0,
        {
            "id": "synthetic-reasoning",
            "type": "reasoning",
            "summary": [],
            "status": status,
        },
    )
    assert run_client(lambda _: httpx.Response(200, json=data), parse).answer == "synthetic"
    assert not recwarn
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@pytest.mark.parametrize("status", ["incomplete", "in_progress", "unknown"])
def test_unfinished_reasoning_blocks_cannot_hide_behind_valid_json(status, capsys, recwarn):
    data = structured_receipt()
    data["output"].insert(
        0, {"id": "synthetic-reasoning", "type": "reasoning", "summary": [], "status": status}
    )
    assert_rejected(data, "response_incomplete_or_refused", capsys, recwarn)
