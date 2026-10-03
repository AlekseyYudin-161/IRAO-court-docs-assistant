"""Оркестратор: входы → doc.json → маршрут → экспорт → письма. Пока ветки не влиты, читает готовые doc_*.json."""

from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path

from src.acts.to_doc import act_to_doc
from src.core.columns import OCR_COLUMNS, XML_COLUMNS
from src.core.contract import Doc, load

log = logging.getLogger("run")


def collect_docs(docs_dir: Path) -> list[Doc]:
    """Сегодня: готовые doc_*.json + судебные акты (act_to_doc). XML/PDF-ветки подключаются сюда же по готовности."""

    docs = [load(p) for p in sorted(docs_dir.glob("doc_*.json"))]
    for p in sorted(docs_dir.rglob("*.pdf")):
        if "labels" in p.parts:
            continue
        d = act_to_doc(p, data_root=docs_dir)      # None → приказ/ИЛ/ФССП, их возьмёт PDF-ветка middle ml
        if d is not None:
            docs.append(d)
        else:
            log.info("PDF-ветка ещё не подключена, пропускаю %s", p)
    for p in sorted(docs_dir.rglob("*.xml")):
        log.info("XML-ветка ещё не подключена, пропускаю %s", p)
    return docs


def run_one(path: str | Path, no_llm: bool = False) -> Doc:
    """Точка входа для UI (карточка E). no_llm прокидывается в ветки; пока их нет — фиксируется в extra."""

    p = Path(path)
    if p.suffix.lower() == ".json":
        doc = load(p)
    elif p.suffix.lower() == ".pdf" and (doc := act_to_doc(p, data_root=p.parent)) is not None:
        pass
    else:
        raise NotImplementedError("ветки ещё не подключены — в UI используйте UI_FIXTURES=1 и fixtures/doc_*.json")
    doc.extra["no_llm"] = no_llm
    return route(doc)


def route(doc: Doc) -> Doc:
    if doc.table == "acts":                             # акты уже промаршрутизированы в act_to_doc
        return doc
    try:
        from src.rules.engine import (
            route_to_lawyer,  # pylint: disable=import-outside-toplevel
        )
        doc.route = route_to_lawyer(doc)
    except ImportError:
        log.info("src.rules ещё нет — беру route из doc.json")
    return doc


def export_tables(docs: list[Doc], out: Path) -> None:
    """Временный экспорт до src/export (карточка D): те же столбцы, csv UTF-8 BOM, запятая, CRLF."""
    out.mkdir(parents=True, exist_ok=True)
    for table, cols in (("ocr", OCR_COLUMNS), ("xml", XML_COLUMNS)):
        rows = []
        for d in docs:
            if d.table != table:
                continue
            row = {c: d.fields[c].value if c in d.fields else "" for c in cols}
            if table == "ocr":
                row["тип документа"], row["Файл"] = d.doc_type, d.file
            else:
                row["FileName"] = d.file
            rows.append(row)
        with open(out / f"{table}.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, lineterminator="\r\n")
            w.writeheader()
            w.writerows(rows)
    with open(out / "routing.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, lineterminator="\r\n")
        w.writerow(["doc_id", "file", "level", "reason_codes", "basis", "deadline", "evidence", "review_flags"])
        for d in docs:
            L, R = d.route.lawyer, d.route.review
            w.writerow([d.doc_id, d.file, L.level, ";".join(L.reason_codes), L.basis or "", L.deadline or "",
                        L.evidence or "", ";".join(R.flags)])


def write_report(docs: list[Doc], out: Path) -> None:
    lines = ["# Отчёт прогона", "", f"Документов: {len(docs)}", ""]
    for lvl in ("L1", "L2", "L3"):
        lines.append(f"- {lvl}: {sum(d.route.lawyer.level == lvl for d in docs)}")
    lines.append(f"- на ручную проверку: {sum(bool(d.route.review.flags) for d in docs)}")
    lines += ["", "| doc | заполнено | пусто | уровень | флаги |", "|---|---|---|---|---|"]
    for d in docs:
        filled = sum(1 for v in d.fields.values() if v.value)
        lines.append(f"| {d.doc_id} | {filled} | {len(d.fields) - filled} | {d.route.lawyer.level} | {', '.join(d.route.review.flags)} |")
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")


def send_mail(docs: list[Doc], out: Path) -> None:
    """Отправка письма ответственному лицу. Реализует на шаге 6 тимлид"""
    try:
        from src.export.mailer import needs_letter, send_for_doc
    except ImportError:
        log.info("mailer ещё нет — письма пропущены")
        return
    for d in docs:
        if needs_letter(d):
            # d.extra["mail"] = … — чтобы статус отправки попал в реестр BI
            d.extra["mail"] = send_for_doc(d, out / "mail")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", default="fixtures")
    ap.add_argument("--out", default="out/examples")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--holdout", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    out = Path(a.out)
    docs = [route(d) for d in collect_docs(Path(a.docs))]
    export_tables(docs, out)
    write_report(docs, out)
    send_mail(docs, out)
    (out / "run.json").write_text(json.dumps({"docs": len(docs), "no_llm": a.no_llm}, ensure_ascii=False), encoding="utf-8")
    log.info("готово: %s", out)


if __name__ == "__main__":
    main()
