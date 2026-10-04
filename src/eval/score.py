"""Сверка out/ocr.csv, out/xml.csv (или папки doc_*.json) с разметкой оргов.

    python -m src.eval.score --pred out --gold data/courts_anonymized/labels
    python -m src.eval.score --pred out/examples --gold data/courts_anonymized/labels --split dev

Выход: таблица в консоль, <pred>/metrics.json, <pred>/metrics.md, строка-на-срез в <pred>/metrics_history.csv.
Сравнение — точное совпадение после нормализации (src/eval/normalize.py), strict и loose.
Строки сопоставляются по stem файла (ocr_007, fssp_001), а не по полному пути.
По умолчанию метрики считаются по документам, которые есть в предсказании; доля покрытых
документов — отдельный столбец «покрытие». С --missing-as-error отсутствующий документ = все поля мимо.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from datetime import datetime
from pathlib import Path

from src.eval.normalize import KEY_FIELDS, KEY_GROUPS, OUT_OF_MACRO, normalize
from src.eval.splits import HOLDOUT_FILE, SLICES, load_holdout, slice_of, stem

TABLES = ("ocr", "xml")
FILE_COL = {"ocr": "Файл", "xml": "FileName"}


# ---------------------------------------------------------------- чтение
def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _rows_from_doc_json(paths: list[Path]) -> dict[str, list[dict]]:
    """Папка с doc_*.json (приёмочный тест PDF-ветки) → строки таблиц, без зависимости от contract.py."""
    out: dict[str, list[dict]] = {t: [] for t in TABLES}
    for p in paths:
        d = json.loads(p.read_text(encoding="utf-8"))
        t = d.get("table")
        if t not in out:
            continue                                     # акты в таблицы не входят
        row = {c: (fv or {}).get("value", "") for c, fv in d.get("fields", {}).items()}
        row[FILE_COL[t]] = d.get("file", "")
        if t == "ocr":
            row["тип документа"] = d.get("doc_type", "")
        out[t].append(row)
    return out


def read_pred(pred: Path) -> dict[str, list[dict]]:
    if pred.is_file():
        t = "xml" if "xml" in pred.stem else "ocr"
        return {t: read_csv(pred), ("ocr" if t == "xml" else "xml"): []}
    rows = {t: read_csv(pred / f"{t}.csv") if (pred / f"{t}.csv").exists() else [] for t in TABLES}
    if not any(rows.values()):
        rows = _rows_from_doc_json(sorted(pred.rglob("doc_*.json")))
    return rows


def read_gold(gold: Path) -> dict[str, list[dict]]:
    if gold.is_file():
        t = "xml" if "xml" in gold.stem else "ocr"
        return {t: read_csv(gold), ("ocr" if t == "xml" else "xml"): []}
    return {t: read_csv(gold / f"{t}.csv") if (gold / f"{t}.csv").exists() else [] for t in TABLES}


def read_timings(pred: Path) -> dict[str, float]:
    """stem → total ms из doc_*.json (timings_ms.total), если ветки их пишут."""
    res = {}
    base = pred if pred.is_dir() else pred.parent
    for p in base.rglob("doc_*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            ms = (d.get("timings_ms") or {}).get("total")
            if ms is not None:
                res[stem(d.get("file") or d.get("doc_id", p.stem))] = float(ms)
        except (ValueError, OSError):
            continue
    return res


# ---------------------------------------------------------------- сравнение
def compare(pred_rows: dict, gold_rows: dict, missing_as_error: bool = False) -> list[dict]:
    """Одна запись на (документ, столбец): stem, table, slice, column, gold, pred, ok_strict, ok_loose, outcome."""
    cells = []
    for t in TABLES:
        fcol = FILE_COL[t]
        pred_by = {stem(r.get(fcol, "")): r for r in pred_rows.get(t, [])}
        for g in gold_rows.get(t, []):
            s = stem(g[fcol])
            p = pred_by.get(s)
            if p is None and not missing_as_error:
                continue
            for col, gv in g.items():
                if col in KEY_FIELDS:
                    continue
                pv = "" if p is None else (p.get(col) or "")
                ns, nl = normalize(col, pv), normalize(col, gv)
                ok_s = ns == normalize(col, gv)
                ok_l = normalize(col, pv, loose=True) == normalize(col, gv, loose=True)
                if ok_s:
                    outcome = "ok"
                elif not ns:
                    outcome = "miss"          # не извлекли
                elif not nl:
                    outcome = "fp"            # извлекли там, где в разметке пусто
                else:
                    outcome = "wrong"
                cells.append({"stem": s, "table": t, "slice": slice_of(g[fcol]), "column": col,
                              "file": g[fcol], "gold": gv, "pred": pv, "present": p is not None,
                              "ok_strict": ok_s, "ok_loose": ok_l, "outcome": outcome})
    return cells


def _share(xs) -> float | None:
    xs = list(xs)
    return round(sum(xs) / len(xs), 4) if xs else None


def aggregate(cells: list[dict], gold_stems: set[str], timings: dict[str, float]) -> dict:
    docs = sorted({c["stem"] for c in cells})
    present = {c["stem"] for c in cells if c["present"]}
    macro_cells = [c for c in cells if c["column"] not in OUT_OF_MACRO]
    cols = sorted({c["column"] for c in macro_cells})

    def macro(key):
        per = [_share(c[key] for c in macro_cells if c["column"] == col) for col in cols]
        per = [x for x in per if x is not None]
        return round(sum(per) / len(per), 4) if per else None

    def doc_ok(key):
        return _share(all(c[key] for c in macro_cells if c["stem"] == d) for d in docs)

    key_cells = [c for c in cells if any(c["column"] in g for g in KEY_GROUPS.values())]
    ms = [timings[d] for d in docs if d in timings]
    return {
        "docs_gold": len(gold_stems),
        "docs_scored": len(docs),
        "coverage": round(len(present) / len(gold_stems), 4) if gold_stems else None,
        "cells_strict": _share(c["ok_strict"] for c in cells),
        "cells_loose": _share(c["ok_loose"] for c in cells),
        "macro_strict": macro("ok_strict"),
        "macro_loose": macro("ok_loose"),
        "docs_all_ok_strict": doc_ok("ok_strict"),
        "docs_all_ok_loose": doc_ok("ok_loose"),
        "key_strict": _share(c["ok_strict"] for c in key_cells),
        "key_loose": _share(c["ok_loose"] for c in key_cells),
        "key_groups": {g: _share(c["ok_strict"] for c in key_cells if c["column"] in cs)
                       for g, cs in KEY_GROUPS.items()},
        "miss": sum(c["outcome"] == "miss" for c in cells),
        "fp": sum(c["outcome"] == "fp" for c in cells),
        "wrong": sum(c["outcome"] == "wrong" for c in cells),
        "ms_per_doc": round(sum(ms) / len(ms)) if ms else None,
    }


def per_column(cells: list[dict]) -> list[dict]:
    rows = []
    for t in TABLES:
        for col in dict.fromkeys(c["column"] for c in cells if c["table"] == t):
            cs = [c for c in cells if c["table"] == t and c["column"] == col]
            rows.append({"table": t, "column": col, "n": len(cs),
                         "strict": _share(c["ok_strict"] for c in cs), "loose": _share(c["ok_loose"] for c in cs),
                         "miss": sum(c["outcome"] == "miss" for c in cs), "fp": sum(c["outcome"] == "fp" for c in cs),
                         "wrong": sum(c["outcome"] == "wrong" for c in cs),
                         "key": any(col in g for g in KEY_GROUPS.values()), "macro": col not in OUT_OF_MACRO})
    return rows


def score(pred: Path, gold: Path, split: str = "all", missing_as_error: bool = False,
          holdout_file: Path = HOLDOUT_FILE) -> dict:
    pred_rows, gold_rows = read_pred(pred), read_gold(gold)
    holdout = load_holdout(holdout_file)
    if split != "all":
        for t in TABLES:
            gold_rows[t] = [r for r in gold_rows[t] if (stem(r[FILE_COL[t]]) in holdout) == (split == "holdout")]
    cells = compare(pred_rows, gold_rows, missing_as_error)
    timings = read_timings(pred)
    gold_all = {t: [r for r in gold_rows[t]] for t in TABLES}
    gold_files = {stem(r[FILE_COL[t]]): r[FILE_COL[t]] for t in TABLES for r in gold_all[t]}

    def sub(pred_fn, stem_fn):
        cs = [c for c in cells if pred_fn(c)]
        gs = {s for s, f in gold_files.items() if stem_fn(s, f)}
        return aggregate(cs, gs, timings)

    slices = {"все": sub(lambda c: True, lambda s, f: True)}
    for name in SLICES:
        slices[name] = sub(lambda c, n=name: c["slice"] == n, lambda s, f, n=name: slice_of(f) == n)
    if split == "all":
        slices["dev-set"] = sub(lambda c: c["stem"] not in holdout, lambda s, f: s not in holdout)
        slices["holdout-set"] = sub(lambda c: c["stem"] in holdout, lambda s, f: s in holdout)
    return {"pred": str(pred), "gold": str(gold), "split": split, "missing_as_error": missing_as_error,
            "slices": slices, "per_column": per_column(cells), "cells": cells}


# ---------------------------------------------------------------- вывод
def _pct(x) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


SUMMARY_COLS = [("срез", None), ("док.", "docs_scored"), ("покрытие", "coverage"),
                ("ячейки strict", "cells_strict"), ("ячейки loose", "cells_loose"),
                ("macro strict", "macro_strict"), ("KEY strict", "key_strict"), ("KEY loose", "key_loose"),
                ("док. без ошибок", "docs_all_ok_strict"), ("мимо/лишнее/неверно", None), ("мс/док", "ms_per_doc")]


def summary_rows(res: dict) -> list[list[str]]:
    rows = []
    for name, m in res["slices"].items():
        if not m["docs_scored"] and not m["docs_gold"]:
            continue
        rows.append([name, str(m["docs_scored"]), _pct(m["coverage"]), _pct(m["cells_strict"]),
                     _pct(m["cells_loose"]), _pct(m["macro_strict"]), _pct(m["key_strict"]), _pct(m["key_loose"]),
                     _pct(m["docs_all_ok_strict"]), f'{m["miss"]}/{m["fp"]}/{m["wrong"]}',
                     "—" if m["ms_per_doc"] is None else str(m["ms_per_doc"])])
    return rows


def to_markdown(res: dict) -> str:
    head = [h for h, _ in SUMMARY_COLS]
    L = ["# Метрики извлечения", "",
         f"Предсказание: `{res['pred']}` · разметка: `{res['gold']}` · набор: {res['split']} · "
         f"{datetime.now():%Y-%m-%d %H:%M}", "",
         "Точное совпадение после нормализации (деньги — 2 знака, даты — ГГГГ-ММ-ДД, пусто == пусто, 0 ≠ пусто). "
         "**strict** — регистр/ё/пробелы; **loose** — дополнительно формат адреса и падеж ФИО. "
         "**KEY** — суммы, даты, ФИО, номера дел/ИП (по ним орги проверяют закрытую выборку).", "",
         "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    L += ["| " + " | ".join(r) + " |" for r in summary_rows(res)]
    L += ["", "## KEY по группам", "", "| срез | " + " | ".join(KEY_GROUPS) + " |", "|---|" + "---|" * len(KEY_GROUPS)]
    for name, m in res["slices"].items():
        if m["docs_scored"]:
            L.append(f"| {name} | " + " | ".join(_pct(m["key_groups"][g]) for g in KEY_GROUPS) + " |")
    L += ["", "## По столбцам", "", "| таблица | столбец | n | strict | loose | мимо | лишнее | неверно |",
          "|---|---|---|---|---|---|---|---|"]
    for r in per_column(res["cells"]):
        name = f"**{r['column']}**" if r["key"] else r["column"]
        name += "" if r["macro"] else " (вне macro)"
        L.append(f"| {r['table']} | {name} | {r['n']} | {_pct(r['strict'])} | {_pct(r['loose'])} | "
                 f"{r['miss']} | {r['fp']} | {r['wrong']} |")
    L += ["", "Жирным — ключевые реквизиты. «мимо» — поле пустое, в разметке есть; «лишнее» — заполнено, "
          "в разметке пусто; «неверно» — оба заполнены и не совпали."]
    return "\n".join(L) + "\n"


def print_table(res: dict) -> None:
    head = [h for h, _ in SUMMARY_COLS]
    rows = summary_rows(res)
    w = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(head)] if rows else [len(h) for h in head]
    print("  ".join(h.ljust(w[i]) for i, h in enumerate(head)))
    print("  ".join("-" * x for x in w))
    for r in rows:
        print("  ".join(v.ljust(w[i]) for i, v in enumerate(r)))


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              timeout=5).stdout.strip() or "—"
    except (OSError, subprocess.SubprocessError):
        return "—"


HISTORY_COLS = ["run_at", "commit", "split", "slice", "docs", "coverage", "cells_strict", "macro_strict",
                "key_strict", "key_loose", "docs_all_ok", "ms_per_doc", "llm_mode", "pred"]


def append_history(res: dict, path: Path) -> None:
    run_info = {}
    base = Path(res["pred"]) if Path(res["pred"]).is_dir() else Path(res["pred"]).parent
    if (base / "run.json").exists():
        run_info = json.loads((base / "run.json").read_text(encoding="utf-8"))
    llm_mode = "no-llm" if run_info.get("no_llm") else ("llm" if run_info else "—")
    new = not path.exists()
    with open(path, "a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\r\n")
        if new:
            w.writerow(HISTORY_COLS)
        now, commit = datetime.now().isoformat(timespec="seconds"), _git_commit()
        for name, m in res["slices"].items():
            if m["docs_scored"]:
                w.writerow([now, commit, res["split"], name, m["docs_scored"], m["coverage"], m["cells_strict"],
                            m["macro_strict"], m["key_strict"], m["key_loose"], m["docs_all_ok_strict"],
                            m["ms_per_doc"] or "", llm_mode, res["pred"]])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pred", default="out", help="папка с ocr.csv/xml.csv (или doc_*.json), либо один csv")
    ap.add_argument("--gold", default="data/courts_anonymized/labels")
    ap.add_argument("--split", choices=["all", "dev", "holdout"], default="all")
    ap.add_argument("--missing-as-error", action="store_true", help="документ без строки в предсказании = все поля мимо")
    ap.add_argument("--holdout-file", default=str(HOLDOUT_FILE))
    ap.add_argument("--out", default=None, help="куда писать metrics.*; по умолчанию — папка --pred")
    ap.add_argument("--no-history", action="store_true")
    a = ap.parse_args()

    pred = Path(a.pred)
    res = score(pred, Path(a.gold), a.split, a.missing_as_error, Path(a.holdout_file))
    out = Path(a.out) if a.out else (pred if pred.is_dir() else pred.parent)
    out.mkdir(parents=True, exist_ok=True)
    print_table(res)
    (out / "metrics.json").write_text(json.dumps({k: v for k, v in res.items() if k != "cells"} | {
        "per_column": res["per_column"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "metrics.md").write_text(to_markdown(res), encoding="utf-8")
    if not a.no_history:
        append_history(res, out / "metrics_history.csv")
    print(f"\n→ {out / 'metrics.md'}, {out / 'metrics.json'}")


if __name__ == "__main__":
    main()
