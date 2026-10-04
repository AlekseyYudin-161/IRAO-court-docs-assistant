"""IdDebtText → период и суммы взыскания (date_start, date_end, rub_*). Регулярки, без LLM.

posthoc=True — обобщаемые правки под то, как размечен эталон:
  * сумма 0 («в размере 0 (ноль рублей 00 копеек)») — заглушка бланка, а не установленное значение → пусто;
  * в тексте нет «задолженность … в размере», а других сумм тоже нет → основной долг = IdDebtSum
    (вся сумма взыскания и есть основной долг), с пониженной уверенностью.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

MONEY = r"(\d{1,3}(?:[  ]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
DATE = r"(\d{1,2}\.\d{1,2}\.\d+)"
# «(?:(?!в размере).)» — не перескакиваем через чужое «в размере»: «пени в размере _, … пошлины в размере 0»
_GAP = r"(?:(?!в размере).){0,%d}?"

PERIOD_RE = re.compile(r"за период\s+(?:с\s+)?" + DATE + r"\s*(?:г\.)?\s*по\s+" + DATE, re.IGNORECASE | re.DOTALL)
MONEY_RE: dict[str, re.Pattern] = {
    "rub_deb": re.compile(r"задолженн?ост\w*" + _GAP % 250 + r"в размере\s+" + MONEY, re.IGNORECASE | re.DOTALL),
    "rub_peni": re.compile(r"\bпени\b" + _GAP % 120 + r"в размере\s+" + MONEY, re.IGNORECASE | re.DOTALL),
    "rub_poshlina": re.compile(r"государственн\w*\s+пошлин\w*" + _GAP % 40 + r"в размере\s+" + MONEY, re.IGNORECASE | re.DOTALL),
    # только «почтовые расходы»: «судебные расходы по отправке почтовой корреспонденции» в эталоне сюда не идут
    "rub_post": re.compile(r"почтов\w+\s+расход\w*" + _GAP % 40 + r"в размере\s+" + MONEY, re.IGNORECASE | re.DOTALL),
}
ANY_MONEY_RE = re.compile(r"в размере\s+" + MONEY, re.IGNORECASE)

DATE_COLUMNS = ["date_start", "date_end"]
MONEY_COLUMNS = list(MONEY_RE)
DERIVED_COLUMNS = DATE_COLUMNS + MONEY_COLUMNS
LONG_TEXT = 200


@dataclass
class Derived:
    value: str = ""
    span: tuple[int, int] | None = None      # срез IdDebtText — для evidence
    confidence: float = 0.0
    note: str | None = None                  # «posthoc: …» — откуда взялось значение без прямого совпадения


def money(raw: str) -> str:
    """'88300,94' / '4 000' / '4338' → '88300.94' / '4000.00' / '4338.00'; не число — пусто."""
    try:
        return str(Decimal(re.sub(r"[  ]", "", raw).replace(",", ".")).quantize(Decimal("0.01")))
    except InvalidOperation:
        return ""


def iso_date(raw: str) -> str:
    """'03.01.2031' → '2031-01-03'; битая дата ('01.11.20217') — пусто."""
    try:
        d, m, y = (int(x) for x in raw.split("."))
        if not 1000 <= y <= 9999:
            return ""
        return date(y, m, d).isoformat()
    except ValueError:
        return ""


def derive_from_text(text: str, id_debt_sum: str = "", posthoc: bool = True) -> tuple[dict[str, Derived], list[str]]:
    """Возвращает (столбец → Derived, список столбцов-кандидатов на LLM-fallback).

    Кандидаты: нет «задолженност… в размере» при тексте > 200 симв.; дата периода не парсится;
    больше одного «Взыскать» (несколько требований — правило берёт только первое)."""
    out = {c: Derived() for c in DERIVED_COLUMNS}
    fallback: list[str] = []

    m = PERIOD_RE.search(text)
    if m:
        for col, grp in (("date_start", 1), ("date_end", 2)):
            v = iso_date(m.group(grp))
            if v:
                out[col] = Derived(v, m.span(grp), 0.9)
            else:
                fallback.append(col)

    for col, rx in MONEY_RE.items():
        m = rx.search(text)
        if not m:
            continue
        v = money(m.group(1))
        if posthoc and v and Decimal(v) == 0:
            continue
        if v:
            out[col] = Derived(v, m.span(1), 0.9)

    if not out["rub_deb"].value and len(text.strip()) > LONG_TEXT:
        fallback.append("rub_deb")
        others = any(out[c].value for c in MONEY_COLUMNS)
        if posthoc and not others and money(id_debt_sum):
            out["rub_deb"] = Derived(money(id_debt_sum), None, 0.5, "posthoc: IdDebtSum, других сумм в тексте нет")

    if len(re.findall(r"\bвзыскать\b", text, re.IGNORECASE)) > 1:
        fallback += [c for c in DERIVED_COLUMNS if c not in fallback]
    return out, fallback


def arith_check(text: str, id_debt_sum: str, derived: dict[str, Derived]) -> dict | None:
    """Сумма всех «в размере N» из IdDebtText против IdDebtSum. None — проверять нечего
    (нет основного долга или требований несколько)."""
    total = money(id_debt_sum)
    if not total or not derived["rub_deb"].span or len(re.findall(r"\bвзыскать\b", text, re.IGNORECASE)) > 1:
        return None
    parts = [money(m.group(1)) for m in ANY_MONEY_RE.finditer(text)]
    s = sum((Decimal(p) for p in parts if p), Decimal("0"))
    return {"ok": abs(s - Decimal(total)) < Decimal("0.01"), "sum": str(s), "expected": total}
