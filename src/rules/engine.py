"""route_to_lawyer(doc) -> Route: чистая функция, без LLM и ввода-вывода.

Порядок:
1. UNCLASSIFIED — тип документа не определён → только флаг ручной проверки, коды не ставим.
2. XML-правила по doc_subtype + extra.npa_articles («46/1/4»; запасной путь — «п. 4 ч. 1 ст. 46» в AdjudicationText).
3. PDF-правила (приказ / ИЛ): идентификаторы должника, солидарные должники, заглушки по тексту extra["text"].
4. Quality-триггеры → route.review: ID_CONFLICT, REQUIRED_FIELD_MISSING, LOW_CONFIDENCE, ARITH_CHECK_FAILED.
Уровень = максимум по кодам (L1 > L2 > L3); срок — ближайший; evidence — цитата + путь NpaArticle.

CLI: python -m src.rules.engine fixtures/doc_fssp_001.json [--as-of 2033-07-01]
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from src.core.contract import Doc, LawyerRoute, ReviewRoute, Route
from src.rules.codes import CODES, LAW, LEVEL_RANK
from src.rules.deadlines import base_date, compute

XML_SUBTYPES = {"O_IP_ACT_END_END", "O_IP_ACT_END_STOP", "O_IP_ACT_REOPEN_CANCEL", "O_IP_ACT_RETURN", "O_IP_RES_REOPEN"}
PDF_TYPES = {"приказ", "приказ эл", "ИЛ", "ИЛ эл"}
REQUIRED = {
    "xml": ["DocType", "DocDate", "IdDocNo", "IpNo", "DbtrName"],
    "ocr": ["фамилия", "имя", "дело_номер", "дело_дата", "дз_осн"],
}
LOW_CONFIDENCE = 0.7
EVIDENCE_MAX = 300
ARTICLE_RE = re.compile(r"п\.\s*(\d+)\s*ч\.\s*(\d+)\s*ст\.\s*(\d+)")
TEXT_RULES: list[tuple[str, re.Pattern]] = [
    ("COURT_ORDER_CANCELLED", re.compile(r"судебный приказ.{0,120}?отменить|отмен\w+ судебн\w+ приказ", re.I | re.S)),
    ("CLAIM_DENIED", re.compile(r"в иске отказать|в удовлетворении (?:исковых )?требований.{0,60}?отказать", re.I | re.S)),
    ("APPLICATION_RETURNED", re.compile(r"заявлени\w* о вынесении судебного приказа.{0,120}?возвратить", re.I | re.S)),
    ("DEFECTS_TO_FIX", re.compile(r"оставить без движения", re.I)),
]


@dataclass
class Hit:
    code: str
    evidence: str
    basis: str | None = None      # уточнённая норма; None — из CODES


def _has(arts: list[str], path: str) -> bool:
    return any(a == path or a.startswith(path + "/") for a in arts)


def _basis_from_path(path: str) -> str:
    """'46/1/4' → 'п. 4 ч. 1 ст. 46 229-ФЗ'; '43/2' → 'ч. 2 ст. 43 229-ФЗ'."""
    parts = path.split("/")
    names = ["ст.", "ч.", "п."]
    return " ".join(f"{names[i]} {parts[i]}" for i in reversed(range(len(parts)))) + f" {LAW}"


def _deepest(arts: list[str], article: str) -> str | None:
    cand = [a for a in arts if a == article or a.startswith(article + "/")]
    return max(cand, key=lambda a: a.count("/")) if cand else None


def _line(text: str, *keywords: str) -> str:
    """Первая строка/предложение текста с ключевым словом — цитата для evidence."""
    for kw in keywords:
        for line in re.split(r"\n|(?<=\.)\s+(?=\d+\.\s)", text):
            if kw.lower() in line.lower():
                return re.sub(r"\s+", " ", line).strip()[:EVIDENCE_MAX]
    return ""


def _money(s: str) -> Decimal:
    try:
        return Decimal(s) if s else Decimal("0")
    except InvalidOperation:
        return Decimal("0")


def _xml_hits(doc: Doc) -> list[Hit]:
    x = doc.extra
    arts: list[str] = x.get("npa_articles", [])
    res, adj = x.get("resolution_text", ""), x.get("adjudication_text", "")
    sub = doc.doc_subtype
    m = ARTICLE_RE.search(adj)
    text_path = f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else ""

    def ev(quote: str, path: str | None) -> str:
        parts = [f"ResolutionText: «{quote}»" if quote else "", f"NpaArticle {path}" if path else ""]
        return "; ".join(p for p in parts if p)

    if sub == "O_IP_ACT_END_END":
        if _has(arts, "47/1/1") or text_path == "47/1/1":
            return [Hit("FSSP_END_47_1_1", ev(_line(res, "окончить"), "47/1/1"))]
        rest = _money(x.get("ip_rest_debtsum") or doc.fields["IdDebtSum"].value)
        if _has(arts, "46") or text_path.startswith("46/"):
            path = _deepest(arts, "46") or text_path
            note = f"; остаток долга {rest}" if rest > 0 else ""
            return [Hit("FSSP_END_46_1_4", ev(_line(res, "окончить"), path) + note, _basis_from_path(path))]
        return []
    if sub == "O_IP_ACT_RETURN":
        path = _deepest(arts, "46") or "46/1/4"
        return [Hit("FSSP_RETURN_46_1_4", ev(_line(res, "возвратить исполнительный документ", "окончить"), path),
                    _basis_from_path(path))]
    if sub == "O_IP_ACT_END_STOP":
        path = _deepest(arts, "43")
        reason = _line(adj, "установлено")
        e = ev(_line(res, "прекратить"), path) + (f"; AdjudicationText: «{reason}»" if reason else "")
        return [Hit("FSSP_STOP_43", e, _basis_from_path(path) if path else None)]
    if sub == "O_IP_ACT_REOPEN_CANCEL":
        basis = f"п. {m.group(1)} ч. {m.group(2)} ст. 31 {LAW}" if m and m.group(3) == "31" else None
        return [Hit("FSSP_REFUSAL_31", ev(_line(res, "отказать в возбуждении"), _deepest(arts, "31")), basis)]
    if sub == "O_IP_RES_REOPEN":
        return [Hit("FSSP_OPENED", ev(_line(res, "возбудить"), _deepest(arts, "30")))]
    return []


def _pdf_hits(doc: Doc) -> list[Hit]:
    f = doc.fields
    hits: list[Hit] = []
    if all(not f[c].value for c in ("паспорт", "снилс", "инн") if c in f):
        hits.append(Hit("NO_DEBTOR_ID", f"должник {f['фио'].value or '—'}: паспорт, СНИЛС и ИНН не найдены"))
    try:
        n = int(f["соответчики_кол-во"].value or 0)
    except ValueError:
        n = 0
    if n > 1:
        hits.append(Hit("MULTI_DEBTOR", f"соответчики ({n}): {f['соответчики_фио'].value}"[:EVIDENCE_MAX]))
    text = doc.extra.get("text", "")
    for code, rx in TEXT_RULES:
        m = rx.search(text)
        if m:
            hits.append(Hit(code, re.sub(r"\s+", " ", m.group(0))[:EVIDENCE_MAX]))
    return hits


def _review(doc: Doc) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    conflicts = doc.extra.get("conflicts") or []
    if conflicts:
        out.append(("ID_CONFLICT", "; ".join(f"{c.get('field')}: {' ≠ '.join(map(str, c.get('values', [])))}"
                                              for c in conflicts)))
    missing = [c for c in REQUIRED.get(doc.table, []) if c in doc.fields and not doc.fields[c].value]
    if missing:
        out.append(("REQUIRED_FIELD_MISSING", "пусто: " + ", ".join(missing)))
    validated = set(doc.extra.get("validated", []))
    low = [k for k, v in doc.fields.items()
           if v.value and (v.confidence < LOW_CONFIDENCE or (v.method == "llm" and k not in validated))]
    if low:
        out.append(("LOW_CONFIDENCE", "поля: " + ", ".join(low)))
    arith = doc.extra.get("arith") or {}
    if arith.get("ok") is False:
        out.append(("ARITH_CHECK_FAILED", f"сумма частей {arith.get('sum')} ≠ итог {arith.get('expected')}"))
    return out


def _classified(doc: Doc) -> bool:
    if doc.table == "xml":
        return doc.doc_subtype in XML_SUBTYPES
    return doc.doc_type in PDF_TYPES


def route_to_lawyer(doc: Doc, as_of: date | None = None) -> Route:
    if doc.table == "acts":                     # акты маршрутизирует src/rules/markers.py
        return doc.route
    if not _classified(doc):
        what = doc.doc_subtype or doc.doc_type
        return Route(review=ReviewRoute(flags=["UNCLASSIFIED"], evidence=[f"тип документа: {what}"]))

    hits = _xml_hits(doc) if doc.table == "xml" else _pdf_hits(doc)
    review = _review(doc)
    if doc.table == "xml" and not hits:
        review.insert(0, ("UNCLASSIFIED", f"{doc.doc_subtype}: основание по NpaArticle не распознано"))

    lawyer = LawyerRoute()
    if hits:
        base = base_date(doc.extra.get("DocDate") or (doc.fields["DocDate"].value if "DocDate" in doc.fields else None),
                         as_of)
        deadlines = [d for h in hits if (d := compute(CODES[h.code].deadline, base))]
        lawyer = LawyerRoute(
            level=min((CODES[h.code].level for h in hits), key=LEVEL_RANK.__getitem__),
            reason_codes=[h.code for h in hits],
            basis="; ".join(dict.fromkeys(h.basis or CODES[h.code].basis for h in hits)),
            deadline=min(deadlines).isoformat() if deadlines else None,
            evidence=" | ".join(h.evidence for h in hits if h.evidence) or None,
        )
    return Route(lawyer=lawyer, review=ReviewRoute(flags=[f for f, _ in review], evidence=[e for _, e in review]))


if __name__ == "__main__":
    import argparse
    import json

    from src.core.contract import load

    ap = argparse.ArgumentParser(description="маршрут юристу для doc.json")
    ap.add_argument("doc", help="путь к doc_*.json или к XML ФССП")
    ap.add_argument("--as-of", type=date.fromisoformat, default=None)
    a = ap.parse_args()
    if a.doc.lower().endswith(".xml"):
        from src.xmlbranch.to_doc import xml_to_doc  # pylint: disable=import-outside-toplevel
        d = xml_to_doc(a.doc, use_llm=False)
    else:
        d = load(a.doc)
    print(json.dumps(route_to_lawyer(d, as_of=a.as_of).model_dump(), ensure_ascii=False, indent=2))
