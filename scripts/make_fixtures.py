"""Фикстуры doc_*.json из строк разметки организаторов (method=gold).
Запуск из корня репо: python scripts/make_fixtures.py"""


import csv
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # чтобы работал import src.* при запуске как скрипта

from src.core.columns import OCR_FIELDS, XML_FIELDS
from src.core.contract import Doc, FieldValue, LawyerRoute, ReviewRoute, Route, dump

ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / "data" / "courts_anonymized" / "labels"
OUT = ROOT / "fixtures"

MONEY = {
    "IdDebtSum", "rub_deb", "rub_peni", "rub_poshlina", "rub_post", "дз_осн", "дз_пени", "дз_пошлина"
    }

def _rows(name: str, key: str) -> dict[str, dict[str, str]]:
    with open(LABELS / name, encoding="utf-8-sig", newline="") as f:
        return {Path(r[key]).stem: r for r in csv.DictReader(f)}
    

def _money(v: str) -> str:
    """'134288.5' / '4000,00' -> '134288.50' / '4000.00'; нечисловое оставляем как есть."""
    try:
        return str(Decimal(v.replace(",", ".").replace(" ", "")).quantize(Decimal("0.01")))
    except InvalidOperation:
        return v

def _fields(row: dict[str, str], cols: list[str], src: str) -> dict[str, FieldValue]:    
    out = {}
    for c in cols:
        v = (row.get(c) or "").strip()
        if v and c in MONEY:
            v = _money(v)
        if v:
            out[c] = FieldValue(value=v, evidence=f"fixture:{src}", confidence=1.0, method="gold")
        else:
            out[c] = FieldValue(value="", confidence=0.0, method="gold", reason="NOT_IN_TEXT")
    return out


def main() -> None:
    xml = _rows("xml.csv", "FileName")
    ocr = _rows("ocr.csv", "Файл")

    r = xml["fssp_001"]
    d1 = Doc(doc_id="fssp_001", source_type="xml", file=r["FileName"], table="xml",
            doc_type="постановление ФССП", doc_subtype=r["DocType"],
            fields=_fields(r, XML_FIELDS, "labels/xml.csv"),
            extra={"npa_articles": ["46/1/4", "6", "14"], "DocDate": r["DocDate"]},
            route=Route(lawyer=LawyerRoute(
                level="L2", reason_codes=["FSSP_END_46_1_4"], basis="п. 4 ч. 1 ст. 46 229-ФЗ",
                deadline="2033-12-10",
                evidence="ResolutionText: «1. Исполнительное производство № 835049/33/55003-ИП окончить.»; NpaArticle 46/1/4"),
                review=ReviewRoute()))
    d1.fields["IdDebtSum"].evidence = "xpath:/OIp/IdDebtSum"
    d1.fields["IdDebtSum"].method = "copy"

    r = ocr["ocr_007"]
    d2 = Doc(doc_id="ocr_007", source_type="pdf", file=r["Файл"], table="ocr", doc_type=r["тип документа"],
            fields=_fields(r, OCR_FIELDS, "labels/ocr.csv"),
            route=Route(lawyer=LawyerRoute(level="L3", reason_codes=[]), review=ReviewRoute()))

    r = ocr["ocr_014"]
    d3 = Doc(doc_id="ocr_014", source_type="pdf", file=r["Файл"], table="ocr", doc_type=r["тип документа"],
            fields=_fields(r, OCR_FIELDS, "labels/ocr.csv"),
            route=Route(lawyer=LawyerRoute(level="L3", reason_codes=[]), review=ReviewRoute()))

    # ocr_020: ИНН в карточке должника (эталон) ≠ ИНН в цитате судебного акта — README оргов, раздел про противоречия
    r = ocr["ocr_020"]
    d4 = Doc(doc_id="ocr_020", source_type="pdf", file=r["Файл"], table="ocr", doc_type=r["тип документа"],
            fields=_fields(r, OCR_FIELDS, "labels/ocr.csv"),
            extra={"conflicts": [{"field": "инн", "values": [r["инн"], "80416142465"],
                                  "evidence": ["карточка должника", "цитата судебного акта"]}]},
            route=Route(lawyer=LawyerRoute(level="L3", reason_codes=[]),
                        review=ReviewRoute(flags=["ID_CONFLICT"], evidence=["инн: 862152469440 ≠ 80416142465"])))

    for d in (d1, d2, d3, d4):
        dump(d, OUT / f"doc_{d.doc_id}.json")
        print("ok", d.doc_id, sum(1 for v in d.fields.values() if v.value))


if __name__ == "__main__":
    main()