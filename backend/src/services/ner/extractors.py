import re
import pymorphy2
from natasha import MoneyExtractor, AddrExtractor
from .parsers.date_parser import date_parser
from .parsers.name_parser import name_parser

from .patterns import PASSPORT_NUMBER_PATTERN, SNILS_NUMBER_PATTERN, TIN_PATTERN

class NameExtractor:
    def __init__(self):
        self.parser = name_parser()
        self.morph = pymorphy2.MorphAnalyzer()

    def extract(self, text: str) -> list[str]:
        return [
            " ".join(
                part for part in [m.fact.last, m.fact.first, m.fact.middle] if part
            )
            for m in self.parser.findall(text)
        ]


class DateExtractor:
    def __init__(self):
        self.parser = date_parser()

    def extract(self, text: str) -> list[str]:
        return [text[m.span.start : m.span.stop] for m in self.parser.findall(text)]


class CostExtractor:
    def __init__(self, morph_vocab):
        self.extractor = MoneyExtractor(morph_vocab)

    def extract(self, text: str) -> list[str]:
        return [f"{m.fact.amount} {m.fact.currency}" for m in self.extractor(text)]

    def extract_with_spans(self, text: str) -> list[tuple[str, tuple[int, int]]]:
        return [
            (f"{m.fact.amount} {m.fact.currency}", (m.start, m.stop))
            for m in self.extractor(text)
        ]


class AddressExtractor:
    def __init__(self, morph_vocab):
        self.extractor = AddrExtractor(morph_vocab)

    def extract(
        self, text: str, money_spans: list[tuple[int, int]] = None
    ) -> list[str]:
        money_spans = money_spans or []
        matches = list(self.extractor(text))
        addresses = []
        current_address = []
        last_stop = None

        for m in matches:
            if any(m.start < end and m.stop > start for start, end in money_spans):
                continue
            if m.fact.value in ["Жилой", "Жилого", "Жилым", "жилой", "жилого", "жилым"]:
                continue
            if m.fact.type == "индекс":
                context = text[max(0, m.start - 30) : m.stop + 30].lower()
                if (
                    "паспорт" in context
                    or "n" in context
                    or "№" in context
                    or "00" in context
                ):
                    continue
            if m.fact.type is None:
                continue

            span_text = text[m.start : m.stop]
            if last_stop is None or m.start - last_stop < 20:
                current_address.append(span_text)
            else:
                if current_address:
                    addresses.append(" ".join(current_address))
                current_address = [span_text]
            last_stop = m.stop

        if current_address:
            addresses.append(" ".join(current_address))
        return addresses

class PassportNumberExtractor:
    def extract(self, text: str) -> list[str]:
        return re.findall(PASSPORT_NUMBER_PATTERN, text)

class SnilsNumberExtractor:
    def extract(self, text: str) -> list[str]:
        return re.findall(SNILS_NUMBER_PATTERN, text)

class TINExtractor:
    def extract(self, text: str) -> list[str]:
        return re.findall(TIN_PATTERN, text)
