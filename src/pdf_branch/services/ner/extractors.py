import re

from natasha import AddrExtractor, MoneyExtractor

from .parsers.date_parser import date_parser
from .parsers.name_parser import name_parser
from .patterns import PASSPORT_NUMBER_PATTERN, SNILS_NUMBER_PATTERN, TIN_PATTERN
from .rules.models import Candidate


_PATRONYMIC = r"(?i:(?:ович|евич|ьич|овн|евн|ичн)(?:а|ы|е|у|ой|ем)?)"
FULL_NAME_RE = re.compile(
    rf"\b[А-ЯЁ][А-ЯЁа-яё\-]+(?:\s*\([А-ЯЁ][а-яё\-]+\))?\s+"
    rf"[А-ЯЁ][А-ЯЁа-яё]+\s+[А-ЯЁ][А-ЯЁа-яё]*?{_PATRONYMIC}\b"
)



class NameExtractor:
    def __init__(self):
        self.parser = name_parser()

    def extract_candidates(self, text: str) -> list[Candidate]:
        # 1) yargy: ФИО со знакомой словарю фамилией
        found = [
            Candidate(
                value=" ".join(part for part in (m.fact.last, m.fact.first, m.fact.middle) if part),
                start=m.span.start,
                end=m.span.stop,
                confidence=0.90,
            )
            for m in self.parser.findall(text)
        ]
        # 2) регулярка по отчеству: ловит фамилии, которых нет в словаре («Текстовой Арины Олеговны»)
        for m in FULL_NAME_RE.finditer(text):
            if not any(m.start() < c.end and m.end() > c.start for c in found):
                found.append(Candidate(
                    value=" ".join(re.sub(r"\s*\([^)]*\)", "", m.group()).split()).title(),
                    start=m.start(), end=m.end(), confidence=0.85))

        return sorted(found, key=lambda c: c.start)

    def extract(self, text: str) -> list[str]:
        return [candidate.value for candidate in self.extract_candidates(text)]


class DateExtractor:
    def __init__(self):
        self.parser = date_parser()

    def extract_candidates(self, text: str) -> list[Candidate]:
        return [
            Candidate(
                value=text[m.span.start:m.span.stop],
                start=m.span.start,
                end=m.span.stop,
                confidence=0.95,
            )
            for m in self.parser.findall(text)
        ]

    def extract(self, text: str) -> list[str]:
        return [candidate.value for candidate in self.extract_candidates(text)]


class CostExtractor:
    def __init__(self, morph_vocab):
        self.extractor = MoneyExtractor(morph_vocab)

    def extract_candidates(self, text: str) -> list[Candidate]:
        return [
            Candidate(
                value=f"{m.fact.amount} {m.fact.currency}",
                start=m.start,
                end=m.stop,
                confidence=0.90,
            )
            for m in self.extractor(text)
        ]

    def extract(self, text: str) -> list[str]:
        return [candidate.value for candidate in self.extract_candidates(text)]

    def extract_with_spans(self, text: str) -> list[tuple[str, tuple[int, int]]]:
        return [
            (
                f"{m.fact.amount} {m.fact.currency}",
                (m.start, m.stop),
            )
            for m in self.extractor(text)
        ]


class AddressExtractor:
    def __init__(self, morph_vocab):
        self.extractor = AddrExtractor(morph_vocab)

    def street_house_flat(self, chunk: str) -> tuple[str | None, str | None, str | None]:
        """Улица, дом, квартира из куска текста по частям адреса natasha (первая улица, потом её дом и квартира)."""
        street = house = flat = None
        for match in self.extractor(chunk):
            kind, value = match.fact.type, match.fact.value
            if value.lower() in {"жилой", "жилого", "жилым"}:
                continue
            if kind == "улица" and not street:
                street = value
            elif kind == "дом" and street and not house and any(c.isdigit() for c in value):
                house = value
            elif kind == "квартира" and house and not flat and any(c.isdigit() for c in value):
                flat = value
        return street, house, flat


class RegexExtractor:
    pattern: str
    confidence = 0.95

    def extract(self, text: str) -> list[str]:
        return re.findall(self.pattern, text)

    def extract_candidates(self, text: str) -> list[Candidate]:
        return [
            Candidate(
                value=match.group(),
                start=match.start(),
                end=match.end(),
                source="regex",
                confidence=self.confidence,
            )
            for match in re.finditer(self.pattern, text)
        ]


class PassportNumberExtractor(RegexExtractor):
    pattern = PASSPORT_NUMBER_PATTERN


class SnilsNumberExtractor(RegexExtractor):
    pattern = SNILS_NUMBER_PATTERN


class TINExtractor(RegexExtractor):
    pattern = TIN_PATTERN