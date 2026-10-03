# src/llm/client.py
"""Единственная точка вызова LLM. Ollama локально через OpenAI-совместимый API, модель из .env.
NO_LLM=1 или --no-llm => chat_json()/extract()/verify() возвращают None, пайплайн работает на правилах.
Тексты промптов — в prompts/*.md (их ведёт middle), клиент их только читает."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("llm")
ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "prompts"
_DISABLED = os.getenv("NO_LLM", "0") == "1"
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE = re.compile(r"^`{3}(?:json)?\s*|\s*`{3}$", re.MULTILINE)


def base_url() -> str:
    return os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")


def model() -> str:
    return os.getenv("LLM_MODEL", "qwen3:8b")


def disable() -> None:
    global _DISABLED
    _DISABLED = True


def enabled() -> bool:
    return not _DISABLED


def info() -> dict:
    """Для индикатора в UI (карточка E): {"enabled": bool, "model": str, "base_url": str}."""
    return {"enabled": enabled(), "model": model(), "base_url": base_url()}


def _client():
    from openai import (
        OpenAI,  # pylint: disable=import-outside-toplevel
    )
    return OpenAI(base_url=base_url(), api_key=os.getenv("LLM_API_KEY", "ollama"),
                  timeout=float(os.getenv("LLM_TIMEOUT", "120")), max_retries=0
                  )  # повторы делаем сами в chat_json


def _parse_json(s: str) -> dict | None:
    """Снимает <think>…</think> (qwen3) и обёртку из трёх бэктиков, затем json.loads; запасной вариант — первый {...}."""
    s = _FENCE.sub("", _THINK.sub("", s).strip()).strip()
    try:
        out = json.loads(s)
        return out if isinstance(out, dict) else None
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", s, re.DOTALL)
        if not m:
            return None
        try:
            out = json.loads(m.group(0))
            return out if isinstance(out, dict) else None
        except json.JSONDecodeError:
            return None


def chat_json(system: str, user: str, schema: dict | None = None, retries: int = 2) -> dict | None:
    """Один вызов модели, ответ — dict. schema (JSON Schema) — если сервер её не принял, деградируем до json_object."""
    if _DISABLED:
        return None
    client = _client()
    kwargs: dict[str, Any] = {"model": model(), "temperature": 0,
                              "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                              "response_format": ({"type": "json_schema", "json_schema": {"name": "fields", "schema": schema}}
                                                  if schema else {"type": "json_object"})}
    for attempt in range(retries + 1):
        t0 = time.time()
        try:
            r = client.chat.completions.create(**kwargs)
        except Exception as e:  # сервер не поднят, модель не скачана, таймаут, json_schema не поддержан
            if schema and kwargs["response_format"]["type"] == "json_schema":
                log.info("json_schema отклонён (%s) — переходим на json_object", type(e).__name__)
                kwargs["response_format"] = {"type": "json_object"}
                continue
            log.warning("LLM недоступна (%s): %s", type(e).__name__, e)
            return None
        out = _parse_json(r.choices[0].message.content or "")
        log.info("llm %s attempt=%d %.1fs ok=%s", model(), attempt, time.time() - t0, out is not None)
        if out is not None:
            return out
    return None


def _prompt(name_or_path: str) -> str:
    p = Path(name_or_path)
    if not p.suffix:
        p = PROMPTS / f"{name_or_path}.md"
    return p.read_text(encoding="utf-8")


def extract(text: str, schema: dict, prompt: str = "scan_extract") -> Optional[dict]:
    """6a: извлечь поля по схеме. prompt — имя файла в prompts/ без .md или путь."""
    fields = list(schema.get("properties", {}))
    user = ("Поля (ключи JSON ровно такие): " + ", ".join(fields) + "\n\nТЕКСТ:\n" + text) if fields else text
    return chat_json(_prompt(prompt), user, schema)


def verify(text: str, values: dict, prompt: str = "scan_verify") -> dict | None:
    """6b: проверить уже извлечённые значения по тексту; ответ {"disagree": {поле: значение}}."""
    user = "ТЕКСТ:\n" + text + "\n\nЗНАЧЕНИЯ:\n" + json.dumps(values, ensure_ascii=False)
    return chat_json(_prompt(prompt), user)
