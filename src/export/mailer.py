# src/export/mailer.py
"""Письмо ответственному сотруднику: коротко, с явной причиной и двумя вложениями (исходник + строка таблицы).
Уходит для L1/L2 и для документов с флагами ручной проверки (review.flags) — формат согласован с ботом оргов 02.10.
Всегда сохраняет .eml в out/mail/; по SMTP отправляет только при заданном SMTP_HOST."""

from __future__ import annotations

import csv
import io
import logging
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

from src.core.columns import ACT_FIELDS, OCR_COLUMNS, XML_COLUMNS
from src.core.contract import Doc

log = logging.getLogger("mail")
DATA_ROOT = Path(os.getenv("DATA_ROOT", "data/courts_anonymized"))
ACTS_ROOT = Path(os.getenv("ACTS_ROOT", "data"))          # акты: doc.file = "acts/Акт_02.pdf" (относительно data/)

# Запасные формулировки по уровню; формулировки оргов по кодам придут из rules/codes.py (карточка C)
DEFAULT_TEXT = {"L1": "требуется действие в установленный срок",
                "L2": "требуется действие юриста, срочного срока нет"}
# Причины канала review — словами, как просил бот оргов (низкая уверенность / нет обязательных полей / противоречия)
REVIEW_TEXT = {"LOW_CONFIDENCE": "низкая уверенность распознавания",
               "REQUIRED_FIELD_MISSING": "не извлечены обязательные реквизиты",
               "ID_CONFLICT": "противоречия в реквизитах (несколько ИНН/паспортов)",
               "ARITH_CHECK_FAILED": "сумма не сходится с составляющими",
               "UNCLASSIFIED": "тип документа не распознан"}


def needs_letter(doc: Doc) -> bool:
    """Кому пишем: L1/L2 (юридическое действие) или есть флаги ручной проверки."""
    return doc.route.lawyer.level in ("L1", "L2") or bool(doc.route.review.flags)


def _letter_text(doc: Doc) -> str:
    if doc.extra.get("actions"):                       # судебные акты: действия из маркеров оргов (src/rules/markers.py)
        return "; ".join(doc.extra["actions"])
    try:
        from src.rules.codes import LETTER_TEXT  # {"FSSP_END_46_1_4": "…", …} — появится у junior ml
    except ImportError:
        LETTER_TEXT = {}
    for code in doc.route.lawyer.reason_codes:
        if code in LETTER_TEXT:
            return LETTER_TEXT[code]
    return DEFAULT_TEXT.get(doc.route.lawyer.level, "требуется проверка")


def _reason(doc: Doc) -> str:
    """Явная причина направления — первая строка письма."""
    L, R = doc.route.lawyer, doc.route.review
    parts = []
    if L.level in ("L1", "L2"):
        parts.append(f"требуется юридическое действие: {_letter_text(doc)}")
    if R.flags:
        parts.append("требуется ручная проверка реквизитов: " + "; ".join(REVIEW_TEXT.get(f, f) for f in R.flags))
    return " и ".join(parts) or "требуется проверка"


def _case(doc: Doc) -> tuple[str, str]:
    """Номер и дата дела для темы и первой строки: XML — IdDeloNo/IdDeloDate, PDF — дело_номер/дело_дата."""
    f = doc.fields
    if doc.table == "xml":
        return f.get("IdDeloNo", None) and f["IdDeloNo"].value or "", f.get("IdDeloDate", None) and f["IdDeloDate"].value or ""
    return f.get("дело_номер", None) and f["дело_номер"].value or "", f.get("дело_дата", None) and f["дело_дата"].value or ""


def _attachment(doc: Doc) -> Path | None:
    """Исходный документ: PDF — сам файл, XML — двойник <stem>.pdf рядом, судебный акт — из data/acts."""
    root = ACTS_ROOT if doc.table == "acts" else DATA_ROOT
    p = root / doc.file
    if p.suffix.lower() == ".xml":
        p = p.with_suffix(".pdf")
    return p if p.exists() else None


def _row_csv(doc: Doc) -> str:
    """Строка таблицы с результатами — второе вложение (столбцы шаблона оргов + маршрут, как в routing.csv)."""
    L, R = doc.route.lawyer, doc.route.review
    cols = {"ocr": OCR_COLUMNS, "xml": XML_COLUMNS, "acts": ACT_FIELDS}[doc.table]
    row = {c: (doc.fields[c].value if c in doc.fields else "") for c in cols}
    if doc.table == "ocr":
        row.update({"Файл": doc.file, "тип документа": doc.doc_type})
    elif doc.table == "xml":
        row["FileName"] = doc.file
    row.update({"route_level": L.level, "route_codes": ";".join(L.reason_codes), "review_flags": ";".join(R.flags)})
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(row), lineterminator="\r\n")
    w.writeheader()
    w.writerow(row)
    return "\ufeff" + buf.getvalue()                      # BOM — чтобы Excel открыл кириллицу


def build_message(doc: Doc, to_addr: str, from_addr: str) -> EmailMessage:
    L = doc.route.lawyer
    case_no, case_date = _case(doc)
    case = f"по делу № {case_no}" + (f" от {case_date}" if case_date else "") if case_no else f"по документу {doc.doc_id}"
    subj = f"[{L.level}] Проверка {case} — {doc.doc_type}" + (f" — срок до {L.deadline}" if L.deadline else "")
    body = [f"Добрый день. {case[0].upper() + case[1:]} ({doc.doc_type}, файл {Path(doc.file).name}) нужно провести проверку. "
            f"Причина направления — {_reason(doc)}."]
    if L.basis:
        body.append(f"Основание: {L.basis}." + (f" Срок: до {L.deadline}." if L.deadline else ""))
    if L.evidence:
        body.append(f"Фрагмент документа: {L.evidence}")
    body.append("Во вложении — исходный документ и строка таблицы с результатами распознавания. "
                "Решение остаётся за сотрудником; система только рекомендует.")
    msg = EmailMessage()
    msg["Subject"], msg["To"], msg["From"] = subj, to_addr, from_addr
    msg.set_content("\n\n".join(body))
    att = _attachment(doc)
    if att:
        msg.add_attachment(att.read_bytes(), maintype="application", subtype="pdf", filename=att.name)
    else:
        log.warning("%s: исходный документ для вложения не найден (%s)", doc.doc_id, doc.file)
    msg.add_attachment(_row_csv(doc), subtype="csv", charset="utf-8", filename=f"{doc.doc_id}_row.csv")
    return msg


def render(doc: Doc, to_addr: str | None = None) -> tuple[str, str]:
    """(тема, тело) для превью письма в UI — карточка E вызывает mailer.render(doc, to_addr)."""
    msg = build_message(doc, to_addr or os.getenv("LAWYER_EMAIL", "lawyer@example.local"),
                        os.getenv("MAIL_FROM", "doc-assistant@example.local"))
    return str(msg["Subject"]), msg.get_body(preferencelist=("plain",)).get_content()


def send_for_doc(doc: Doc, mail_dir: Path, to_addr: str | None = None) -> dict:
    """Возвращает статус для реестра: {"eml": путь, "sent": bool, "to": адрес, "error": str|None}.
    to_addr — адрес получателя из UI; по умолчанию LAWYER_EMAIL из .env."""
    to_addr = to_addr or os.getenv("LAWYER_EMAIL", "lawyer@example.local")
    from_addr = os.getenv("MAIL_FROM", "doc-assistant@example.local")
    msg = build_message(doc, to_addr, from_addr)
    mail_dir.mkdir(parents=True, exist_ok=True)
    path = mail_dir / f"{doc.doc_id}.eml"
    path.write_bytes(msg.as_bytes())
    status = {"eml": str(path), "sent": False, "to": to_addr, "error": None}
    host = os.getenv("SMTP_HOST")
    if not host:
        log.info("SMTP не настроен, письмо сохранено в %s", path)
        return status
    port = int(os.getenv("SMTP_PORT", "465"))
    user, password = os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD")
    try:
        if os.getenv("SMTP_SSL", "1") == "1":          # Яндекс: smtp.yandex.ru:465, SSL
            server = smtplib.SMTP_SSL(host, port, timeout=20)
        else:                                          # Mailpit / STARTTLS-серверы
            server = smtplib.SMTP(host, port, timeout=20)
            if user:
                server.starttls()
        with server:
            if user:
                server.login(user, password or "")
            server.send_message(msg)
        status["sent"] = True
        log.info("отправлено %s -> %s", doc.doc_id, to_addr)
    except Exception as e:
        status["error"] = f"{type(e).__name__}: {e}"
        log.warning("SMTP не сработал (%s), письмо сохранено в %s", e, path)
    return status
