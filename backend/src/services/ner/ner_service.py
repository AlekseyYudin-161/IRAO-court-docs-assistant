# ner_service.py
from natasha import MorphVocab
from backend.src.utils.text_utils import TextUtils

from .extractors import (
    NameExtractor,
    DateExtractor,
    CostExtractor,
    AddressExtractor,
    PassportNumberExtractor,
    SnilsNumberExtractor,
    TINExtractor
)
from backend.src.dto.ocr_ner import ExtractedEntitiesDTO


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

    def extract_entities(self, ocr_results, file_name: str) -> ExtractedEntitiesDTO:
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
        # Извлечение номера паспорта и снилса
        passport_number = self._passport_number_extractor.extract(combined)
        snils_number = self._snils_number_extractor.extract(combined)
        tin_number = self._tin_extractor.extract(combined)

        # document_type: str = ""
        # file_name: str = ""
        # names: List[str]
        # dates: List[str]
        # passport_number: str = ""
        # snils_number: str = ""
        # money: List[str]
        # addresses: List[str]
        # paragraph_text: str = ""

        return ExtractedEntitiesDTO(
            document_type="",
            file_name=file_name,
            names=names,
            dates=dates,
            passport_number=passport_number,
            snils_number=snils_number,
            tin_number=tin_number,
            money=money,
            addresses=addresses,
            paragraph_text=combined,
        )

    def process_all(self, ocr_results, file_name:str) -> list[ExtractedEntitiesDTO]:
        extracted = self.extract_entities(ocr_results, file_name)
        return [extracted]
