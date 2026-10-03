import re

from natasha import AddrExtractor, MoneyExtractor

from .parsers.date_parser import date_parser
from .parsers.name_parser import name_parser
from .patterns import PASSPORT_NUMBER_PATTERN, SNILS_NUMBER_PATTERN, TIN_PATTERN
from .rules.models import Candidate


class NameExtractor:
    def __init__(self):
        self.parser = name_parser()

    def extract_candidates(self, text: str) -> list[Candidate]:
        return [
            Candidate(
                value=" ".join(
                    part
                    for part in (m.fact.last, m.fact.first, m.fact.middle)
                    if part
                ),
                start=m.span.start,
                end=m.span.stop,
                confidence=0.90,
            )
            for m in self.parser.findall(text)
        ]

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

    def extract(
        self,
        text: str,
        money_spans: list[tuple[int, int]] | None = None,
    ) -> list[str]:

        money_spans = money_spans or []
        addresses = []
        current = []
        last_stop = None

        for match in self.extractor(text):
            if any(
                match.start < end and match.stop > start
                for start, end in money_spans
            ):
                continue

            if match.fact.value.lower() in {"жилой", "жилого", "жилым"}:
                continue

            if match.fact.type == "индекс":
                context = text[max(0, match.start - 30):match.stop + 30].lower()

                if any(value in context for value in ("паспорт", "n", "№", "00")):
                    continue

            if match.fact.type is None:
                continue

            if last_stop is None or match.start - last_stop < 20:
                current.append(text[match.start:match.stop])
            else:
                if current:
                    addresses.append(" ".join(current))
                current = [text[match.start:match.stop]]

            last_stop = match.stop

        if current:
            addresses.append(" ".join(current))

        return addresses


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