"""Карточка D: нормализатор, скорер, срезы, отчёт."""

import csv
from pathlib import Path

import pytest

from src.eval.normalize import equal, normalize
from src.eval.score import score
from src.eval.splits import filter_paths, load_holdout, slice_of

LABELS = Path("data/courts_anonymized/labels")
need_labels = pytest.mark.skipif(not (LABELS / "ocr.csv").exists(), reason="нет data/courts_anonymized/labels")


@pytest.mark.parametrize("a,b", [("4000", "4000.0"), ("4 000,00 руб.", "4000.0"), ("134288.50", "134288.5"),
                                 ("1\u00a0234,5", "1234.50")])
def test_money_equal(a, b):
    assert equal("дз_пошлина", a, b)


def test_empty_vs_zero():
    assert equal("дз_пени", "", "")
    assert not equal("дз_пени", "0", "")
    assert not equal("дз_пени", "", "0.00")


@pytest.mark.parametrize("a", ["11 ноября 2025 г.", "11.11.2025", "2025-11-11", "«11» ноября 2025 года"])
def test_dates(a):
    assert normalize("дело_дата", a) == "2025-11-11"


def test_may_and_march():
    assert normalize("DocDate", "3 мая 2033 г.") == "2033-05-03"
    assert normalize("DocDate", "3 марта 2033 г.") == "2033-03-03"


def test_ids_and_text():
    assert equal("инн", " 012345678901 ", "012345678901")       # ведущий ноль сохранён
    assert equal("IpNo", "835049/33/55003-ИП", "835049/33/55003-ИП")
    assert not equal("IpNo", "835049/33/55003-ИП.", "835049/33/55003-ИП")
    assert equal("IpNo", "835049/33/55003-ИП.", "835049/33/55003-ИП", loose=True)
    assert equal("фио", "Пробов  Назар Назарович", "пробов назар назарович")


def test_loose_address_and_names():
    assert not equal("street", "г Тест, ул. 22 Пробная", "г. Тест, Пробная 22-я ул.")
    assert equal("street", "г Тест, ул. 22 Пробная", "г. Тест, Пробная 22-я ул.", loose=True)
    assert equal("street", "г Тест, ул. Образцовая 5-я", "г. Тест, 5 Образцовая ул.", loose=True)
    assert equal("соответчики_фио", "Иванова Ивана, Петрова Петра", "Петрова Петра, Иванова Ивана")
    assert equal("фио", "Иванова Ивана Петровича", "Иванов Иван Петрович", loose=True)


def test_slices():
    assert slice_of("fssp/O_IP_ACT_END_END/fssp_001.xml") == "XML ФССП"
    assert slice_of("ocr/orders_scan/ocr_002.pdf") == "PDF сканы"
    assert slice_of("ocr/writs_electronic/ocr_020.pdf") == "PDF электронные"


def test_holdout_fixed():
    h = load_holdout()
    assert len(h) == 13 and "ocr_004" in h and "fssp_020" in h
    assert [p.name for p in filter_paths(["a/ocr_004.pdf", "a/ocr_007.pdf"], holdout=True)] == ["ocr_004.pdf"]
    assert len(filter_paths(["a/ocr_004.pdf", "a/ocr_007.pdf"], holdout=False)) == 2


@need_labels
def test_labels_vs_labels_is_100():
    res = score(LABELS, LABELS)
    for name, m in res["slices"].items():
        if m["docs_scored"]:
            assert m["cells_strict"] == 1.0 and m["docs_all_ok_strict"] == 1.0, name
    assert res["slices"]["dev-set"]["docs_scored"] == 31
    assert res["slices"]["holdout-set"]["docs_scored"] == 13


def _write(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\r\n")
        w.writeheader()
        w.writerows(rows)


@need_labels
def test_errors_are_counted(tmp_path):
    with open(LABELS / "xml.csv", encoding="utf-8-sig", newline="") as f:
        gold = list(csv.DictReader(f))
    pred = [dict(r) for r in gold[:3]]
    pred[0]["IdDebtSum"] = "134 288,50 руб."          # тот же смысл — засчитывается
    pred[1]["rub_peni"] = ""                           # не извлечено
    pred[2]["DbtrName"] = "Кто-то Другой"              # неверно
    _write(tmp_path / "xml.csv", pred)
    res = score(tmp_path, LABELS)
    m = res["slices"]["XML ФССП"]
    assert m["docs_scored"] == 3 and m["coverage"] == round(3 / 21, 4)
    assert m["miss"] == 1 and m["wrong"] == 1
    assert m["docs_all_ok_strict"] == round(1 / 3, 4)
    res2 = score(tmp_path, LABELS, missing_as_error=True)
    assert res2["slices"]["XML ФССП"]["docs_scored"] == 21


@need_labels
def test_report_writes_files(tmp_path):
    from src.eval.report import build_markdown, write_diff_xlsx
    from src.eval.score import read_gold, read_pred
    with open(LABELS / "ocr.csv", encoding="utf-8-sig", newline="") as f:
        gold = list(csv.DictReader(f))
    pred = [dict(r) for r in gold[:2]]
    pred[0]["дз_осн"] = "1.00"
    _write(tmp_path / "ocr.csv", pred)
    res = score(tmp_path, LABELS)
    md = build_markdown(res, {}, {}, tmp_path)
    assert "ocr_001" in md and "дз_осн" in md
    write_diff_xlsx(res, read_pred(tmp_path), read_gold(LABELS), tmp_path / "diff.xlsx")
    assert (tmp_path / "diff.xlsx").stat().st_size > 0
