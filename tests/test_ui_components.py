"""Карточка E: функции UI без streamlit — работают на fixtures без Ollama."""

import json
from pathlib import Path

from src.eval.normalize import KEY_COLUMNS
from src.ui import components as C

FIX = Path("fixtures")


def _doc(name):
    return json.loads((FIX / f"doc_{name}.json").read_text(encoding="utf-8"))


def test_field_rows_mark_key_and_empty():
    rows = {r["поле"]: r for r in C.field_rows(_doc("ocr_014"), KEY_COLUMNS)}
    assert rows["дз_осн"]["_key"] and rows["дз_осн"]["значение"] == "13961.58"
    assert rows["паспорт"]["значение"] == "" and rows["паспорт"]["причина пустого"] == "в документе нет"


def test_table_row_has_template_columns_and_route():
    r = C.table_row(_doc("fssp_001"))
    assert r["FileName"] == "fssp/O_IP_ACT_END_END/fssp_001.xml" and r["route_level"] == "L2"
    assert C.rows_to_csv([r]).startswith("\ufeff".encode("utf-8"))
    assert len(C.rows_to_xlsx([r])) > 1000


def test_llm_ping_offline_is_graceful():
    ok, models, err = C.ping_models("http://127.0.0.1:9/v1", timeout=0.3)
    assert ok is False and models == [] and err


def test_fallback_finds_fixture(tmp_path):
    assert C.fallback_json("ocr_007", tmp_path).name == "doc_ocr_007.json"
    assert C.fallback_json("ocr_999", tmp_path) is None
