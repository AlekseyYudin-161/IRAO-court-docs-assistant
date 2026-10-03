"""XML постановления ФССП → doc.json (контракт v2.4). Маршрут не ставит — это route_to_lawyer() в src/rules.

Столбец → FieldValue: копия тега — method copy, evidence xpath; регулярка — method regex, evidence срез
IdDebtText; адрес — method derived; пусто — reason NOT_IN_TEXT. Деньги в value как в теге («134288.50»),
в формат csv переводит экспорт. Если сработал триггер LLM-fallback — reason LLM_FALLBACK_CANDIDATE,
значение правил не затирается; LLM (если включена) только дозаполняет пустые поля с цитатой из текста.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from src.core.columns import XML_FIELDS
from src.core.contract import Doc, FieldValue
from src.xmlbranch.address import split_address
from src.xmlbranch.derive import DATE_COLUMNS, DERIVED_COLUMNS, arith_check, derive_from_text, iso_date, money
from src.xmlbranch.doctype import doctype2
from src.xmlbranch.parse import COPY_COLUMNS, parse_xml, rule_extra

log = logging.getLogger("xmlbranch")
ADDRESS_COLUMNS = ["street", "dom", "kv"]
EVIDENCE_MAX = 200


def _empty(method: str = "none", reason: str = "NOT_IN_TEXT") -> FieldValue:
    return FieldValue(value="", confidence=0.0, method=method, reason=reason)


def _copy(tags: dict[str, str], col: str) -> FieldValue:
    v = tags.get(col, "")
    if not v.strip():
        return _empty("copy")
    return FieldValue(value=v, evidence=f"xpath:/OIp/{col}", confidence=1.0, method="copy")


def _slice(text: str, span: tuple[int, int]) -> str:
    a, b = span
    return f"IdDebtText[{a}:{b}]: {text[a:b]}"[:EVIDENCE_MAX]


def _llm_fill(text: str, cols: list[str]) -> dict[str, tuple[str, str]]:
    """Дозаполнение пустых полей локальной LLM. Принимаем значение, только если цитата есть в тексте
    и значение нормализуется (дата → ISO, сумма → Decimal). Ответ: {столбец: (value, quote)}."""
    from src.llm import client as llm_client  # pylint: disable=import-outside-toplevel
    if not cols or not llm_client.enabled():
        return {}
    schema = {"type": "object", "required": cols, "properties": {
        c: {"type": "object", "required": ["value", "quote"],
            "properties": {"value": {"type": "string"}, "quote": {"type": "string"}}} for c in cols}}
    out = llm_client.extract(text, schema, prompt="xml_fallback") or {}
    flat = re.sub(r"\s+", " ", text)
    got: dict[str, tuple[str, str]] = {}
    for c in cols:
        item = out.get(c) or {}
        raw, quote = str(item.get("value", "")).strip(), re.sub(r"\s+", " ", str(item.get("quote", ""))).strip()
        if not raw or not quote or quote not in flat:
            continue
        if c in DATE_COLUMNS:
            v = raw if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw) else iso_date(raw)
        else:
            v = money(raw)
        if v:
            got[c] = (v, quote)
    return got


def xml_to_doc(path: str | Path, use_llm: bool | None = None, posthoc: bool = True) -> Doc:
    """use_llm=None — как решил llm_client (NO_LLM / --no-llm); False — LLM не вызываем вовсе."""
    t0 = time.time()
    p = Path(path)
    tags, root = parse_xml(p)
    code = tags.get("DocType", "")
    text, adr = tags.get("IdDebtText", ""), tags.get("DbtrAdr", "")

    f: dict[str, FieldValue] = {c: _copy(tags, c) for c in COPY_COLUMNS}
    dt2 = doctype2(code)
    f["DocType2"] = (FieldValue(value=dt2, evidence=f"DocType={code}", confidence=1.0, method="lookup")
                     if dt2 else _empty("lookup"))

    derived, fallback = derive_from_text(text, tags.get("IdDebtSum", ""), posthoc=posthoc)
    for c, d in derived.items():
        if not d.value:
            f[c] = _empty("regex")
        elif d.span:
            f[c] = FieldValue(value=d.value, evidence=_slice(text, d.span), confidence=d.confidence, method="regex")
        else:
            f[c] = FieldValue(value=d.value, evidence=f"xpath:/OIp/IdDebtSum ({d.note})", confidence=d.confidence,
                              method="derived")

    a = split_address(adr, text, posthoc=posthoc)
    for c in ADDRESS_COLUMNS:
        v = getattr(a, c)
        ev = "xpath:/OIp/DbtrAdr" + (f"; тип улицы: {a.type_evidence}" if c == "street" and a.type_evidence else "")
        f[c] = (FieldValue(value=v, evidence=ev[:EVIDENCE_MAX], confidence=0.9 if a.structured else 0.6, method="derived")
                if v else _empty("derived"))
    if adr.strip() and not a.structured:
        fallback += ADDRESS_COLUMNS

    extra = rule_extra(tags, root)
    extra["DocDate"] = tags.get("DocDate", "")
    extra["llm_fallback"] = list(dict.fromkeys(fallback))
    arith = arith_check(text, tags.get("IdDebtSum", ""), derived)
    if arith:
        extra["arith"] = arith

    for c in extra["llm_fallback"]:
        f[c].reason = "LLM_FALLBACK_CANDIDATE"
    t_llm = time.time()
    if use_llm is not False:
        filled = _llm_fill(text, [c for c in extra["llm_fallback"] if not f[c].value and c in DERIVED_COLUMNS])
        for c, (v, quote) in filled.items():
            f[c] = FieldValue(value=v, evidence=f"llm: «{quote}»"[:EVIDENCE_MAX], confidence=0.6, method="llm",
                              reason="LLM_FALLBACK_CANDIDATE")
        extra["validated"] = sorted(filled)     # цитата найдена, значение нормализовано — валидатор пройден
    missing = [c for c in XML_FIELDS if c not in f]
    assert not missing, missing

    return Doc(doc_id=p.stem, source_type="xml", file=f"fssp/{code or 'unknown'}/{p.name}", table="xml",
               doc_type="постановление ФССП" if code else "unknown", doc_subtype=code or None,
               fields={c: f[c] for c in XML_FIELDS}, extra=extra,
               timings_ms={"extract": int((t_llm - t0) * 1000), "llm": int((time.time() - t_llm) * 1000)})

