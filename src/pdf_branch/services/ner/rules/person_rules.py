import re

from .models import Candidate
from .text_utils import window_after

DEBTOR_BLOCK_PATTERNS = [
    # самый точный якорь: «Должником по исполнительному документу является: …»
    (r"должник\w*\s+по\s+исполнительному\s+документу\s+является\s*:?(?P<block>.*?)"
     r"(?=в\s+пользу|взыскател|РЕШИЛ|\Z)", 1.0),
    (r"(?:с\s+)?должник(?:а|у|ом|ов)?\s*:?(?P<block>.*?)(?=в\s+пользу|взыскател|истец|ответчик|\Z)", 0.95),
]


def extract_debtor_block(text: str) -> tuple[str, int, int] | None:
    for pattern, _ in DEBTOR_BLOCK_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group("block"), match.start("block"), match.end("block")
    return None


# ---------------------------------------------------------------- кто НЕ должник

# слова, после которых идёт не должник: судья, пристав, взыскатель-физлицо и т.д.
_ROLE_RE = re.compile(
    r"судь|суд[аеу]?\b|пристав|секретар|прокурор|представител|председател|заместител|нотариус|"
    r"адвокат|свидетел|эксперт|взыскател|истц|заявител|кредитор|в\s+пользу",
    re.IGNORECASE,
)
_DEBTOR_RE = re.compile(r"должник|ответчик", re.IGNORECASE)


def is_official(text: str, name: Candidate, lookback: int = 80) -> bool:
    """ФИО судьи/пристава/взыскателя. Смотрим на 80 символов перед именем: что ближе к имени,
    слово-роль («судья», «в пользу», «взыскатель») или «должник»."""
    before = text[max(0, name.start - lookback):name.start]
    roles = [m.end() for m in _ROLE_RE.finditer(before)]
    debtors = [m.end() for m in _DEBTOR_RE.finditer(before)]
    return bool(roles) and (not debtors or max(roles) > max(debtors))


def signature(fio: str) -> tuple[str, ...]:
    """Один и тот же человек в разных падежах: первые 3 буквы каждого слова."""
    return tuple(w[:3].lower().replace("ё", "е") for w in fio.split())


def extract_co_debtors(people: list[Candidate], main: Candidate) -> list[str]:
    """Все остальные люди (не судьи и не основной должник), без повторов."""
    seen, result = {signature(main.value)}, []
    for person in people:
        if (sig := signature(person.value)) not in seen:
            seen.add(sig)
            result.append(person.value)
    return result


# ---------------------------------------------------------------- дата рождения

_MONTHS = "января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря"
_DATE = (
    r"(?:(?:0?[1-9]|[12]\d|3[01])[./\-](?:0?[1-9]|1[0-2])[./\-](?:19|20)\d\d"
    rf"|\d{{1,2}}\s+(?:{_MONTHS})\s+(?:19|20)\d\d)"
)
_BIRTH_WORD = r"(?:дат[аы]\s+рожд\w*|родил\w+|рожд\w+|(?<![а-яё])род\b\.?)"
BIRTH_PATTERNS = [
    re.compile(rf"{_BIRTH_WORD}[^\d]{{0,20}}?(?P<d>{_DATE})", re.IGNORECASE),
    re.compile(rf"(?P<d>{_DATE})\s*(?:г\.?\s*р\b|года\s+рожд|г\.\s*рожд)", re.IGNORECASE),
    # дата сразу после ФИО без маркера: «Иванова А.А., 18.10.1947, место…»
    re.compile(rf"^[\s,]{{0,3}}(?P<d>{_DATE})(?=\s*[,(]|\s+года|\s*$)", re.IGNORECASE),
]


def extract_birth_date(chunk: str) -> str | None:
    found = [m for p in BIRTH_PATTERNS if (m := p.search(chunk))]
    return min(found, key=lambda m: m.start("d"))["d"] if found else None