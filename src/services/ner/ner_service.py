# ner_service.py
from natasha import MorphVocab
from src.utils.text_utils import TextUtils

from .extractors import (
    NameExtractor,
    DateExtractor,
    CostExtractor,
    AddressExtractor,
    PassportNumberExtractor,
    SnilsNumberExtractor,
    TINExtractor
)
from src.dto.ocr_ner import ExtractedEntitiesDTO

from .rules.rule_resolver import RuleResolver


class NERService:
    def __init__(self, text_utils: TextUtils) -> None:
        self._morph_vocab = MorphVocab()
        self._text_utils = text_utils
        self._name_extractor = NameExtractor()
        self._date_extractor = DateExtractor()
        self._money_extractor = CostExtractor(self._morph_vocab)
        self._address_extractor = AddressExtractor(self._morph_vocab)
        self._passport_number_extractor = PassportNumberExtractor()
        self._snils_number_extractor = SnilsNumberExtractor()
        self._tin_extractor = TINExtractor()
        self._rule_resolver = RuleResolver(
            name_extractor=self._name_extractor,
            date_extractor=self._date_extractor,
            money_extractor=self._money_extractor,
            address_extractor=self._address_extractor,
            passport_extractor=self._passport_number_extractor,
            snils_extractor=self._snils_number_extractor,
            tin_extractor=self._tin_extractor,
        )

    def extract_entities(self, ocr_results, file_name: str,document_type: str = "") -> ExtractedEntitiesDTO:
        #  Удаление типичных ошибок и соединение вычлененных текстов
        normalized_group = [
            self._text_utils.normalize_text(item["recognized_text"])
            for item in ocr_results
            if item.get("recognized_text")
        ]
        combined = "\n".join(normalized_group)

        # Вычленение имен и дат
        names = self._name_extractor.extract(combined)
        dates = self._date_extractor.extract(combined)

        # Извлечение стоимости объектов
        money_with_spans = self._money_extractor.extract_with_spans(combined)
        money = [m for m, _ in money_with_spans]
        money_spans = [span for _, span in money_with_spans]

        addresses = self._address_extractor.extract(combined, money_spans=money_spans)
        # # Извлечение номера паспорта и снилса
        # passport_number = self._passport_number_extractor.extract(combined)
        # snils_number = self._snils_number_extractor.extract(combined)
        # tin_number = self._tin_extractor.extract(combined)
        rule_extraction = self._rule_resolver.resolve(combined)

        return ExtractedEntitiesDTO(
            document_type=document_type,
            file_name=file_name,
            # names=names,
            # dates=dates,
            # passport_number=passport_number,
            # snils_number=snils_number,
            # tin_number=tin_number,
            # money=money,
            # addresses=addresses,
            paragraph_text=combined,
            rule_extraction=rule_extraction,
        )

    def process_all(self, ocr_results, file_name: str, document_type: str = "") -> list[ExtractedEntitiesDTO]:
        extracted = self.extract_entities(ocr_results, file_name, document_type)
        return [extracted]
