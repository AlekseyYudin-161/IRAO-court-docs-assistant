import re

from .models import Candidate, PersonCandidate


DEBTOR_BLOCK_PATTERNS = [
    (
        r"(?:с\s+)?должник(?:а|у|ом|ов)?\s*:?(?P<block>.*?)(?=\bв\s+пользу\b|\bвзыскатель\b|\bистец\b|\bответчик\b|\Z)",
        0.95,
    ),
    (
        r"должник\s*:?(?P<block>.*?)(?=\bвзыскатель\b|\bв\s+пользу\b|\Z)",
        0.90,
    ),
]


def extract_debtor_block(text: str) -> tuple[str, int, int] | None:
    for pattern, _ in DEBTOR_BLOCK_PATTERNS:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE | re.DOTALL,
        )

        if match:
            return (
                match.group("block"),
                match.start("block"),
                match.end("block"),
            )

    return None


def extract_co_debtors(
    text: str,
    names: list[Candidate],
    main_person: PersonCandidate | None,
) -> list[Candidate]:

    if not names:
        return []

    if not main_person:
        return names

    main_span = main_person.fio.start, main_person.fio.end

    return [
        name
        for name in names
        if (name.start, name.end) != main_span
    ]


def build_person_from_name(
    name: Candidate,
    surname: str | None = None,
    first_name: str | None = None,
    patronymic: str | None = None,
) -> PersonCandidate:

    return PersonCandidate(
        fio=name,
        surname=Candidate(
            surname,
            name.start,
            name.start + len(surname),
            confidence=0.9,
        ) if surname else None,
        first_name=Candidate(
            first_name,
            name.start,
            name.start + len(first_name),
            confidence=0.9,
        ) if first_name else None,
        patronymic=Candidate(
            patronymic,
            name.start,
            name.end,
            confidence=0.9,
        ) if patronymic else None,
    )