"""
Schema Inference Engine.

Infers JSON response schemas from captured API traffic WITHOUT storing
full financial payloads or PII-heavy responses. Only stores structural metadata.
"""

import logging
from typing import Any, Optional
from pydantic import BaseModel

log = logging.getLogger(__name__)


class InferredField(BaseModel):
    name: str
    field_type: str  # "str", "int", "float", "bool", "list", "dict", "null"
    nullable: bool = False
    nested_keys: Optional[list[str]] = None  # only populated for dict fields
    list_item_type: Optional[str] = None  # only populated for list fields


class InferredSchema(BaseModel):
    endpoint: str
    method: str
    status_code: int
    root_type: str  # "dict", "list", "scalar"
    fields: list[InferredField]
    record_count: Optional[int] = None  # for list responses
    sample_size: int = 0


def _infer_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return "unknown"


def _infer_fields_from_dict(obj: dict) -> list[InferredField]:
    """Extract field-level schema from a dict WITHOUT storing values."""
    fields = []
    for key, value in obj.items():
        ft = _infer_type(value)
        nested = None
        list_item = None

        if ft == "dict" and isinstance(value, dict):
            nested = sorted(value.keys())
        elif ft == "list" and isinstance(value, list) and len(value) > 0:
            list_item = _infer_type(value[0])
            if list_item == "dict" and isinstance(value[0], dict):
                nested = sorted(value[0].keys())

        fields.append(InferredField(
            name=key,
            field_type=ft,
            nullable=(value is None),
            nested_keys=nested,
            list_item_type=list_item,
        ))
    return fields


class SchemaInferenceEngine:
    """Stateful engine that accumulates schema knowledge across requests."""

    def __init__(self):
        self._schemas: dict[str, InferredSchema] = {}

    def infer(self, endpoint: str, method: str, status_code: int, payload: Any) -> Optional[InferredSchema]:
        """Infer schema from a response payload. Never stores raw data."""
        if payload is None:
            return None

        try:
            if isinstance(payload, dict):
                fields = _infer_fields_from_dict(payload)
                schema = InferredSchema(
                    endpoint=endpoint,
                    method=method,
                    status_code=status_code,
                    root_type="dict",
                    fields=fields,
                    sample_size=1,
                )
            elif isinstance(payload, list):
                if len(payload) > 0 and isinstance(payload[0], dict):
                    fields = _infer_fields_from_dict(payload[0])
                else:
                    fields = []
                schema = InferredSchema(
                    endpoint=endpoint,
                    method=method,
                    status_code=status_code,
                    root_type="list",
                    fields=fields,
                    record_count=len(payload),
                    sample_size=1,
                )
            else:
                schema = InferredSchema(
                    endpoint=endpoint,
                    method=method,
                    status_code=status_code,
                    root_type="scalar",
                    fields=[],
                    sample_size=1,
                )

            cache_key = f"{method}:{endpoint}"
            existing = self._schemas.get(cache_key)
            if existing:
                # Merge: increment sample count, union fields
                existing.sample_size += 1
                existing_names = {f.name for f in existing.fields}
                for f in schema.fields:
                    if f.name not in existing_names:
                        existing.fields.append(f)
                        existing_names.add(f.name)
                return existing
            else:
                self._schemas[cache_key] = schema
                return schema

        except Exception as e:
            log.warning(f"[SchemaInference] Failed to infer schema for {endpoint}: {e}")
            return None

    def get_schema(self, method: str, endpoint: str) -> Optional[InferredSchema]:
        return self._schemas.get(f"{method}:{endpoint}")

    def all_schemas(self) -> dict[str, InferredSchema]:
        return dict(self._schemas)

    def to_summary(self) -> dict:
        """Export a JSON-safe summary of all inferred schemas."""
        result = {}
        for key, schema in self._schemas.items():
            result[key] = {
                "root_type": schema.root_type,
                "field_count": len(schema.fields),
                "fields": [f.name for f in schema.fields],
                "record_count": schema.record_count,
                "sample_size": schema.sample_size,
            }
        return result
