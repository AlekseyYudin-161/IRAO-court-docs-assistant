"""Mailer tests"""

from pathlib import Path

from src.core.contract import load
from src.export.mailer import build_message, send_for_doc


def test_l2_letter_short_with_case_and_quote(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)       # письмо только в .eml, без реальной отправки
    doc = load("fixtures/doc_fssp_001.json")
    msg = build_message(doc, "a@b.c", "x@y.z")
    text = msg.get_body(preferencelist=("plain",)).get_content()
    assert msg["Subject"].startswith("[L2]") and "2-8540/2033" in msg["Subject"]
    for marker in ("нужно провести проверку", "Причина направления", "ст. 46", "окончить", "Решение остаётся за сотрудником"):
        assert marker in text
    assert len(text.strip().splitlines()) <= 12          # коротко, как просили орги
    status = send_for_doc(doc, tmp_path)
    assert Path(status["eml"]).exists() and status["sent"] is False and status["error"] is None


def test_pdf_attached_when_present():
    doc = load("fixtures/doc_fssp_001.json")
    msg = build_message(doc, "a@b.c", "x@y.z")
    names = [p.get_filename() for p in msg.iter_attachments()]
    # исходник + строка таблицы (требование бота 02.10)
    assert names == ["fssp_001.pdf", "fssp_001_row.csv"]
    row = [p for p in msg.iter_attachments() if p.get_filename().endswith(".csv")][0].get_content()
    assert "route_level" in row and "IdDeloNo" in row
