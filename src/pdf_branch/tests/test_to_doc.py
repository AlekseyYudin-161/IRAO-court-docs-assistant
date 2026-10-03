from types import SimpleNamespace

import pytest

from src.core.columns import OCR_FIELDS
from src.pdf_branch.services import to_doc


def test_to_date():
    assert to_doc.to_date("11.03.1976") == "1976-03-11"
    assert to_doc.to_date("11 марта 1976") == "1976-03-11"
    assert to_doc.to_date("invalid") == ""


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("68326,38 RUB", "68326.38"),
        ("1 000,5 руб.", "1000.50"),
        ("invalid", ""),
    ],
)
def test_to_money(value, expected):
    assert to_doc.to_money(value) == expected


def test_normalize():
    assert to_doc.normalize("инн", "123-456-789") == "123456789"
    assert to_doc.normalize("дата рождения", "11.03.1976") == "1976-03-11"


def test_same_people():
    assert to_doc.same("Иванов Иван; Петров Пётр", "Петров Петр; Иванов Иван")
    assert not to_doc.same("Иванов Иван", "Петров Петр")


def test_fields_from_rules():
    fields = to_doc.fields_from_rules({
        "fio": "Иванов Иван Иванович",
        "birth_date": "11.03.1976",
        "inn": "123 456 789",
    })

    assert fields["фио"].value == "Иванов Иван Иванович"
    assert fields["фио"].method == "regex"
    assert fields["дата рождения"].value == "1976-03-11"
    assert fields["инн"].value == "123456789"
    assert not fields["паспорт"].value


def test_fix_derived():
    fields = {col: to_doc.empty() for col in OCR_FIELDS}
    fields["фио"] = to_doc.FieldValue(
        value="Иванов Иван Иванович",
        evidence="Иванова Иван Ивановича",
        confidence=0.6,
        method="llm",
    )
    fields["соответчики_фио"] = to_doc.FieldValue(
        value="Иванов Иван Иванович; Петров Пётр Петрович",
        evidence="Иванов Иван Иванович; Петров Пётр Петрович",
        confidence=0.6,
        method="llm",
    )

    to_doc.fix_derived(fields)

    assert fields["фамилия"].value == "Иванов"
    assert fields["имя"].value == "Иван"
    assert fields["отчетство"].value == "Иванович"
    assert fields["соответчики_фио"].value == "Петров Пётр Петрович"
    assert fields["соответчики_кол-во"].value == "1"


def test_check_with_llm_disabled(monkeypatch):
    monkeypatch.setattr(to_doc.llm, "enabled", lambda: False)

    fields = {col: to_doc.empty() for col in OCR_FIELDS}
    conflicts = to_doc.check_with_llm(fields, "текст")

    assert conflicts == []
    assert all(f.reason == "LLM_DISABLED" for f in fields.values())


def test_check_with_llm_fills_empty(monkeypatch):
    monkeypatch.setattr(to_doc.llm, "enabled", lambda: True)
    monkeypatch.setattr(
        to_doc.llm,
        "extract",
        lambda text, schema: {
            "фио": {
                "value": "Иванов Иван Иванович",
                "quote": "Иванов Иван Иванович",
            }
        },
    )

    fields = {col: to_doc.empty() for col in OCR_FIELDS}
    conflicts = to_doc.check_with_llm(
        fields,
        "Должник: Иванов Иван Иванович",
    )

    assert conflicts == []
    assert fields["фио"].value == "Иванов Иван Иванович"
    assert fields["фио"].method == "llm"


def test_check_with_llm_detects_conflict(monkeypatch):
    monkeypatch.setattr(to_doc.llm, "enabled", lambda: True)
    monkeypatch.setattr(
        to_doc.llm,
        "extract",
        lambda text, schema: {
            "инн": {"value": "2222222222", "quote": "ИНН 2222222222"}
        },
    )

    fields = {col: to_doc.empty() for col in OCR_FIELDS}
    fields["инн"] = to_doc.FieldValue(
        value="1111111111",
        evidence="ИНН 1111111111",
        confidence=0.9,
        method="regex",
    )

    conflicts = to_doc.check_with_llm(
        fields,
        "ИНН 1111111111. Также встречается ИНН 2222222222.",
    )

    assert len(conflicts) == 1
    assert fields["инн"].value == "1111111111"
    assert fields["инн"].confidence == 0.5


def test_check_with_llm_rejects_unverified_value(monkeypatch):
    monkeypatch.setattr(to_doc.llm, "enabled", lambda: True)
    monkeypatch.setattr(
        to_doc.llm,
        "extract",
        lambda text, schema: {
            "инн": {"value": "9999999999", "quote": "несуществующая цитата"}
        },
    )

    fields = {col: to_doc.empty() for col in OCR_FIELDS}

    to_doc.check_with_llm(fields, "В тексте нет этого ИНН.")

    assert fields["инн"].value == ""
    assert fields["инн"].reason == "VALIDATOR_FAILED"


def test_find_pdf(tmp_path):
    pdf = tmp_path / "ocr_007.pdf"
    pdf.touch()

    assert to_doc.find_pdf("ocr_007", tmp_path) == pdf
    assert to_doc.find_pdf("ocr_007.pdf", tmp_path) == pdf


def test_pdf_to_doc_fssp_by_xml(tmp_path):
    pdf = tmp_path / "ocr_001.pdf"
    pdf.touch()
    pdf.with_suffix(".xml").touch()

    doc = to_doc.pdf_to_doc(pdf, tmp_path)

    assert doc.table == "xml"
    assert doc.doc_type == "постановление ФССП"
    assert doc.extra["twin"] == "ocr_001.xml"


def test_pdf_to_doc_skips_llm_when_disabled(monkeypatch, tmp_path):
    pdf = tmp_path / "ocr_009.pdf"
    pdf.touch()

    monkeypatch.setattr(to_doc.llm, "enabled", lambda: False)

    analysis = SimpleNamespace(
        ocr=[{"recognized_text": "Судебный приказ № 1"}],
        classification=SimpleNamespace(
            doc_class=to_doc.DocumentClass.COURT_ORDER,
            source_kind=to_doc.SourceKind.TEXT_LAYER,
        ),
        timings_ms={"ocr": 10, "ner": 5},
        processed=[SimpleNamespace(
            rule_extraction=SimpleNamespace(
                model_dump=lambda: {"fio": "Иванов Иван Иванович"}
            )
        )],
    )

    class FakeService:
        async def analyze(self, *args):
            return analysis

    monkeypatch.setattr(to_doc, "get_service", lambda: FakeService())

    extract = pytest.MonkeyPatch()
    extract.setattr(
        to_doc.llm,
        "extract",
        lambda *_: pytest.fail("LLM не должна вызываться"),
    )

    doc = to_doc.pdf_to_doc(pdf, tmp_path)

    extract.undo()

    assert doc.doc_type == "приказ эл"
    assert doc.timings_ms["llm"] == 0

def test_to_date_ignores_extra_text():
    assert to_doc.to_date("дата рождения: 11.03.1976") == "1976-03-11"

def test_to_money_integer():
    assert to_doc.to_money("1000 руб.") == "1000.00"

def test_normalize_default():
    assert to_doc.normalize("паспорт", 123456) == "123456"

def test_fields_from_rules_list():
    fields = to_doc.fields_from_rules({
        "co_debtors": ["Иванов Иван", "Петров Пётр"]
    })

    assert fields["соответчики_фио"].value == "Иванов Иван; Петров Пётр"
def test_fix_derived_invalid_fio():
    fields = {col: to_doc.empty() for col in OCR_FIELDS}
    fields["фио"] = to_doc.FieldValue(value="Иванов Иван")

    to_doc.fix_derived(fields)

    assert not fields["фамилия"].value
    assert not fields["имя"].value
    assert not fields["отчетство"].value

def test_as_text():
    assert to_doc.as_text(["Иванов", "Петров"]) == "Иванов; Петров"
    assert to_doc.as_text(None) == ""
    assert to_doc.as_text(0) == ""
    assert to_doc.as_text("  abc  ") == "abc"


def test_key_normalizes():
    assert to_doc.key("Иванов, Иван!") == "ивановиван"
    assert to_doc.key("ПЁТР") == "петр"


def test_people():
    assert to_doc.people("Иванов; Петров, Сидоров") == [
        "Иванов", "Петров", "Сидоров"
    ]


def test_same_single_value():
    assert to_doc.same("Иванов Иван", "иванов иван")


def test_fields_from_rules_confidence():
    fields = to_doc.fields_from_rules({"fio": "Иванов Иван Иванович"})

    assert fields["фио"].confidence == 0.9
    assert fields["фио"].method == "regex"
    assert fields["фио"].evidence == "Иванов Иван Иванович"


def test_fields_from_rules_money_and_date():
    fields = to_doc.fields_from_rules({
        "birth_date": "11.03.1976",
        "debt_main": "1000,50",
        "debt_penalty": "20",
        "debt_duty": "10,5",
    })

    assert fields["дата рождения"].value == "1976-03-11"
    assert fields["дз_осн"].value == "1000.50"
    assert fields["дз_пени"].value == "20.00"
    assert fields["дз_пошлина"].value == "10.50"


def test_llm_fills_missing_date(monkeypatch):
    monkeypatch.setattr(to_doc.llm, "enabled", lambda: True)
    monkeypatch.setattr(
        to_doc.llm, "extract",
        lambda *_: {
            "дата рождения": {
                "value": "11.03.1976",
                "quote": "Дата рождения 11.03.1976",
            }
        },
    )

    fields = {col: to_doc.empty() for col in OCR_FIELDS}

    to_doc.check_with_llm(fields, "Дата рождения 11.03.1976")

    assert fields["дата рождения"].value == "1976-03-11"
    assert fields["дата рождения"].method == "llm"


def test_llm_accepts_value_without_quote(monkeypatch):
    monkeypatch.setattr(to_doc.llm, "enabled", lambda: True)
    monkeypatch.setattr(
        to_doc.llm, "extract",
        lambda *_: {
            "инн": {"value": "1234567890", "quote": ""}
        },
    )

    fields = {col: to_doc.empty() for col in OCR_FIELDS}

    to_doc.check_with_llm(fields, "ИНН: 1234567890")

    assert fields["инн"].value == "1234567890"


def test_llm_rejects_value_not_in_text(monkeypatch):
    monkeypatch.setattr(to_doc.llm, "enabled", lambda: True)
    monkeypatch.setattr(
        to_doc.llm, "extract",
        lambda *_: {
            "инн": {"value": "1234567890", "quote": "ИНН 1234567890"}
        },
    )

    fields = {col: to_doc.empty() for col in OCR_FIELDS}
    to_doc.check_with_llm(fields, "ИНН в документе отсутствует")

    assert fields["инн"].value == ""
    assert fields["инн"].reason == "VALIDATOR_FAILED"


def test_llm_error_does_not_break_pipeline(monkeypatch):
    monkeypatch.setattr(to_doc.llm, "enabled", lambda: True)

    def fail(*_):
        raise RuntimeError("Ollama unavailable")

    monkeypatch.setattr(to_doc.llm, "extract", fail)

    fields = {col: to_doc.empty() for col in OCR_FIELDS}

    assert to_doc.check_with_llm(fields, "текст") == []


def test_llm_agrees_with_rule(monkeypatch):
    monkeypatch.setattr(to_doc.llm, "enabled", lambda: True)
    monkeypatch.setattr(
        to_doc.llm, "extract",
        lambda *_: {
            "инн": {
                "value": "1234567890",
                "quote": "ИНН 1234567890",
            }
        },
    )

    fields = {col: to_doc.empty() for col in OCR_FIELDS}
    fields["инн"] = to_doc.FieldValue(
        value="1234567890",
        evidence="ИНН 1234567890",
        confidence=0.9,
        method="regex",
    )

    conflicts = to_doc.check_with_llm(fields, "ИНН 1234567890")

    assert conflicts == []
    assert fields["инн"].value == "1234567890"
    assert fields["инн"].confidence == 0.95
    assert fields["инн"].method == "regex"


def test_llm_overrides_fio(monkeypatch):
    monkeypatch.setattr(to_doc.llm, "enabled", lambda: True)
    monkeypatch.setattr(
        to_doc.llm, "extract",
        lambda *_: {
            "фио": {
                "value": "Иванов Иван Иванович",
                "quote": "Иванов Иван Иванович",
            }
        },
    )

    fields = {col: to_doc.empty() for col in OCR_FIELDS}
    fields["фио"] = to_doc.FieldValue(
        value="Иванова Ивана Ивановича",
        evidence="Иванова Ивана Ивановича",
        confidence=0.9,
        method="regex",
    )

    to_doc.check_with_llm(fields, "Иванов Иван Иванович")

    assert fields["фио"].value == "Иванов Иван Иванович"
    assert fields["фио"].method == "llm"


def test_fix_derived_without_fio():
    fields = {col: to_doc.empty() for col in OCR_FIELDS}

    to_doc.fix_derived(fields)

    assert not fields["фамилия"].value
    assert not fields["имя"].value
    assert not fields["отчетство"].value


def test_fix_derived_invalid_fio():
    fields = {col: to_doc.empty() for col in OCR_FIELDS}
    fields["фио"] = to_doc.FieldValue(value="Иванов Иван")

    to_doc.fix_derived(fields)

    assert not fields["фамилия"].value
    assert not fields["имя"].value
    assert not fields["отчетство"].value


def test_fix_derived_removes_main_debtor():
    fields = {col: to_doc.empty() for col in OCR_FIELDS}
    fields["фио"] = to_doc.FieldValue(value="Иванов Иван Иванович")
    fields["соответчики_фио"] = to_doc.FieldValue(
        value="Иванов Иван Иванович"
    )

    to_doc.fix_derived(fields)

    assert fields["соответчики_фио"].value == ""
    assert fields["соответчики_кол-во"].value == ""


def test_fix_derived_two_co_debtors():
    fields = {col: to_doc.empty() for col in OCR_FIELDS}
    fields["фио"] = to_doc.FieldValue(value="Иванов Иван Иванович")
    fields["соответчики_фио"] = to_doc.FieldValue(
        value="Иванов Иван Иванович; Петров Пётр Петрович; Сидоров Сидор Сидорович"
    )

    to_doc.fix_derived(fields)

    assert fields["соответчики_фио"].value == (
        "Петров Пётр Петрович; Сидоров Сидор Сидорович"
    )
    assert fields["соответчики_кол-во"].value == "2"


def test_fssp_doc():
    from pathlib import Path

    doc = to_doc.fssp_doc(Path("ocr_001.pdf"), "ocr/orders/ocr_001.pdf")

    assert doc.doc_id == "ocr_001"
    assert doc.source_type == "pdf"
    assert doc.table == "xml"
    assert doc.doc_type == "постановление ФССП"
    assert doc.extra["twin"] == "ocr_001.xml"
    assert set(doc.fields) == set(to_doc.XML_FIELDS)


def test_find_pdf_with_quotes(tmp_path):
    pdf = tmp_path / "ocr_007.pdf"
    pdf.touch()

    assert to_doc.find_pdf('"ocr_007.pdf"', tmp_path) == pdf


def test_find_pdf_not_found(tmp_path):
    with pytest.raises(SystemExit):
        to_doc.find_pdf("missing.pdf", tmp_path)


def test_pdf_to_doc_unknown(monkeypatch, tmp_path):
    pdf = tmp_path / "unknown.pdf"
    pdf.touch()

    analysis = SimpleNamespace(
        ocr=[{"recognized_text": "какой-то текст"}],
        classification=SimpleNamespace(
            doc_class=to_doc.DocumentClass.UNKNOWN,
            source_kind=to_doc.SourceKind.SCAN,
        ),
        timings_ms={"ocr": 10, "ner": 5},
        processed=[],
    )

    class FakeService:
        async def analyze(self, *_):
            return analysis

    monkeypatch.setattr(to_doc, "get_service", lambda: FakeService())

    doc = to_doc.pdf_to_doc(pdf, tmp_path)

    assert doc.doc_type == "unknown"
    assert doc.route.review.flags == ["UNCLASSIFIED"]


def test_pdf_to_doc_scan(monkeypatch, tmp_path):
    pdf = tmp_path / "scan.pdf"
    pdf.touch()

    monkeypatch.setattr(to_doc.llm, "enabled", lambda: False)

    analysis = SimpleNamespace(
        ocr=[{"recognized_text": "текст приказа"}],
        classification=SimpleNamespace(
            doc_class=to_doc.DocumentClass.COURT_ORDER,
            source_kind=to_doc.SourceKind.SCAN,
        ),
        timings_ms={"ocr": 10, "ner": 5},
        processed=[SimpleNamespace(
            rule_extraction=SimpleNamespace(
                model_dump=lambda: {"fio": "Иванов Иван Иванович"}
            )
        )],
    )

    class FakeService:
        async def analyze(self, *_):
            return analysis

    monkeypatch.setattr(to_doc, "get_service", lambda: FakeService())

    doc = to_doc.pdf_to_doc(pdf, tmp_path)

    assert doc.doc_type == "приказ"
    assert doc.timings_ms["llm"] == 0


