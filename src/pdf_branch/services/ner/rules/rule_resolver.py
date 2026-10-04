from .address_rules import extract_address as regex_address
from .case_rules import extract_case_date, extract_case_number
from .debt_rules import extract_duty, extract_main_debt, extract_penalty
from .models import Candidate, RuleExtraction
from .period_rules import extract_period
from .person_rules import extract_birth_date, extract_co_debtors, extract_debtor_block, is_official
from .text_utils import window_after

import re

from .person_rules import signature
from .text_utils import window_after


class RuleResolver:

    def __init__(
        self,
        name_extractor,
        date_extractor,
        money_extractor,
        address_extractor,
        passport_extractor,
        snils_extractor,
        tin_extractor,
    ):
        self.name_extractor = name_extractor
        self.date_extractor = date_extractor
        self.money_extractor = money_extractor
        self.address_extractor = address_extractor
        self.passport_extractor = passport_extractor
        self.snils_extractor = snils_extractor
        self.tin_extractor = tin_extractor

    def resolve(self, text: str) -> RuleExtraction:
        result = RuleExtraction()

        money = self.money_extractor.extract_candidates(text)
        passports = self.passport_extractor.extract_candidates(text)
        snils = self.snils_extractor.extract_candidates(text)
        tins = [t for t in self.tin_extractor.extract_candidates(text)
                if len(re.sub(r"\D", "", t.value)) == 12]  # у физлица ИНН 12 цифр, 10 цифр у организации-взыскателя

        if case_number := extract_case_number(text):
            result.case_number = case_number.value
        if case_date := extract_case_date(text):
            result.case_date = case_date.value
        period_start, period_end = extract_period(text)
        if period_start:
            result.period_start = period_start.value
        if period_end:
            result.period_end = period_end.value

        # люди: все полные ФИО, кроме судей, приставов и взыскателей
        people = [n for n in self.name_extractor.extract_candidates(text) if not is_official(text, n)]

        # основной должник: первое ФИО в блоке «должник…», а если блока нет, первое из всех
        block = extract_debtor_block(text)
        in_block = [n for n in people if block and block[1] <= n.start and n.end <= block[2]]
        main = next(iter(in_block or people), None)

        if main:
            result.fio = main.value
            result.surname, result.first_name, result.patronymic = (main.value.split() + [None] * 3)[:3]

            # в приказе должник назван дважды (вводная и резолютивная часть): данные идут после любого упоминания
            mentions = [p for p in people if signature(p.value) == signature(main.value)]
            starts = sorted(p.start for p in people)
            next_person = lambda pos: next((s for s in starts if s >= pos), None)

            for m in mentions:
                win = window_after(text, m.end, stop=next_person(m.end))
                result.birth_date = result.birth_date or extract_birth_date(win)
                if not result.street or not result.house:
                    street, house, flat = self.address_extractor.street_house_flat(win)
                    if not house:  # natasha не вытащила дом → regex
                        street, house, flat = regex_address(win)
                    if street and (house or not result.street):
                        result.street, result.house, result.flat = street, house, flat

            result.passport = self._first_after(text, mentions, passports)
            result.snils = self._first_after(text, mentions, snils)
            result.inn = self._first_after(text, mentions, tins)
            result.co_debtors = extract_co_debtors(people, main)

        result.co_debtors_count = len(result.co_debtors)

        if main_debt := extract_main_debt(text, money):
            result.debt_main = main_debt.value
        if penalty := extract_penalty(text, money):
            result.debt_penalty = penalty.value
        if duty := extract_duty(text, money):
            result.debt_duty = duty.value

        return result

    @staticmethod
    def _first_after(text: str, persons: list[Candidate], candidates: list[Candidate], size: int = 500, stop_fn=None) -> str | None:
        """Первый кандидат после ФИО, но до «в пользу / взыскатель»: дальше идут данные взыскателя."""
        for p in persons:
            end = p.end + len(window_after(text, p.end, size, stop=stop_fn(p.end) if stop_fn else None))
            hit = next((c for c in candidates if p.end <= c.start < end), None)
            if hit:
                return hit.value
        return None

    @staticmethod
    def _find_birth_date(
        text: str,
        person: Candidate,
        dates: list[Candidate],
    ) -> Candidate | None:

        search_start = person.end
        search_end = min(len(text), person.end + 300)

        local_text = text[search_start:search_end].lower()

        markers = [
            "дата рождения",
            "дата рожд.",
            "родился",
            "родилась",
            "года рождения",
        ]

        positions = [
            local_text.find(marker)
            for marker in markers
            if local_text.find(marker) >= 0
        ]

        if not positions:
            return None

        marker_position = search_start + min(positions)

        dates = [
            date
            for date in dates
            if 0 <= date.start - marker_position <= 100
        ]

        return min(
            dates,
            key=lambda date: date.start - marker_position,
            default=None,
        )