"""CLI: все XML из каталога → таблица по xml_template.csv (+ per-column EM, если рядом есть разметка).

    python -m src.xmlbranch.to_table data -o work/xml.csv [--no-llm] [--gold path/to/labels/xml.csv]

Запись csv здесь временная (UTF-8 BOM, запятая, CRLF — как run_examples.export_tables); итоговый экспорт —
src/export (BI/DA), ему отдаём doc.json / строки. EM — только для локальной сверки, скорер живёт в src/eval.
"""

from __future__ import annotations

import argparse
import csv
import logging
from decimal import Decimal, InvalidOperation
from pathlib import Path

from src.core.columns import XML_COLUMNS
from src.core.contract import Doc
from src.xmlbranch.to_doc import xml_to_doc

MONEY_COLS = {"IdDebtSum", "rub_deb", "rub_peni", "rub_poshlina", "rub_post"}


def collect(root: Path, use_llm: bool | None = None) -> list[Doc]:
    return [xml_to_doc(p, use_llm=use_llm) for p in sorted(root.rglob("*.xml"))]


def rows(docs: list[Doc]) -> list[dict[str, str]]:
    return [{"FileName": d.file, **{c: d.fields[c].value for c in XML_COLUMNS if c != "FileName"}} for d in docs]


def write_csv(table: list[dict[str, str]], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=XML_COLUMNS, lineterminator="\r\n")
        w.writeheader()
        w.writerows(table)


def same(col: str, a: str, b: str) -> bool:
    """Сравнение с разметкой: деньги — через Decimal ('134288.50' == '134288.5'), остальное — строго."""
    if col in MONEY_COLS and a and b:
        try:
            return Decimal(a) == Decimal(b)
        except InvalidOperation:
            return a == b
    return a == b


def exact_match(pred: list[dict[str, str]], gold_path: Path) -> tuple[dict[str, int], int, int, list[tuple[str, str, str, str]]]:
    """(совпадений по столбцу, строк целиком, строк в разметке, расхождения [(файл, столбец, наше, эталон)])."""
    with open(gold_path, encoding="utf-8-sig", newline="") as f:
        gold = {r["FileName"]: r for r in csv.DictReader(f)}
    by_file = {r["FileName"]: r for r in pred}
    cols = [c for c in XML_COLUMNS if c != "FileName"]
    hits = dict.fromkeys(cols, 0)
    full, diffs = 0, []
    for name, g in gold.items():
        p = by_file.get(name, {})
        ok = True
        for c in cols:
            if same(c, p.get(c, ""), g[c]):
                hits[c] += 1
            else:
                ok = False
                diffs.append((name, c, p.get(c, ""), g[c]))
        full += ok
    return hits, full, len(gold), diffs


def print_em(hits: dict[str, int], full: int, n: int) -> None:
    print(f"{'столбец':<14} EM")
    for c, k in hits.items():
        print(f"{c:<14} {k}/{n}")
    print(f"{'строк целиком':<14} {full}/{n}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", type=Path, help="каталог, где искать *.xml (рекурсивно)")
    ap.add_argument("-o", "--out", type=Path, default=Path("out/xml.csv"))
    ap.add_argument("--gold", type=Path, help="labels/xml.csv; по умолчанию ищется внутри root")
    ap.add_argument("--no-llm", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    table = rows(collect(a.root, use_llm=False if a.no_llm else None))
    write_csv(table, a.out)
    print(f"{len(table)} строк → {a.out}")
    gold = a.gold or next(iter(sorted(a.root.rglob("labels/xml.csv"))), None)
    if gold:
        hits, full, n, _ = exact_match(table, gold)
        print_em(hits, full, n)


if __name__ == "__main__":
    main()
