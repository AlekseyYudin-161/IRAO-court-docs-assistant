"""XML постановления ФССП → плоский словарь тегов + сведения для правил (extra). Без OCR и LLM.

В наборе два пространства имён (order/2017/2 и order_fssp/2022/1) — теги ищем по local-name.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

# 13 столбцов шаблона, которые копируются из одноимённых тегов
COPY_COLUMNS: list[str] = [
    "DocType", "DebtorType", "DocDate", "IdDebtText", "IdDocNo", "IdDocDate", "IdDeloNo",
    "IdDeloDate", "IdDebtSum", "IpNo", "IdType", "DbtrAdr", "DbtrName",
]
RAW_COLUMNS = {"IdDebtText", "DbtrAdr"}           # без strip(): в разметке они байт-в-байт как в теге


def _local(el: etree._Element) -> str:
    return etree.QName(el).localname


def _children(el: etree._Element, name: str) -> list[etree._Element]:
    return [c for c in el if isinstance(c.tag, str) and _local(c) == name]


def parse_xml(path: str | Path) -> tuple[dict[str, str], etree._Element]:
    """Теги верхнего уровня без вложенности: {имя: текст}. Повторяющиеся теги — первое вхождение."""
    root = etree.parse(str(path)).getroot()
    tags: dict[str, str] = {}
    for el in root:
        if not isinstance(el.tag, str) or len(el):
            continue
        name = _local(el)
        if name not in tags:
            text = el.text or ""
            tags[name] = text if name in RAW_COLUMNS else text.strip()
    return tags, root


def npa_articles(root: etree._Element) -> list[str]:
    """OIpNpaActsOIp/OIpNpaArticle рекурсивно → ['46', '46/1', '46/1/4', …] (статья/часть/пункт).
    Блок предупреждений (OIpActWarningsOIp) не берём: там ст. 121–122 о порядке обжалования."""
    out: list[str] = []

    def walk(el: etree._Element, prefix: str) -> None:
        for a in _children(el, "OIpNpaArticle"):
            num = next((c.text or "").strip() for c in _children(a, "NpaArticle"))
            path = f"{prefix}/{num}" if prefix else num
            if path not in out:
                out.append(path)
            walk(a, path)

    for acts in _children(root, "OIpNpaActsOIp"):
        walk(acts, "")
    return out


def rule_extra(tags: dict[str, str], root: etree._Element) -> dict:
    """Поля для правил маршрутизации — в таблицу не идут."""
    return {
        "npa_articles": npa_articles(root),
        "adjudication_text": tags.get("AdjudicationText", ""),
        "resolution_text": tags.get("ResolutionText", ""),
        "ip_rest_debtsum": tags.get("IpRestDebtsum", ""),
        "dbtr_inn": tags.get("DbtrInn", ""),
        "dbtr_snils": tags.get("IdDbtrSNILS", ""),
        "dbtr_born": tags.get("idDbtrBorn", ""),
    }
