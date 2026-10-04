"""Реестр обработанных документов out/registry.csv — «что пришло, куда направлено, ушло ли письмо».

Ключ строки — sha256(файл) + дата документа (так предложили орги на Q&A 01.10).
Повторный прогон того же файла обновляет строку, а не дублирует её.
Статус письма — из doc.extra["mail"] = {"eml", "sent", "to", "error"} (его кладёт run_examples.send_mail).

Подключение в run_examples.main() после send_mail(docs, out):
    from src.export.registry import update_registry
    update_registry(docs, out)

Модуль не импортирует contract.py: работает и с pydantic-Doc, и с dict из doc_*.json.
"""

from __future__ import annotations

import csv
import hashlib
import os
from datetime import datetime
from pathlib import Path

COLUMNS = ["sha256", "doc_id", "file", "doc_type", "doc_date", "route_level", "route_codes", "review_flags",
           "mail_eml", "mail_sent", "mail_to", "mail_error", "processed_at"]

DATA_ROOTS = [os.getenv("DATA_ROOT", "data/courts_anonymized"), "data/courts_anonymized", "data/acts", "data", "."]
DATE_FIELDS = ("DocDate", "дело_дата")


def _get(obj, key, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def resolve_path(doc, roots=None) -> Path | None:
    """doc.file — путь относительно корня набора; ищем файл в известных корнях."""
    extra = _get(doc, "extra") or {}
    cands = [extra.get("path"), extra.get("source_path")]
    f = _get(doc, "file") or ""
    cands += [Path(r) / f for r in (roots or DATA_ROOTS)]
    for c in cands:
        if c and Path(c).is_file():
            return Path(c)
    return None


def file_sha256(doc, roots=None) -> str:
    p = resolve_path(doc, roots)
    if p is None:                                   # файла нет на диске (фикстура) — хэш от пути, помечен
        return "path:" + hashlib.sha256(str(_get(doc, "file") or _get(doc, "doc_id")).encode()).hexdigest()[:16]
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def doc_date(doc) -> str:
    extra = _get(doc, "extra") or {}
    if extra.get("DocDate"):
        return str(extra["DocDate"])
    fields = _get(doc, "fields") or {}
    for k in DATE_FIELDS:
        v = _get(fields.get(k), "value")
        if v:
            return str(v)
    return ""


def _mail_sent(doc, level: str, flags: list) -> str:
    mail = (_get(doc, "extra") or {}).get("mail")
    if not mail:
        return "не требуется" if level not in ("L1", "L2") and not flags else "нет"
    if mail.get("sent"):
        return "да"
    return "сохранено .eml" if mail.get("eml") else "нет"


def doc_to_row(doc, roots=None, processed_at: str | None = None) -> dict:
    route = _get(doc, "route")
    lawyer, review = _get(route, "lawyer"), _get(route, "review")
    level = _get(lawyer, "level") or ""
    codes = list(_get(lawyer, "reason_codes") or [])
    flags = list(_get(review, "flags") or [])
    mail = (_get(doc, "extra") or {}).get("mail") or {}
    return {
        "sha256": file_sha256(doc, roots),
        "doc_id": _get(doc, "doc_id") or "",
        "file": _get(doc, "file") or "",
        "doc_type": _get(doc, "doc_type") or "",
        "doc_date": doc_date(doc),
        "route_level": level,
        "route_codes": ";".join(codes),
        "review_flags": ";".join(flags),
        "mail_eml": str(mail.get("eml") or ""),
        "mail_sent": _mail_sent(doc, level, flags),
        "mail_to": mail.get("to") or "",
        "mail_error": mail.get("error") or "",
        "processed_at": processed_at or datetime.now().isoformat(timespec="seconds"),
    }


def read_registry(path: Path) -> list[dict]:
    if not Path(path).exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _key(row: dict) -> tuple[str, str]:
    return row["sha256"], row["doc_date"]


def already_sent(doc, registry_path: Path, roots=None) -> bool:
    """Для run_examples: не отправлять письмо повторно, если по этому файлу оно уже ушло."""
    key = (file_sha256(doc, roots), doc_date(doc))
    return any(_key(r) == key and r.get("mail_sent") == "да" for r in read_registry(registry_path))


def update_registry(docs, out_dir: Path | str, roots=None, name: str = "registry.csv") -> Path:
    path = Path(out_dir) / name
    rows = {_key(r): r for r in read_registry(path)}
    now = datetime.now().isoformat(timespec="seconds")
    for d in docs:
        row = doc_to_row(d, roots, now)
        old = rows.get(_key(row))
        if old and old.get("mail_sent") == "да" and row["mail_sent"] != "да":
            # письмо по этому файлу уже уходило в прошлом прогоне — статус не затираем
            for k in ("mail_eml", "mail_sent", "mail_to"):
                row[k] = old[k]
        rows[_key(row)] = row
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\r\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: (r["doc_id"], r["doc_date"])))
    return path
