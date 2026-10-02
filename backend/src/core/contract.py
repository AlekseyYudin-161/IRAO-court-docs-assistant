"""Контракт doc.json: единственный формат обмена между ветками, правилами, экспортом, UI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from backend.src.core.columns import ACT_FIELDS, OCR_FIELDS, XML_FIELDS

Reason = Literal["NOT_IN_TEXT", "ANCHOR_NOT_FOUND", "OCR_UNREADABLE",
                 "VALIDATOR_FAILED", "LLM_DISAGREE", "LLM_DISABLED", "LLM_FALLBACK_CANDIDATE"]
ReviewFlag = Literal["ID_CONFLICT", "REQUIRED_FIELD_MISSING", "LOW_CONFIDENCE",
                     "UNCLASSIFIED", "ARITH_CHECK_FAILED"]
Method = Literal["copy", "lookup", "regex", "anchor", "llm", "derived", "gold", "none"]


class FieldValue(BaseModel):
    value: str = ""                                 # всегда строка; деньги "134288.50", даты "2033-06-10", пусто ""
    evidence: str | None = None                     # xpath:/OIp/IdDebtSum | IdDebtText[712:748]: … | p3: <цитата OCR>
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    method: Method = "none"
    reason: Reason | None = None                    # обязателен, если value == ""


class LawyerRoute(BaseModel):
    level: Literal["L1", "L2", "L3"] = "L3"
    reason_codes: list[str] = []
    basis: str | None = None                        # норма: "п. 4 ч. 1 ст. 46 229-ФЗ"
    deadline: str | None = None                     # ISO-дата
    evidence: str | None = None                     # цитата из документа


class ReviewRoute(BaseModel):
    flags: list[ReviewFlag] = []
    evidence: list[str] = []                        # по одному фрагменту на флаг, в том же порядке


class Route(BaseModel):
    lawyer: LawyerRoute = LawyerRoute()
    review: ReviewRoute = ReviewRoute()


class Doc(BaseModel):
    doc_id: str
    source_type: Literal["xml", "pdf"]
    file: str                                       # путь как в разметке: fssp/O_IP_ACT_END_END/fssp_001.xml
    table: Literal["xml", "ocr", "acts"]
    doc_type: str                                   # постановление ФССП | приказ | приказ эл | ИЛ | ИЛ эл | unknown
    doc_subtype: str | None = None                  # код DocType для XML
    fields: dict[str, FieldValue]
    extra: dict = {}
    route: Route = Route()
    timings_ms: dict[str, int] = {}
    pipeline_version: str = "v2.4"

    @model_validator(mode="after")
    def _all_fields_present(self) -> Doc:
        expected = {"xml": XML_FIELDS, "ocr": OCR_FIELDS, "acts": ACT_FIELDS}[self.table]
        missing = [c for c in expected if c not in self.fields]
        if missing:
            raise ValueError(f"{self.doc_id}: в fields нет столбцов {missing}")
        empty_no_reason = [k for k, v in self.fields.items() if v.value == "" and v.reason is None]
        if empty_no_reason:
            raise ValueError(f"{self.doc_id}: пустые поля без reason: {empty_no_reason}")
        return self


def load(path: str | Path) -> Doc:
    return Doc.model_validate_json(Path(path).read_text(encoding="utf-8"))


def dump(doc: Doc, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(doc.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")