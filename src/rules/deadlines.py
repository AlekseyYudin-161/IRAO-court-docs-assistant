"""Сроки для route.lawyer.deadline: "+10d" / "+6m" / "+1m" от даты постановления (DocDate).

Если даты документа нет (у приказов/ИЛ её нет в шаблоне) — считаем от as_of (дата прогона).
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

RULE_RE = re.compile(r"^\+(\d+)([dm])$")


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def compute(rule: str | None, base: date | None) -> date | None:
    if not rule or base is None:
        return None
    m = RULE_RE.match(rule)
    if not m:
        raise ValueError(f"неизвестное правило срока: {rule!r}")
    n = int(m.group(1))
    return base + timedelta(days=n) if m.group(2) == "d" else add_months(base, n)


def parse_iso(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def base_date(doc_date: str | None, as_of: date | None = None) -> date | None:
    return parse_iso(doc_date) or as_of


def days_left(deadline: str | date | None, as_of: date | None = None) -> int | None:
    d = parse_iso(deadline) if isinstance(deadline, str) else deadline
    return None if d is None else (d - (as_of or date.today())).days
