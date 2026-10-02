# src/acts/to_doc.py
"""Судебные акты (решение / определение / постановление суда) → doc.json.
Пятый класс входа: текстовый слой есть всегда (набор оргов 01.10), OCR не нужен; если слоя нет — вернуть None,
и пусть PDF-ветка прогонит OCR, а текст отдаст сюда через act_text_to_doc()."""

from __future__ import annotations

import re
import time
from datetime import date
from pathlib import Path

from backend.src.core.columns import ACT_FIELDS
from backend.src.core.contract import Doc, FieldValue, LawyerRoute, ReviewRoute, Route
from backend.src.rules.markers import flatten, looks_like_court_act, route_court_act

KIND_RE = re.compile(r"\b(РЕШЕНИЕ|ОПРЕДЕЛЕНИЕ|ПОСТАНОВЛЕНИЕ)\b|Резолютивная часть (решения|определения|постановления)")
CASE_RE = re.compile(r"Дело\s*№?\s*((?:А\d{2}-\d+/\d{4})|\[дело\])")
DATE_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")


def pdf_text(path: Path) -> str:
    import pymupdf
    return " ".join(pg.get_text("text", sort=True) for pg in pymupdf.open(path))


def _fv(value: str, evidence: str | None, method: str = "regex") -> FieldValue:
    if value:
        return FieldValue(value=value, evidence=evidence, confidence=0.9, method=method)
    return FieldValue(value="", confidence=0.0, method=method, reason="NOT_IN_TEXT")


def act_text_to_doc(text: str, doc_id: str, file: str, doc_date: date | None = None) -> Doc:
    t0 = time.time()
    flat = flatten(text)
    head = flat[:1500]
    clean = re.sub(r"\[[^\]]*\]", " ", head)          # маски оргов «[номер]», «[дата]» из шапки убираем
    court = re.search(r"([А-ЯЁ][^.]{3,100}?суд[а-яё]*(?: [А-ЯЁа-яё\-]+){0,8})", clean)
    kind = KIND_RE.search(head)
    kind_name = (kind.group(1) or {"решения": "РЕШЕНИЕ", "определения": "ОПРЕДЕЛЕНИЕ", "постановления": "ПОСТАНОВЛЕНИЕ"}[kind.group(2)]) if kind else ""
    case = CASE_RE.search(flat)
    f = {
        "суд": _fv(court.group(1).strip() if court else "", "p1: шапка акта"),
        "вид_акта": _fv(kind_name.capitalize(), f"p1: «{kind.group(0)}»" if kind else None),
        "дело_номер": _fv(case.group(1) if case and case.group(1) != "[дело]" else "", f"«{case.group(0)}»" if case else None),
        "дело_дата": _fv(doc_date.isoformat() if doc_date else "", "дата акта" if doc_date else None),
    }
    assert set(f) == set(ACT_FIELDS)
    r = route_court_act(text, doc_date)
    route = Route(
        lawyer=LawyerRoute(level=r.level, reason_codes=r.reason_codes, basis=r.basis, deadline=r.deadline, evidence=r.evidence),
        review=ReviewRoute(flags=["UNCLASSIFIED"] if not kind else [], evidence=["вид акта не распознан"] if not kind else []),
    )
    return Doc(doc_id=doc_id, source_type="pdf", file=file, table="acts",
               doc_type="судебный акт" + (f" ({kind_name.lower()})" if kind else ""), fields=f,
               extra={"actions": r.actions, "appeal_window_days": r.window_days,
                      "markers": [{"no": h.no, "code": h.code, "evidence": h.evidence} for h in r.hits]},
               route=route, timings_ms={"extract": int((time.time() - t0) * 1000)})


def act_to_doc(path: str | Path, data_root: str | Path = "data") -> Doc | None:
    """None — если это не судебный акт с текстовым слоем (тогда файл идёт в обычную PDF-ветку)."""
    p = Path(path)
    text = pdf_text(p)
    if len(text.strip()) < 200 or not looks_like_court_act(text):
        return None
    try:
        rel = str(p.relative_to(data_root))
    except ValueError:
        rel = p.name
    return act_text_to_doc(text, p.stem, rel)
