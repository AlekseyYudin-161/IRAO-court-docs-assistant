"""Тесты маркеров на наборе оргов data/acts/ (11 актов, «Фразы и примеры.csv»). 
Запуск: pytest tests/test_markers.py -q"""

import csv
from pathlib import Path

import pymupdf
import pytest

from src.rules.markers import looks_like_court_act, operative_part, route_court_act

ACTS = Path("data/acts")
pytestmark = pytest.mark.skipif(not ACTS.exists(), reason="data/acts отсутствует")


def _text(p: Path) -> str:
    return " ".join(pg.get_text("text", sort=True) for pg in pymupdf.open(p))


def _expected() -> dict[str, set[int]]:
    exp: dict[str, set[int]] = {}
    with open(ACTS / "Фразы и примеры.csv", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f, delimiter=";"):
            exp.setdefault(r["Пример судебного акта"], set()).add(int(r["Номер фразы"]))
    return exp


@pytest.mark.parametrize("name,nos", sorted(_expected().items()) if ACTS.exists() else [])
def test_each_act_has_its_marker(name, nos):
    rt = route_court_act(_text(ACTS / name))
    found = {h.no for h in rt.hits}
    assert nos <= found, f"{name}: ожидали {nos}, нашли {found}"
    assert rt.level in ("L1", "L2") and rt.evidence


def test_marker_only_in_operative_part():
    # Акт_08: «решение … отменить» есть и в описательной части как пересказ жалобы; считать должны только резолютивную
    txt = _text(ACTS / "Акт_08.pdf")
    op, _ = operative_part(txt)
    assert "отменить" in op and len(op) < len(txt) // 4


def test_classifier_and_no_false_positives_on_main_set():
    for name in ("Акт_01.pdf", "Акт_04.pdf", "Акт_09.pdf"):
        assert looks_like_court_act(_text(ACTS / name))
    for p in [*Path("data/ocr").rglob("*.pdf")][:3] + [*Path("data/fssp").rglob("*.pdf")][:2]:
        txt = _text(p)
        assert not looks_like_court_act(txt), p
        assert route_court_act(txt).reason_codes == [], p
