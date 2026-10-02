"""Списки столбцов выходных таблиц — читаются из data/templates/, не редактировать руками."""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "data" / "courts_anonymized" / "templates"


def _header(name: str) -> list[str]:
    # utf-8-sig: шаблоны начинаются с BOM, иначе первый столбец будет "_тип документа"
    with open(TEMPLATES / name, encoding="utf-8-sig", newline="") as f:
        return next(csv.reader(f))


OCR_COLUMNS: list[str] = _header("ocr_template.csv")   # 22
XML_COLUMNS: list[str] = _header("xml_template.csv")   # 24

# Поля, которые обязаны заполнить ветки в doc.json (без служебных, их ставит экспорт)
OCR_FIELDS: list[str] = [c for c in OCR_COLUMNS if c not in ("тип документа", "Файл")]  # 20
XML_FIELDS: list[str] = [c for c in XML_COLUMNS if c != "FileName"]                     # 23

CLASS_TO_FOLDER = {
    "приказ": "orders_scan",
    "приказ эл": "orders_electronic",
    "ИЛ": "writs_scan",
    "ИЛ эл": "writs_electronic",
}

FOLDER_TO_CLASS = {v: k for k, v in CLASS_TO_FOLDER.items()}

# Судебные акты (data/acts/): в шаблоны таблиц не входят, нужны для реестра и письма
ACT_FIELDS: list[str] = ["суд", "вид_акта", "дело_номер", "дело_дата"]
