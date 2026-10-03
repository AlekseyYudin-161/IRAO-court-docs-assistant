import json
import logging
import re
from typing import Any

import requests

from backend.src.core.config import settings
from backend.src.services.ner.rules.models import RuleExtraction

logger = logging.getLogger(__name__)


class ExtractionValidator:
    """Дополняет и правит rule_extraction через LLM (Ollama)."""

    FIELDS = [
        "street", "house", "flat",
        "surname", "first_name", "patronymic", "fio",
        "birth_date", "passport", "snils", "inn",
        "case_number", "case_date",
        "period_start", "period_end",
        "debt_main", "debt_penalty", "debt_duty",
        "co_debtors_count", "co_debtors",
    ]

    def __init__(
        self,
        url: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self._url = url or settings.OLLAMA_URL
        self._model = model or settings.OLLAMA_MODEL
        self._timeout = timeout or settings.OLLAMA_TIMEOUT

    def enrich(
        self,
        text: str,
        extraction: RuleExtraction,
    ) -> RuleExtraction:
        """Возвращает НОВЫЙ RuleExtraction, дополненный LLM.
        При любой ошибке — возвращает исходный без изменений."""
        try:
            current = extraction.model_dump()
            fixed = self._ask(text, current)
            merged = self._merge(current, fixed)
            return RuleExtraction(**merged)
        except Exception:
            logger.exception("LLM enrichment failed, returning original")
            return extraction

    # ---------- private ----------

    def _ask(self, text: str, extracted: dict[str, Any]) -> dict[str, Any]:
        user_prompt = (
            f"ТЕКСТ ДОКУМЕНТА:\n---\n{text}\n---\n\n"
            f"ТЕКУЩИЙ JSON:\n"
            f"```json\n{json.dumps(extracted, ensure_ascii=False, indent=2)}\n```\n\n"
            f"Верни ТОЛЬКО исправленный JSON-объект с теми же ключами: "
            f"{', '.join(self.FIELDS)}."
        )

        response = requests.post(
            self._url,
            json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": settings.OLLAMA_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.0, "num_ctx": 8192},
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        raw = response.json()["message"]["content"]
        return self._parse_object(raw)

    @staticmethod
    def _parse_object(raw: str) -> dict[str, Any]:
        raw = re.sub(r" thinking.*?", "", raw, flags=re.DOTALL).strip()

        fence = re.search(r"```(?:json)?\s*(.*?)```", raw, flags=re.DOTALL)
        if fence:
            raw = fence.group(1).strip()

        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            raise ValueError(f"Не найден JSON-объект в ответе LLM:\n{raw}")

        return json.loads(raw[start:end + 1])

    @staticmethod
    def _merge(current: dict[str, Any], fixed: dict[str, Any]) -> dict[str, Any]:
        """LLM заполняет только пустые/None поля. Непустые не трогаем,
        чтобы не потерять уже верные данные из правил."""
        merged = dict(current)
        for key, new_value in fixed.items():
            if key not in merged:
                continue
            old_value = merged[key]
            if old_value in (None, "", [], 0) and new_value not in (None, "", [], 0):
                merged[key] = new_value

        # пересчёт co_debtors_count
        co = merged.get("co_debtors") or []
        merged["co_debtors_count"] = len(co)
        return merged