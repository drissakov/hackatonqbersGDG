"""Responses schema compatibility without weakening D03 runtime URL validation."""

from backend.app.services.events.models import CandidateBatch


def _transport_schema(value):
    if isinstance(value, dict):
        return {
            key: _transport_schema(item)
            for key, item in value.items()
            if not (key == "format" and item == "uri")
        }
    if isinstance(value, list):
        return [_transport_schema(item) for item in value]
    return value


class EventExtractionBatch(CandidateBatch):
    @classmethod
    def model_json_schema(cls, *args, **kwargs) -> dict:
        # Responses does not accept format=uri. HttpUrl's runtime validators
        # remain inherited; only the schema sent to the provider is projected.
        return _transport_schema(super().model_json_schema(*args, **kwargs))
