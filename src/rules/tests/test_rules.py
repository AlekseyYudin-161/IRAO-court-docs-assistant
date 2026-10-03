"""Движок правил: по тесту на каждый код и флаг на искусственных doc.json + два реальных XML."""

from datetime import date
from pathlib import Path

import pytest

from src.core.contract import FieldValue, load
from src.rules.codes import CODES, LETTER_TEXT
from src.rules.deadlines import add_months, compute, days_left
from src.rules.engine import route_to_lawyer
from src.xmlbranch.to_doc import xml_to_doc

ROOT = Path(__file__).resolve().parents[3]
FIX = ROOT / "fixtures"
FSSP = ROOT / "data" / "courts_anonymized" / "fssp"


def xml_doc(subtype, npa, res="", adj="", rest="1000.00", doc_date="2033-06-10"):
    d = load(FIX / "doc_fssp_001.json")
    d.doc_subtype = subtype
    d.extra = {"npa_articles": npa, "resolution_text": res, "adjudication_text": adj,
               "ip_rest_debtsum": rest, "DocDate": doc_date}
    return d


def clean_order():
    """Эл. приказ ocr_007 с одним должником — чистый документ без кодов."""
    d = load(FIX / "doc_ocr_007.json")
    d.fields["соответчики_кол-во"] = FieldValue(value="1", confidence=1.0, method="gold")
    d.fields["соответчики_фио"] = FieldValue(value=d.fields["фио"].value, confidence=1.0, method="gold")
    return d


def codes(route):
    return route.lawyer.reason_codes


# --- реальные XML (DoD) ---

def test_fssp_001_real_xml():
    r = route_to_lawyer(xml_to_doc(FSSP / "O_IP_ACT_END_END" / "fssp_001.xml", use_llm=False))
    assert (r.lawyer.level, codes(r), r.lawyer.deadline) == ("L2", ["FSSP_END_46_1_4"], "2033-12-10")
    assert "окончить" in r.lawyer.evidence and "NpaArticle 46/1/4" in r.lawyer.evidence
    assert r.lawyer.basis == "п. 4 ч. 1 ст. 46 229-ФЗ"
    assert r.review.flags == []


def test_fssp_012_real_xml():
    r = route_to_lawyer(xml_to_doc(FSSP / "O_IP_ACT_REOPEN_CANCEL" / "fssp_012.xml", use_llm=False))
    assert (r.lawyer.level, codes(r), r.lawyer.deadline) == ("L1", ["FSSP_REFUSAL_31"], "2033-08-05")
    assert "Отказать в возбуждении" in r.lawyer.evidence
    assert r.lawyer.basis == "п. 4 ч. 1 ст. 31 229-ФЗ"


def test_fssp_001_fixture_cli_path():
    r = route_to_lawyer(load(FIX / "doc_fssp_001.json"))
    assert (r.lawyer.level, codes(r), r.lawyer.deadline) == ("L2", ["FSSP_END_46_1_4"], "2033-12-10")


# --- XML-коды ---

def test_end_46_regex_fallback_from_adjudication():
    d = xml_doc("O_IP_ACT_END_END", [], adj="окончено на основании п. 4 ч. 1 ст. 46 Закона")
    r = route_to_lawyer(d)
    assert codes(r) == ["FSSP_END_46_1_4"] and r.lawyer.level == "L2"


def test_end_47_actual_execution_is_l3():
    d = xml_doc("O_IP_ACT_END_END", ["47", "47/1", "47/1/1"], res="1. ИП окончить.", rest="0.00")
    r = route_to_lawyer(d)
    assert (r.lawyer.level, codes(r), r.lawyer.deadline) == ("L3", ["FSSP_END_47_1_1"], None)


def test_return_46_six_months():
    d = xml_doc("O_IP_ACT_RETURN", ["46", "46/1", "46/1/4"], res="3. Возвратить исполнительный документ взыскателю.",
                doc_date="2032-05-17")
    r = route_to_lawyer(d)
    assert (r.lawyer.level, codes(r), r.lawyer.deadline) == ("L2", ["FSSP_RETURN_46_1_4"], "2032-11-17")


def test_stop_43_basis_from_npa():
    d = xml_doc("O_IP_ACT_END_STOP", ["43", "43/2", "43/2/4"], res="1. Исполнительное производство прекратить.",
                adj="В ходе исполнения установлено, что Отмена судебного акта.")
    r = route_to_lawyer(d)
    assert (r.lawyer.level, codes(r)) == ("L2", ["FSSP_STOP_43"])
    assert r.lawyer.basis == "п. 4 ч. 2 ст. 43 229-ФЗ" and "прекратить" in r.lawyer.evidence


def test_refusal_31_ten_days():
    d = xml_doc("O_IP_ACT_REOPEN_CANCEL", ["31", "14"], res="1. Отказать в возбуждении ИП.",
                adj="(п. 8 ч. 1 ст. 31).", doc_date="2033-03-28")
    r = route_to_lawyer(d)
    assert (r.lawyer.level, r.lawyer.deadline, r.lawyer.basis) == ("L1", "2033-04-07", "п. 8 ч. 1 ст. 31 229-ФЗ")


def test_opened_is_l3():
    r = route_to_lawyer(xml_doc("O_IP_RES_REOPEN", ["30"], res="1. Возбудить исполнительное производство."))
    assert (r.lawyer.level, codes(r)) == ("L3", ["FSSP_OPENED"])


# --- PDF-коды ---

def test_clean_order_is_l3_without_codes():
    r = route_to_lawyer(clean_order())
    assert (r.lawyer.level, codes(r), r.review.flags) == ("L3", [], [])


def test_no_debtor_id():
    d = clean_order()
    for c in ("паспорт", "снилс", "инн"):
        d.fields[c] = FieldValue(value="", reason="NOT_IN_TEXT")
    r = route_to_lawyer(d)
    assert (r.lawyer.level, codes(r)) == ("L2", ["NO_DEBTOR_ID"])


def test_multi_debtor():
    r = route_to_lawyer(load(FIX / "doc_ocr_007.json"))       # в эталоне 2 солидарных должника
    assert (r.lawyer.level, codes(r)) == ("L3", ["MULTI_DEBTOR"])


@pytest.mark.parametrize("code, text, level", [
    ("COURT_ORDER_CANCELLED", "О П Р Е Д Е Л И Л: судебный приказ № 2-1/2033 от 01.02.2033 отменить.", "L2"),
    ("CLAIM_DENIED", "Р Е Ш И Л: в удовлетворении исковых требований АО «Тест РТС» отказать.", "L2"),
    ("APPLICATION_RETURNED", "заявление о вынесении судебного приказа АО «Тест РТС» возвратить заявителю.", "L2"),
    ("DEFECTS_TO_FIX", "Исковое заявление оставить без движения до 10.03.2033.", "L1"),
])
def test_text_stub_codes(code, text, level):
    d = clean_order()
    d.extra["text"] = text
    r = route_to_lawyer(d)
    assert codes(r) == [code] and r.lawyer.level == level and r.lawyer.basis == CODES[code].basis


def test_level_is_max_over_codes():
    d = clean_order()
    d.extra["text"] = "оставить без движения; судебный приказ отменить"
    r = route_to_lawyer(d)
    assert r.lawyer.level == "L1" and set(codes(r)) == {"DEFECTS_TO_FIX", "COURT_ORDER_CANCELLED"}


# --- route.review ---

def test_id_conflict_ocr_020():
    r = route_to_lawyer(load(FIX / "doc_ocr_020.json"))
    assert "ID_CONFLICT" in r.review.flags and "ID_CONFLICT" not in codes(r)
    assert "80416142465" in r.review.evidence[r.review.flags.index("ID_CONFLICT")]


def test_required_field_missing():
    d = clean_order()
    d.fields["дело_номер"] = FieldValue(value="", reason="NOT_IN_TEXT")
    r = route_to_lawyer(d)
    assert r.review.flags == ["REQUIRED_FIELD_MISSING"] and "дело_номер" in r.review.evidence[0]


def test_unclassified():
    d = clean_order()
    d.doc_type = "unknown"
    r = route_to_lawyer(d)
    assert r.review.flags == ["UNCLASSIFIED"] and codes(r) == [] and r.lawyer.level == "L3"


def test_unclassified_xml_subtype():
    r = route_to_lawyer(xml_doc("O_IP_SOMETHING_NEW", ["6"]))
    assert r.review.flags == ["UNCLASSIFIED"] and codes(r) == []


def test_low_confidence_and_unvalidated_llm():
    d = clean_order()
    d.fields["дз_пени"] = FieldValue(value="1.00", confidence=0.5, method="regex")
    d.fields["дз_осн"] = FieldValue(value="2.00", confidence=0.9, method="llm")
    r = route_to_lawyer(d)
    assert r.review.flags == ["LOW_CONFIDENCE"]
    assert "дз_пени" in r.review.evidence[0] and "дз_осн" in r.review.evidence[0]
    d.extra["validated"] = ["дз_осн"]
    assert "дз_осн" not in route_to_lawyer(d).review.evidence[0]


def test_arith_check_failed():
    d = xml_doc("O_IP_ACT_END_END", ["46/1/4"])
    d.extra["arith"] = {"ok": False, "sum": "100.00", "expected": "101.00"}
    r = route_to_lawyer(d)
    assert r.review.flags == ["ARITH_CHECK_FAILED"] and codes(r) == ["FSSP_END_46_1_4"]


# --- справочник и сроки ---

def test_every_code_has_letter_text():
    assert set(LETTER_TEXT) == set(CODES) and all(LETTER_TEXT.values())


def test_deadlines():
    assert compute("+6m", date(2033, 6, 10)) == date(2033, 12, 10)
    assert compute("+10d", date(2033, 7, 26)) == date(2033, 8, 5)
    assert add_months(date(2033, 8, 31), 6) == date(2034, 2, 28)
    assert compute(None, date(2033, 1, 1)) is None
    assert days_left("2033-08-05", as_of=date(2033, 8, 1)) == 4


def test_as_of_used_when_no_doc_date():
    d = clean_order()
    d.extra["text"] = "в удовлетворении требований отказать"
    r = route_to_lawyer(d, as_of=date(2033, 1, 31))
    assert r.lawyer.deadline == "2033-02-28"
