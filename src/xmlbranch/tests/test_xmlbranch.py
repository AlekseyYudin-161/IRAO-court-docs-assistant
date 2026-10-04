"""XML-ветка: сверка с разметкой (DoD карточки C) + юнит-тесты разбора."""

from pathlib import Path

import pytest

from src.xmlbranch import to_doc as to_doc_mod
from src.xmlbranch.address import split_address
from src.xmlbranch.derive import derive_from_text
from src.xmlbranch.doctype import doctype2
from src.xmlbranch.parse import COPY_COLUMNS, npa_articles, parse_xml
from src.xmlbranch.to_doc import xml_to_doc
from src.xmlbranch.to_table import collect, exact_match, print_em, rows, same

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data" / "courts_anonymized"
GOLD = DATA / "labels" / "xml.csv"


@pytest.fixture(scope="module")
def em():
    return exact_match(rows(collect(DATA / "fssp", use_llm=False)), GOLD)


@pytest.mark.parametrize("name", ["O_IP_ACT_END_END/fssp_001", "O_IP_ACT_REOPEN_CANCEL/fssp_012"])
def test_copy_fields_and_doctype2_match_labels(name):
    import csv
    gold = {r["FileName"]: r for r in csv.DictReader(open(GOLD, encoding="utf-8-sig"))}[f"fssp/{name}.xml"]
    d = xml_to_doc(DATA / "fssp" / f"{name}.xml", use_llm=False)
    cols = COPY_COLUMNS + ["DocType2"]
    ok = [c for c in cols if same(c, d.fields[c].value, gold[c])]
    assert len(ok) == 14, set(cols) - set(ok)


def test_per_column_em(em, capsys):
    hits, full, n, diffs = em
    with capsys.disabled():
        print()
        print_em(hits, full, n)
    assert n == 21
    for c in COPY_COLUMNS + ["DocType2", "kv", "dom", "date_end", "rub_peni", "rub_poshlina", "rub_post"]:
        assert hits[c] == 21, (c, [x for x in diffs if x[1] == c])
    for c in ("street", "date_start", "rub_deb"):
        assert hits[c] >= 20, (c, [x for x in diffs if x[1] == c])
    assert full >= 18


def test_contract_evidence_and_reasons():
    for p in sorted((DATA / "fssp").rglob("*.xml")):
        d = xml_to_doc(p, use_llm=False)
        assert d.file == f"fssp/{d.doc_subtype}/{p.name}" and d.table == "xml"
        for c, v in d.fields.items():
            if v.method == "copy" and v.value:
                assert v.evidence == f"xpath:/OIp/{c}" and v.confidence == 1.0
            if v.method == "regex" and v.value:
                assert v.evidence.startswith("IdDebtText[")
            if not v.value:
                assert v.reason


def test_money_kept_as_in_tag_and_raw_text_not_stripped():
    d = xml_to_doc(DATA / "fssp" / "O_IP_ACT_END_END" / "fssp_001.xml", use_llm=False)
    assert d.fields["IdDebtSum"].value == "134288.50"
    tags, _ = parse_xml(DATA / "fssp" / "O_IP_ACT_END_STOP" / "fssp_006.xml")
    assert tags["IdDebtText"] == xml_to_doc(DATA / "fssp" / "O_IP_ACT_END_STOP" / "fssp_006.xml",
                                            use_llm=False).fields["IdDebtText"].value


def test_extra_for_rules():
    d = xml_to_doc(DATA / "fssp" / "O_IP_ACT_END_END" / "fssp_001.xml", use_llm=False)
    x = d.extra
    assert x["npa_articles"] == ["6", "14", "46", "46/1", "46/1/4"]     # без ст. 121/122 из блока предупреждений
    assert x["ip_rest_debtsum"] == "134288.50" and x["dbtr_inn"] == "814083822493"
    assert x["dbtr_snils"] == "82397425841" and x["dbtr_born"] == "2008-04-17"
    assert "окончить" in x["resolution_text"] and x["adjudication_text"]
    assert x["arith"]["ok"] is True


def test_npa_second_namespace():
    _, root = parse_xml(DATA / "fssp" / "O_IP_ACT_RETURN" / "fssp_016.xml")
    arts = npa_articles(root)
    assert "46/1/4" in arts and "47/1/3" in arts


def test_doctype2_unknown_is_empty(caplog):
    assert doctype2("O_IP_ACT_END_END") == "Постановление об окончании ИП"
    assert doctype2("O_IP_NEW") == "" and "O_IP_NEW" in caplog.text


@pytest.mark.parametrize("adr, text, expected", [
    ("643,644086,55,,,Тест,22 Пробная,9,23", "", ("г Тест, ул. 22 Пробная", "9", "23")),
    ("643,644117,55,,Тест,,Примерный,38 Б,71/72", "ул. Примерный пер., д. 38Б", ("г Тест, пер. Примерный", "38/Б", "71/72")),
    ("643,644023,55,,Тест,,Учебный,5А,с13к70-71", "ул. Учебный городок д. 5А", ("г Тест, городок. Учебный", "5/А", "с13к70-71")),
    ("643,644023,55,,Тест,,5 Образцовая,50,138", "", ("г Тест, ул. Образцовая 5-я", "50", "138")),
    ("643,644117,55,,Тест,,4-я Условная,62к1,с5к107", "", ("г Тест, ул. Условная 4-я", "62 корп.1", "с5к107")),
    ("Эталонная ул., д. 9, кв.121, г. Тест, 644110", "", ("г Тест, ул. Эталонная", "9", "121")),
    ("644050, Россия, Пробная обл., , г. Тест, , Тест пр-кт, д. 38, корп. г, кв. 77", "", ("г Тест, пр-кт Тест", "38/г", "77")),
    ("644086, Россия, , , г. Тест, , ул. Учебный Путь, д. 20, корп. 1, кв. 26", "", ("г Тест, ул. Учебный Путь", "20 корп.1", "26")),
])
def test_split_address(adr, text, expected):
    a = split_address(adr, text)
    assert (a.street, a.dom, a.kv) == expected


def test_unstructured_address_is_llm_candidate(tmp_path):
    a = split_address("где-то за рекой у старой мельницы")
    assert not a.structured


def test_derive_period_and_money():
    text = ("задолженность за период с 03.07.2030 г. по 03.04.2033 г. в размере 234156,36 руб., пени в размере _, "
            "расходы по уплате государственной пошлины в размере 0 (ноль рублей), почтовые расходы в размере 729,60 руб.")
    d, fb = derive_from_text(text)
    assert d["date_start"].value == "2030-07-03" and d["date_end"].value == "2033-04-03"
    assert d["rub_deb"].value == "234156.36" and d["rub_post"].value == "729.60"
    assert d["rub_peni"].value == "" and d["rub_poshlina"].value == ""     # «_» и «0 (ноль)» — заглушки бланка
    assert fb == []


def test_fallback_triggers():
    long_no_debt = "Взыскать с должника " + "x" * 250
    d, fb = derive_from_text(long_no_debt, id_debt_sum="100.00")
    assert "rub_deb" in fb and d["rub_deb"].value == "100.00" and d["rub_deb"].confidence < 0.7
    d, fb = derive_from_text("за период с 01.11.20217 по 13.04.2027 в размере 1 руб.")
    assert "date_start" in fb and d["date_end"].value == "2027-04-13"
    _, fb = derive_from_text("Взыскать … задолженность в размере 1 руб. Взыскать … задолженность в размере 2 руб.")
    assert set(fb) >= {"rub_deb", "date_start"}


def test_fssp_013_is_llm_candidate_and_rules_kept():
    d = xml_to_doc(DATA / "fssp" / "O_IP_ACT_REOPEN_CANCEL" / "fssp_013.xml", use_llm=False)
    assert d.fields["rub_deb"].value == "98756.44" and d.fields["rub_deb"].reason == "LLM_FALLBACK_CANDIDATE"
    assert d.fields["date_start"].value == "" and d.fields["date_start"].reason == "LLM_FALLBACK_CANDIDATE"


def test_llm_fills_only_empty_with_quote(monkeypatch):
    from src.llm import client
    monkeypatch.setattr(client, "enabled", lambda: True)
    calls = []

    def fake_extract(text, schema, prompt):
        calls.append(sorted(schema["properties"]))
        return {"date_start": {"value": "05.03.2025", "quote": "с 05.03.2025 по 13.04.2027"}}

    monkeypatch.setattr(client, "extract", fake_extract)
    d = to_doc_mod.xml_to_doc(DATA / "fssp" / "O_IP_ACT_REOPEN_CANCEL" / "fssp_013.xml")
    assert calls == [["date_start", "rub_post"]]                       # только пустые кандидаты
    assert d.fields["date_start"].value == "2025-03-05" and d.fields["date_start"].method == "llm"
    assert d.fields["rub_deb"].method == "regex"                       # значение правил не затёрто
    assert d.extra["validated"] == ["date_start"]


def test_no_llm_means_no_call(monkeypatch):
    from src.llm import client
    monkeypatch.setattr(client, "extract", lambda *a, **k: pytest.fail("LLM вызвана при use_llm=False"))
    xml_to_doc(DATA / "fssp" / "O_IP_ACT_REOPEN_CANCEL" / "fssp_013.xml", use_llm=False)
