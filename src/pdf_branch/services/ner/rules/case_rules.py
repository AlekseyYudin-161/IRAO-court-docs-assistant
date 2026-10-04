import re

from .models import Candidate
from .text_utils import clean_value


_LET = "А-Яа-яЁёA-Za-z"
_NUM = rf"(?P<number>[0-9{_LET}][0-9{_LET}./\\\-]*[0-9{_LET}])"
_SIGN = r"(?:№|N[оo]?\.?|No\.?)"
# «по делу (материалам делам) № ...» — в скобках может быть пояснение
_GAP = r"\s*(?:\([^)]{0,60}\)\s*)?"

CASE_NUMBER_PATTERNS = [
    rf"(?<![{_LET}])дел[ауео]{_GAP}{_SIGN}\s*{_NUM}",
    rf"(?<![{_LET}])производств[оау]{_GAP}{_SIGN}\s*{_NUM}",
    rf"(?<![{_LET}])материал(?:ам|ы|ов)?{_GAP}{_SIGN}\s*{_NUM}",
]

# Запасной вариант: идентификатор ИД вида 55RS0006#2-8612/2032#1
_ID_PATTERN = r"#(?P<number>\d+(?:-\d+)*/\d{4})#"

_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
_MONTH_RE = "|".join(_MONTHS)

# «от»; OCR иногда даёт «or», «oт»
_FROM = r"[оo][тtr]"
_DATE = (
    r"(?:(?P<d>\d{1,2})\.(?P<m>\d{1,2})\.(?P<y>\d{4})"
    rf"|«?(?P<d2>\d{{1,2}})»?\s+(?P<mon>{_MONTH_RE})\s+(?P<y2>\d{{4}}))"
)
_TRUNCATED_DATE = re.compile(r"\d{1,2}\.\d{1,2}\.\d{0,3}(?!\d)")


def _find_number_match(text: str) -> re.Match | None:
    for pattern in CASE_NUMBER_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match
    return None


def extract_case_number(text: str) -> Candidate | None:
    match = _find_number_match(text)
    confidence = 0.95

    if not match:
        match = re.search(_ID_PATTERN, text)
        confidence = 0.6

    if not match:
        return None

    return Candidate(
        value=clean_value(match.group("number")),
        start=match.start("number"),
        end=match.end("number"),
        confidence=confidence,
    )


def _to_candidate(match: re.Match, confidence: float) -> Candidate:
    if match.group("d"):
        day, month, year = int(match.group("d")), int(match.group("m")), match.group("y")
    else:
        day, month, year = int(match.group("d2")), _MONTHS[match.group("mon").lower()], match.group("y2")

    return Candidate(
        value=f"{day:02d}.{month:02d}.{year}",
        start=match.start(),
        end=match.end(),
        confidence=confidence,
    )


def extract_case_date(
    text: str,
    date_candidates: list[Candidate] | None = None,  # оставлен для совместимости, не нужен
) -> Candidate | None:
    """Дата дела в формате дд.мм.гггг.

    Исполнительный лист: «по делу № ... от 06.12.2032» — дата сразу после номера дела.
    Дата «Выдан: ...» и «вступает в законную силу ...» — это другие даты, их не берём.
    Судебный приказ: дата стоит в заголовке после слов «СУДЕБНЫЙ ПРИКАЗ».
    Если дата после номера обрезана OCR («06.12.2»), возвращаем None, а не угадываем.
    """
    number = _find_number_match(text)
    if number:
        after = re.compile(rf"\s*,?\s*{_FROM}\s*", re.IGNORECASE).match(text, number.end())
        if after:
            date = re.compile(_DATE, re.IGNORECASE).match(text, after.end())
            if date:
                return _to_candidate(date, 0.95)
            if _TRUNCATED_DATE.match(text, after.end()):
                return None

    order = re.search(
        rf"судебн\w+\s+приказ\W{{0,15}}?(?={_DATE})",
        text,
        re.IGNORECASE,
    )
    if order:
        date = re.compile(_DATE, re.IGNORECASE).search(text, order.end())
        if date:
            return _to_candidate(date, 0.9)

    generic = re.search(
        rf"(?:решени[еяю]|определени[еяю])\s+(?:суда\s+)?{_FROM}\s*(?={_DATE})",
        text,
        re.IGNORECASE,
    )
    if generic:
        date = re.compile(_DATE, re.IGNORECASE).search(text, generic.end())
        if date:
            return _to_candidate(date, 0.7)

    return None