# src/llm/schemas.py
"""JSON Schema для ответа LLM — генерируется из столбцов шаблона, руками не пишется."""

from src.core.columns import OCR_FIELDS


def ocr_schema(fields: list[str] | None = None) -> dict:
    fields = list(fields or OCR_FIELDS)
    prop = {c: {"type": "object", "properties": {"value": {"type": "string"}, "quote": {"type": "string"}},
                "required": ["value", "quote"]} for c in fields}
    return {"type": "object", "properties": prop, "required": fields}
