"""DbtrAdr → street («г Тест, ул. Примерова»), dom, kv.

Два формата в наборе:
  A. 9 полей через запятую: «643,644086,55,,,Тест,22 Пробная,9,23» — страна, индекс, регион, район,
     город, нас. пункт, улица, дом, квартира. Тип улицы в теге не указан — ищем название в IdDebtText
     («ул. Примерный пер.» → пер., «пр-кт Макетчиков» → пр-кт), иначе «ул.».
  B. свободный текст: «644027, Россия, , , г. Тест, , ул. Примерова, д. 235, корп. А, кв. 4».

posthoc=True — обобщаемые правки под формат эталона:
  * дом с литерой → «38/Б», с цифровым корпусом → «62 корп.1»;
  * «5 Образцовая» / «4-я Условная» → «Образцовая 5-я» (порядковые улицы как в ФИАС). Номер > 12 не
    переставляем: в выборке это улицы-даты вида «22 Апреля», эталон оставляет их как есть.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

STREET_TYPES = {
    "ул": "ул.", "улица": "ул.", "пер": "пер.", "переулок": "пер.", "пр-кт": "пр-кт", "просп": "пр-кт",
    "проспект": "пр-кт", "городок": "городок.", "б-р": "б-р", "бульвар": "б-р", "ш": "ш.", "шоссе": "ш.",
    "мкр": "мкр.", "проезд": "проезд", "пл": "пл.", "наб": "наб.",
}
_TYPE = r"(ул|улица|пер|переулок|пр-кт|просп|проспект|городок|б-р|бульвар|ш|шоссе|мкр|проезд|пл|наб)\.?"
ORDINAL_RE = re.compile(r"^(\d+)(-я)?\s+(\S.*)$")
MAX_ORDINAL = 12
MARKERS_RE = re.compile(r"\b(?:г|д|кв)\.", re.IGNORECASE)


@dataclass
class Address:
    street: str = ""
    dom: str = ""
    kv: str = ""
    structured: bool = True          # False — адрес не 9 полей и без маркеров «г./д./кв.» → кандидат на LLM
    type_evidence: str | None = None  # откуда взят тип улицы


def _norm_type(t: str) -> str:
    return STREET_TYPES.get(t.lower().rstrip("."), t)


def _norm_name(name: str, posthoc: bool) -> str:
    name = re.sub(r"\s+", " ", name).strip()
    m = ORDINAL_RE.match(name)
    if posthoc and m and (m.group(2) or int(m.group(1)) <= MAX_ORDINAL):
        return f"{m.group(3)} {m.group(1)}-я"
    return name


def _norm_dom(dom: str, korp: str = "", posthoc: bool = True) -> str:
    dom = re.sub(r"\s+", " ", dom).strip()
    if not posthoc:
        return f"{dom} корп.{korp}" if korp else dom
    m = re.fullmatch(r"(\d+)\s*([А-ЯЁа-яё])", dom)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    m = re.fullmatch(r"(\d+)\s*к(?:орп\.?)?\s*(\d+)", dom, re.IGNORECASE)
    if m:
        return f"{m.group(1)} корп.{m.group(2)}"
    if korp:
        return f"{dom}/{korp}" if re.fullmatch(r"[А-ЯЁа-яё]", korp) else f"{dom} корп.{korp}"
    return dom


def _city(raw: str) -> str:
    return re.sub(r"^г\.?\s*", "", raw.strip())


def _join(city: str, stype: str, name: str) -> str:
    street = f"{stype} {name}".strip()
    return f"г {city}, {street}" if city else street


def street_type_from_text(name: str, text: str) -> tuple[str, str | None]:
    """Тип улицы по упоминанию названия в IdDebtText. Тип после названия («Примерный пер.») важнее,
    чем перед ним («ул. Примерный пер.»)."""
    base = ORDINAL_RE.match(name).group(3) if ORDINAL_RE.match(name) else name
    rx = re.compile(r"(?:\b" + _TYPE + r"\s+)?(?:\d+(?:-я)?\s+)?" + re.escape(base) + r"(?:\s+" + _TYPE + r"(?=[\s,.]|$))?",
                    re.IGNORECASE)
    for m in rx.finditer(text):
        t = m.group(2) or m.group(1)
        if t:
            return _norm_type(t), f"IdDebtText[{m.start()}:{m.end()}]: {m.group(0)}"
    return "ул.", None


def _split_fields(parts: list[str], text: str, posthoc: bool) -> Address:
    city = _city(parts[5] or parts[4])
    raw_name = parts[6].strip()
    stype, ev = street_type_from_text(raw_name, text) if raw_name else ("", None)
    name = _norm_name(raw_name, posthoc)
    return Address(_join(city, stype, name) if name else "", _norm_dom(parts[7], posthoc=posthoc),
                   parts[8].strip(), True, ev)


def _split_free(adr: str, posthoc: bool) -> Address:
    chunks = [c.strip() for c in adr.split(",") if c.strip()]
    city = stype = name = dom = korp = kv = ""
    for c in chunks:
        if re.match(r"г\.?\s", c) and not city:
            city = _city(c)
        elif m := re.match(r"(?:д\.|дом\b)\s*(.+)", c, re.IGNORECASE):
            dom = m.group(1)
        elif m := re.match(r"кв\.?\s*(.+)", c, re.IGNORECASE):      # раньше «к.»: иначе «кв.121» станет корпусом
            kv = m.group(1).strip()
        elif m := re.match(r"(?:корп\.?|к\.)\s*(.+)", c, re.IGNORECASE):
            korp = m.group(1).strip()
        elif not name and (m := re.match(_TYPE + r"\s+(.+)", c, re.IGNORECASE)):
            stype, name = _norm_type(m.group(1)), m.group(2)
        elif not name and (m := re.match(r"(.+?)\s+" + _TYPE + r"$", c, re.IGNORECASE)):
            stype, name = _norm_type(m.group(2)), m.group(1)
    name = _norm_name(name, posthoc) if name else ""
    structured = bool(MARKERS_RE.search(adr))
    return Address(_join(city, stype, name) if name else "", _norm_dom(dom, korp, posthoc) if dom else "", kv,
                   structured, "xpath:/OIp/DbtrAdr" if stype else None)


def split_address(adr: str, debt_text: str = "", posthoc: bool = True) -> Address:
    parts = adr.split(",")
    if len(parts) == 9 and parts[0].strip() == "643":
        return _split_fields(parts, debt_text, posthoc)
    return _split_free(adr, posthoc)
