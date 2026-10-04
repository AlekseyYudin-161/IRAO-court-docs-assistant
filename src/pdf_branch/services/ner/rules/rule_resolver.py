from .models import Candidate, RuleExtraction
from .case_rules import extract_case_number, extract_case_date
from .period_rules import extract_period
from .person_rules import extract_debtor_block
from .debt_rules import extract_main_debt, extract_penalty, extract_duty


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

    def resolve(
        self,
        text: str,
    ) -> RuleExtraction:

        result = RuleExtraction()

        names = self.name_extractor.extract_candidates(text)
        dates = self.date_extractor.extract_candidates(text)
        money = self.money_extractor.extract_candidates(text)
        passports = self.passport_extractor.extract_candidates(text)
        snils = self.snils_extractor.extract_candidates(text)
        tins = self.tin_extractor.extract_candidates(text)

        case_number = extract_case_number(text)
        if case_number:
            result.case_number = case_number.value

        case_date = extract_case_date(text, dates)
        if case_date:
            result.case_date = case_date.value

        period_start, period_end = extract_period(text)

        if period_start:
            result.period_start = period_start.value

        if period_end:
            result.period_end = period_end.value

        debtor_block = extract_debtor_block(text)

        if debtor_block:
            _, block_start, block_end = debtor_block
            names = [
                name
                for name in names
                if block_start <= name.start
                and name.end <= block_end
            ]

        main_person = names[0] if names else None

        if main_person:
            result.fio = main_person.value

            parts = main_person.value.split()
            result.surname = parts[0] if len(parts) > 0 else None
            result.first_name = parts[1] if len(parts) > 1 else None
            result.patronymic = parts[2] if len(parts) > 2 else None

            birth_date = self._find_birth_date(
                text,
                main_person,
                dates,
            )

            if birth_date:
                result.birth_date = birth_date.value

            result.passport = self._nearest(main_person, passports)
            result.snils = self._nearest(main_person, snils)
            result.inn = self._nearest(main_person, tins)

        result.co_debtors = [
            name.value
            for name in names[1:]
        ]
        result.co_debtors_count = len(result.co_debtors)

        main_debt = extract_main_debt(text, money)
        penalty = extract_penalty(text, money)
        duty = extract_duty(text, money)

        if main_debt:
            result.debt_main = main_debt.value

        if penalty:
            result.debt_penalty = penalty.value

        if duty:
            result.debt_duty = duty.value

        return result

    @staticmethod
    def _nearest(
        person: Candidate,
        candidates: list[Candidate],
        max_distance: int = 500,
    ) -> str | None:

        candidates = [
            candidate
            for candidate in candidates
            if abs(candidate.start - person.end) <= max_distance
        ]

        if not candidates:
            return None

        candidate = min(
            candidates,
            key=lambda candidate: abs(
                candidate.start - person.end
            ),
        )

        return candidate.value

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