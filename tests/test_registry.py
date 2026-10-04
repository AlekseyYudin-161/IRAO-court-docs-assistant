"""Карточка D: реестр обработанных документов."""

from types import SimpleNamespace as NS

from src.export.registry import already_sent, read_registry, update_registry


def _doc(tmp_path, level="L2", mail=None, content=b"pdf-1"):
    f = tmp_path / "fssp_001.xml"
    f.write_bytes(content)
    fv = NS(value="2033-06-10")
    return NS(doc_id="fssp_001", file="fssp_001.xml", doc_type="постановление ФССП",
              fields={"DocDate": fv}, extra={"mail": mail} if mail else {},
              route=NS(lawyer=NS(level=level, reason_codes=["FSSP_END_46_1_4"]), review=NS(flags=[])))


def test_update_not_duplicate(tmp_path):
    roots = [tmp_path]
    d = _doc(tmp_path, mail={"eml": "out/mail/fssp_001.eml", "sent": True, "to": "lawyer@x", "error": None})
    update_registry([d], tmp_path / "out", roots)
    update_registry([d], tmp_path / "out", roots)
    rows = read_registry(tmp_path / "out" / "registry.csv")
    assert len(rows) == 1
    r = rows[0]
    assert r["doc_date"] == "2033-06-10" and r["route_level"] == "L2" and r["mail_sent"] == "да"
    assert len(r["sha256"]) == 64
    assert already_sent(d, tmp_path / "out" / "registry.csv", roots)


def test_sent_status_survives_rerun_without_mail(tmp_path):
    roots = [tmp_path]
    update_registry([_doc(tmp_path, mail={"eml": "a.eml", "sent": True, "to": "x"})], tmp_path, roots)
    update_registry([_doc(tmp_path)], tmp_path, roots)            # повторный прогон, письмо не отправлялось
    assert read_registry(tmp_path / "registry.csv")[0]["mail_sent"] == "да"


def test_changed_file_is_new_row(tmp_path):
    roots = [tmp_path]
    update_registry([_doc(tmp_path, content=b"v1")], tmp_path, roots)
    update_registry([_doc(tmp_path, content=b"v2")], tmp_path, roots)
    assert len(read_registry(tmp_path / "registry.csv")) == 2


def test_l3_needs_no_mail(tmp_path):
    update_registry([_doc(tmp_path, level="L3")], tmp_path, [tmp_path])
    assert read_registry(tmp_path / "registry.csv")[0]["mail_sent"] == "не требуется"
