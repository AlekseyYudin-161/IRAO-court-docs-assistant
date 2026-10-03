"""LLM client tests"""

from src.core.columns import OCR_FIELDS
from src.llm import client
from src.llm.schemas import ocr_schema


def test_parse_json_strips_think_and_fences():
    raw = "<think>рассуждаю...</think>\n```json\n{\"дело_номер\": {\"value\": \"2-1/2033\", \"quote\": \"Дело № 2-1/2033\"}}\n```"
    assert client._parse_json(raw)["дело_номер"]["value"] == "2-1/2033"
    assert client._parse_json("мусор без json") is None
    assert client._parse_json("[1, 2]") is None


def test_schema_covers_all_ocr_fields():
    s = ocr_schema()
    assert set(s["properties"]) == set(OCR_FIELDS) and s["required"] == OCR_FIELDS


def test_disabled_returns_none_without_server(monkeypatch):
    monkeypatch.setattr(client, "_DISABLED", True)
    assert client.extract("x", ocr_schema()) is None and client.enabled() is False


def test_unreachable_server_returns_none(monkeypatch):
    monkeypatch.setattr(client, "_DISABLED", False)
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:1/v1")
    monkeypatch.setenv("LLM_TIMEOUT", "2")
    assert client.chat_json("s", "u") is None
