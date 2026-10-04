import asyncio
import re
import sys
import time
from decimal import Decimal, InvalidOperation
from functools import cache
from pathlib import Path

from src.acts.to_doc import act_text_to_doc
from src.core.columns import OCR_FIELDS, XML_FIELDS
from src.core.contract import Doc, FieldValue, ReviewRoute, Route
from src.llm import client as llm
from src.llm.schemas import ocr_schema
from src.pdf_branch.core.container import Container
from src.pdf_branch.services.classification.document_classification import (
    DocumentClass,
    SourceKind,
)
from src.pdf_branch.utils import compat_pymorphy  # noqa: F401
from src.rules.markers import looks_like_court_act

# .env здесь не читаем: это делают точки входа (run_examples.py, src/ui/app.py) — иначе импорт модуля
# перетирал переменные окружения и тесты отправляли реальные письма.

DATA_ROOT = "data/courts_anonymized"            # doc.file считается от этого корня — как в labels/ и в XML-ветке


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
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]

# Признак постановления ФССП в PDF. Только служебная шапка выгрузки: фраза «судебный пристав-исполнитель»
# встречается в любом исполнительном листе и раньше уводила все сканы ИЛ в пустой fssp_doc.
FSSP_PDF_RE = re.compile(r"Вид документа:\s*O_IP_")


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


def to_inn(s: str) -> str:
    """ИНН должника-физлица — 12 цифр. 10 цифр — это ИНН организации (взыскателя), в столбец не кладём."""
    digits = re.sub(r"\D", "", s)
    return digits if len(digits) == 12 else ""


# --- ФИО в именительный падеж -------------------------------------------------------------------------
# В приказах должник стоит в родительном («с Макетнова Леонтия Степановича»), в разметке — именительный.
# Род берём из отчества (надёжнее pymorphy), фамилию склоняем правилами, имя и отчество — pymorphy.

try:
    import pymorphy3
    _MORPH = pymorphy3.MorphAnalyzer()
except Exception:                                   # pragma: no cover — без словарей оставляем как есть
    _MORPH = None

_MASC_SURNAME = (("ова", "ов"), ("ева", "ев"), ("ёва", "ёв"), ("ина", "ин"), ("ына", "ын"),
                 ("ого", "ий"), ("его", "ий"))
_FEM_SURNAME = (("овой", "ова"), ("евой", "ева"), ("ёвой", "ёва"), ("иной", "ина"), ("ыной", "ына"),
                ("ской", "ская"), ("цкой", "цкая"), ("овую", "ова"), ("евую", "ева"),
                ("ову", "ова"), ("еву", "ева"), ("ину", "ина"))


def _cap(word: str) -> str:
    return "-".join(p[:1].upper() + p[1:] for p in word.split("-"))


def _gender(patronymic: str) -> str | None:
    p = patronymic.lower()
    if p.endswith(("ич", "ича", "ичу", "ичем", "иче", "ыч", "ыча", "ычу")):
        return "masc"
    if p.endswith(("на", "ны", "не", "ну", "ной")):
        return "femn"
    return None


def _nomn(word: str, gender: str | None, tags: tuple[str, ...]) -> str:
    """Именительный падеж через pymorphy: берём разбор с нужной пометкой (Name/Patr) и полом."""
    if not _MORPH or not word:
        return word
    parses = [p for p in _MORPH.parse(word.lower()) if any(t in p.tag for t in tags)]
    if gender:
        parses = [p for p in parses if p.tag.gender in (gender, None)] or parses
    if not parses:
        return word
    form = parses[0].inflect({"nomn"})
    return _cap(form.word if form else parses[0].normal_form)


def _surname_nomn(word: str, gender: str | None) -> str:
    low = word.lower()
    rules = _MASC_SURNAME if gender == "masc" else _FEM_SURNAME if gender == "femn" else ()
    for end, repl in rules:
        if low.endswith(end):
            return _cap(low[: -len(end)] + repl)
    return _cap(low)


def to_nominative(fio: str) -> str:
    parts = fio.split()
    if len(parts) != 3:
        return fio
    surname, name, patronymic = parts
    gender = _gender(patronymic)
    return " ".join((
        _surname_nomn(surname, gender),
        _nomn(name, gender, ("Name",)),
        _nomn(patronymic, gender, ("Patr",)),
    ))


FORMATS = {
    "дата рождения": to_date, "дело_дата": to_date,
    "период_дз_начало": to_date, "период_дз_оконч": to_date,
    "дз_осн": to_money, "дз_пени": to_money, "дз_пошлина": to_money,
    "инн": to_inn,
    "фио": to_nominative,
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

        if not old.value:                           # regex_first: LLM только дозаполняет пустое
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
    """Фамилия/имя/отчество — из ФИО. Соответчики — по шаблону заказчика: ВСЕ должники как в тексте
    (включая основного), количество — их число; один должник → он же в списке, количество 1."""
    fio = fields["фио"]

    if len(parts := fio.value.split()) == 3:
        for col, value in zip(("фамилия", "имя", "отчетство"), parts):
            fields[col] = FieldValue(
                value=value, evidence=fio.evidence,
                confidence=fio.confidence, method="derived"
            )

    co = fields["соответчики_фио"]
    debtors: list[str] = []
    for p in people(co.value):
        if key(p) not in map(key, debtors):
            debtors.append(p)
    if not debtors and fio.value:
        debtors = [fio.evidence or fio.value]       # как в тексте — так требует шаблон
    if not debtors:
        return

    fields["соответчики_фио"] = FieldValue(
        value=", ".join(debtors), evidence=co.evidence or fio.evidence,
        confidence=co.confidence if co.value else fio.confidence,
        method=co.method if co.value else "derived",
    )
    fields["соответчики_кол-во"] = FieldValue(
        value=str(len(debtors)), evidence="по списку должников",
        confidence=0.9, method="derived",
    )


def make_doc(path: Path, rel: str, table: str, doc_type: str, fields: dict, **kw) -> Doc:
    return Doc(doc_id=path.stem, source_type="pdf", file=rel,
               table=table, doc_type=doc_type, fields=fields, **kw)


def fssp_doc(path: Path, rel: str) -> Doc:
    """Постановление ФССП, пришедшее одним PDF без XML: реквизиты не извлекаем, отдаём на ручную проверку."""
    return make_doc(path, rel, "xml", "постановление ФССП",
                    {c: empty() for c in XML_FIELDS},
                    route=Route(review=ReviewRoute(
                        flags=["REQUIRED_FIELD_MISSING"],
                        evidence=["постановление ФССП в PDF: реквизиты берутся из XML-выгрузки"],
                    )))


def pdf_to_doc(path: str | Path, data_root: str | Path = DATA_ROOT) -> Doc | None:
    """PDF → Doc. None — если это PDF-двойник постановления ФССП: его обрабатывает XML-ветка."""
    path, data_root = Path(path), Path(data_root)
    rel = str(path.relative_to(data_root)) if path.is_relative_to(data_root) else path.name
    enabled = llm.enabled()

    log(f"Файл: {path} | LLM: {llm.model() if enabled else 'выключена'}")

    if path.with_suffix(".xml").exists():
        log(f"{path.name}: есть XML-двойник, PDF пропускаем")
        return None

    a = asyncio.run(get_service().analyze(path.read_bytes(), path.name))
    text = "\n".join(page["recognized_text"] for page in a.ocr)
    print(text)
    doc_class, source = a.classification.doc_class, a.classification.source_kind

    log(
        f"OCR {a.timings_ms['ocr']} мс, правила {a.timings_ms['ner']} мс | "
        f"страниц: {len(a.ocr)}, символов: {len(text)}, "
        f"класс: {doc_class.value}, источник: {source.value}"
    )

    if FSSP_PDF_RE.search(text):
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
            flags=["LOW_CONFIDENCE"] if conflicts else [], evidence=conflicts
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
    from dotenv import load_dotenv

    from src.core.contract import dump

    load_dotenv()
    name = sys.argv[1] if len(sys.argv) > 1 else input("Имя файла: ")
    doc = pdf_to_doc(find_pdf(name))
    if doc is None:
        sys.exit("PDF-двойник постановления ФССП: обрабатывается XML-веткой")
    dump(doc, f"out/{doc.doc_id}.json")
    log(f"Готово: {doc.doc_type} → out/{doc.doc_id}.json")
