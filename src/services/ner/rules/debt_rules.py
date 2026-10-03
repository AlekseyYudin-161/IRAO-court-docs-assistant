import re

from .models import Candidate


MAIN_DEBT_PATTERNS = [
    r"задолженн(?:ость|ости).*?(?:в\s+размере|составляет|сумме)",
    r"сумма\s+основного\s+долга.*?(?:в\s+размере|составляет|сумме)",
    r"основной\s+долг.*?(?:в\s+размере|составляет|сумме)",
]


PENALTY_PATTERNS = [
    r"пен[яи].*?(?:в\s+размере|составляет|сумме)",
    r"неустойк[аи].*?(?:в\s+размере|составляет|сумме)",
]


DUTY_PATTERNS = [
    r"государственн(?:ой|ая)\s+пошлин[аые].*?(?:в\s+размере|составляет|сумме)",
    r"госпошлин[аы].*?(?:в\s+размере|составляет|сумме)",
]


def _find_money_after_anchor(
    text: str,
    anchor_patterns: list[str],
    money_candidates: list[Candidate],
) -> Candidate | None:

    for pattern in anchor_patterns:
        for match in re.finditer(
            pattern,
            text,
            re.IGNORECASE | re.DOTALL,
        ):
            money = next(
                (
                    money
                    for money in money_candidates
                    if 0 <= money.start - match.end() <= 150
                ),
                None,
            )

            if money:
                return money

    return None


def extract_main_debt(
    text: str,
    money_candidates: list[Candidate],
) -> Candidate | None:
    return _find_money_after_anchor(text, MAIN_DEBT_PATTERNS, money_candidates)


def extract_penalty(
    text: str,
    money_candidates: list[Candidate],
) -> Candidate | None:
    return _find_money_after_anchor(text, PENALTY_PATTERNS, money_candidates)


def extract_duty(
    text: str,
    money_candidates: list[Candidate],
) -> Candidate | None:
    return _find_money_after_anchor(text, DUTY_PATTERNS, money_candidates)