import asyncio
import re
import sys
import time
from decimal import Decimal, InvalidOperation
from functools import cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=True)

from src.pdf_branch.utils import compat_pymorphy  # noqa: F401,E402
from src.acts.to_doc import act_text_to_doc  # noqa: E402
from src.core.columns import OCR_FIELDS, XML_FIELDS  # noqa: E402
from src.core.contract import Doc, FieldValue, ReviewRoute, Route  # noqa: E402
from src.llm import client as llm  # noqa: E402
from src.llm.schemas import ocr_schema  # noqa: E402
from src.pdf_branch.core.container import Container  # noqa: E402
from src.pdf_branch.services.classification.document_classification import DocumentClass, SourceKind  # noqa: E402
from src.rules.markers import looks_like_court_act  # noqa: E402


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


DOC_TYPE = {
    DocumentClass.FSSP_RESOLUTION: "постановление ФССП",
    DocumentClass.WRIT_OF_EXECUTION: "ИЛ",
    DocumentClass.COURT_ORDER: "приказ",
}

COLUMN_TO_RULE = {
    "улица": "street", "дом": "house", "кв": "flat",
    "фамилия": "surname", "имя": "first_name", "отчетство": "patronymic", "фио": "fio",
    "дата рождения": "birth_date", "паспорт": "passport", "снилс": "snils", "инн": "inn",
    "дело_номер": "case_number", "дело_дата": "case_date",
    "период_дз_начало": "period_start", "период_дз_оконч": "period_end",
    "дз_осн": "debt_main", "дз_пени": "debt_penalty", "дз_пошлина": "debt_duty",
    "соответчики_кол-во": "co_debtors_count", "соответчики_фио": "co_debtors",
}

DERIVED_COLS = {"фамилия", "имя", "отчетство", "соответчики_кол-во"}
NAME_COLS = {"фио", "соответчики_фио"}
MONTHS = "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split()


def to_date(s: str) -> str:
    if m := re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s):
        d, mth, y = m.groups()
    elif m := re.search(r"(\d{1,2})\s+([а-яё]+)\s+(\d{4})", s.lower()):
        if m[2] not in MONTHS:
            return ""
        d, mth, y = m[1], MONTHS.index(m[2]) + 1, m[3]
    else:
        return ""
    return f"{y}-{int(mth):02d}-{int(d):02d}"


def to_money(s: str) -> str:
    m = re.search(r"\d[\d\s]*(?:[,.]\d+)?", s)
    if not m:
        return ""
    try:
        return f"{Decimal(m.group().replace(' ', '').replace(',', '.')):.2f}"
    except InvalidOperation:
        return ""


FORMATS = {
    "дата рождения": to_date, "дело_дата": to_date,
    "период_дз_начало": to_date, "период_дз_оконч": to_date,
    "дз_осн": to_money, "дз_пени": to_money, "дз_пошлина": to_money,
    "инн": lambda s: re.sub(r"\D", "", s),
}


def as_text(value) -> str:
    if isinstance(value, list):
        return "; ".join(map(str, value))
    return "" if value in (None, 0) else str(value).strip()


def normalize(col: str, value) -> str:
    value = as_text(value)
    return FORMATS.get(col, str)(value) if value else ""


def key(s: str) -> str:
    return re.sub(r"[\W_]+", "", s.lower().replace("ё", "е"))


def people(s: str) -> list[str]:
    return [x.strip() for x in re.split(r"[;,]", s) if x.strip()]


def same(a: str, b: str) -> bool:
    return sorted(map(key, people(a))) == sorted(map(key, people(b)))


def empty(reason="NOT_IN_TEXT", method="none") -> FieldValue:
    return FieldValue(value="", method=method, reason=reason)


@cache
def get_service():
    log("Загрузка сервисов...")
    return Container().document_processing_service()


def fields_from_rules(rule: dict) -> dict[str, FieldValue]:
    fields = {}
    for col in OCR_FIELDS:
        raw = rule.get(COLUMN_TO_RULE[col])
        value = normalize(col, raw)
        fields[col] = (
            FieldValue(value=value, evidence=as_text(raw)[:200], confidence=0.9, method="regex")
            if value else empty()
        )
    return fields


def check_with_llm(fields: dict[str, FieldValue], text: str) -> list[str]:
    if not llm.enabled():
        for col, field in fields.items():
            if not field.value:
                fields[col] = empty("LLM_DISABLED")
        return []

    started = time.perf_counter()
    log("Запрашиваю LLM...")

    try:
        answer = llm.extract(text, ocr_schema()) or {}
    except Exception as e:
        log(f"LLM не вызвана: {type(e).__name__}: {e}")
        return []

    log(f"LLM ответила за {time.perf_counter() - started:.1f} с")
    text_key, conflicts = key(text), []

    for col in OCR_FIELDS:
        item = answer.get(col) or {}
        value = str(item.get("value") or "").strip()
        quote = str(item.get("quote") or "").strip()

        if not value:
            continue

        old = fields[col]

        if not any(key(x) and key(x) in text_key for x in (quote, value)):
            if not old.value:
                fields[col] = empty("VALIDATOR_FAILED", "llm")
            continue

        value = normalize(col, value)
        if not value:
            continue

        if not old.value or col in NAME_COLS:
            fields[col] = FieldValue(
                value=value, evidence=quote[:200] or value,
                confidence=0.6, method="llm"
            )
        elif col not in DERIVED_COLS:
            agree = same(old.value, value)
            if not agree:
                conflicts.append(f"{col}: правила={old.value!r}, LLM={value!r}")
            fields[col] = old.model_copy(update={"confidence": 0.95 if agree else 0.5})

    return conflicts


def fix_derived(fields: dict[str, FieldValue]) -> None:
    fio = fields["фио"]

    if len(parts := fio.value.split()) == 3:
        for col, value in zip(("фамилия", "имя", "отчетство"), parts):
            fields[col] = FieldValue(
                value=value, evidence=fio.evidence,
                confidence=fio.confidence, method="derived"
            )

    co = fields["соответчики_фио"]
    if not co.value:
        return

    others = [p for p in people(co.value) if key(p) != key(fio.value)]
    fields["соответчики_фио"] = (
        co.model_copy(update={"value": "; ".join(others)}) if others else empty()
    )
    fields["соответчики_кол-во"] = (
        FieldValue(value=str(len(others)), evidence="по списку соответчиков",
                   confidence=0.9, method="derived") if others else empty()
    )


def make_doc(path: Path, rel: str, table: str, doc_type: str, fields: dict, **kw) -> Doc:
    return Doc(doc_id=path.stem, source_type="pdf", file=rel,
               table=table, doc_type=doc_type, fields=fields, **kw)


def fssp_doc(path: Path, rel: str) -> Doc:
    return make_doc(path, rel, "xml", "постановление ФССП",
                    {c: empty() for c in XML_FIELDS},
                    extra={"twin": f"{path.stem}.xml"})


def pdf_to_doc(path: str | Path, data_root="data") -> Doc:
    path = Path(path)
    rel = str(path.relative_to(data_root)) if path.is_relative_to(data_root) else path.name
    enabled = llm.enabled()

    log(f"Файл: {path} | LLM: {llm.model() if enabled else 'выключена'}")

    if path.with_suffix(".xml").exists():
        return fssp_doc(path, rel)

    a = asyncio.run(get_service().analyze(path.read_bytes(), path.name))
    text = "\n".join(page["recognized_text"] for page in a.ocr)
    doc_class, source = a.classification.doc_class, a.classification.source_kind

    log(
        f"OCR {a.timings_ms['ocr']} мс, правила {a.timings_ms['ner']} мс | "
        f"страниц: {len(a.ocr)}, символов: {len(text)}, "
        f"класс: {doc_class.value}, источник: {source.value}"
    )

    if re.search(r"Вид документа:\s*O_IP_|Судебный пристав-исполнитель", text):
        return fssp_doc(path, rel)

    if doc_class is DocumentClass.UNKNOWN:
        if source is SourceKind.TEXT_LAYER and looks_like_court_act(text):
            return act_text_to_doc(text, path.stem, rel)
        return make_doc(
            path, rel, "ocr", "unknown", {c: empty() for c in OCR_FIELDS},
            timings_ms=a.timings_ms,
            route=Route(review=ReviewRoute(
                flags=["UNCLASSIFIED"], evidence=["класс не распознан"]
            )),
        )

    extraction = a.processed[0].rule_extraction.model_dump() if a.processed else {}
    fields = fields_from_rules(extraction)
    log(f"После правил заполнено: {sum(bool(f.value) for f in fields.values())}/20")

    started = time.perf_counter() if enabled else None
    conflicts = check_with_llm(fields, text)

    if enabled:
        log(
            f"После LLM заполнено: {sum(bool(f.value) for f in fields.values())}/20, "
            f"расхождений: {len(conflicts)}"
        )

    fix_derived(fields)

    doc_type = DOC_TYPE[doc_class] + (" эл" if source is not SourceKind.SCAN else "")
    llm_ms = int((time.perf_counter() - started) * 1000) if started else 0

    return make_doc(
        path, rel, "ocr", doc_type, fields,
        route=Route(review=ReviewRoute(
            flags=["LOW_CONFIDENCE"] * len(conflicts), evidence=conflicts
        )),
        timings_ms={**a.timings_ms, "llm": llm_ms},
    )


def find_pdf(name: str, data_root="data") -> Path:
    name = name.strip("\"'")
    if Path(name).exists():
        return Path(name)
    found = sorted(Path(data_root).rglob(f"{Path(name).stem}.pdf"))
    return found[0] if found else sys.exit(f"Файл '{name}' не найден")


if __name__ == "__main__":
    from src.core.contract import dump

    name = sys.argv[1] if len(sys.argv) > 1 else input("Имя файла: ")
    doc = pdf_to_doc(find_pdf(name))
    dump(doc, f"out/{doc.doc_id}.json")
    log(f"Готово: {doc.doc_type} → out/{doc.doc_id}.json")
