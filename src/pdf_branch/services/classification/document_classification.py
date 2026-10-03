import re
from dataclasses import dataclass
from enum import Enum

from .patterns import *

class DocumentClass(str, Enum):
    FSSP_RESOLUTION = "fssp_resolution" #класс документов ФССП
    WRIT_OF_EXECUTION = "writ_of_execution" #класс документов для исполнительных листов
    COURT_ORDER = "court_order" # для судебных приказов
    UNKNOWN = "unknown"


class SourceKind(str, Enum):
    TEXT_LAYER = "text_layer"  # есть встроенный текст, OCR не нужен
    ELECTRONIC_IMAGE = "electronic_image"  # электронный документ, но без слоя
    SCAN = "scan"  # скан


@dataclass(frozen=True)
class Classification:
    doc_class: DocumentClass
    source_kind: SourceKind


TITLE_PATTERNS: dict[DocumentClass, re.Pattern] = {
    DocumentClass.FSSP_RESOLUTION: FSSP_PATTERN,
    DocumentClass.WRIT_OF_EXECUTION: WRIT_OF_EXECUTION_PATTERN,
    DocumentClass.COURT_ORDER: COURT_ORDER_PATTERN,
}


def normalize(text: str) -> str:
    text = text.lower().replace("ё", "е")
    return re.sub(r"\s+", " ", text).strip()


class DocumentClassifier:

    def classify(self, first_page_text: str, has_text_layer: bool) -> Classification:
        norm = normalize(first_page_text)
        doc_class, reason = self._detect_class(norm)
        source_kind = self._detect_source_kind(first_page_text, has_text_layer)
        return Classification(doc_class, source_kind)

    @staticmethod
    def _earliest(text: str):
        hits = []
        for cls, pattern in TITLE_PATTERNS.items():
            match = pattern.search(text)
            if match:
                hits.append((match.start(), cls))
        return min(hits, key=lambda h: h[0]) if hits else None

    def _detect_class(self, norm: str) -> tuple[DocumentClass, str]:
        hit = self._earliest(norm)
        if hit:
            pos, cls = hit
            return cls, f"title@{pos}:{cls.value}"

        return DocumentClass.UNKNOWN, "no_markers"

    @staticmethod
    def _detect_source_kind(raw: str, has_text_layer: bool) -> SourceKind:
        if has_text_layer:
            return SourceKind.TEXT_LAYER
        if any(p.search(raw) for p in ELECTRONIC_PATTERNS):
            return SourceKind.ELECTRONIC_IMAGE
        return SourceKind.SCAN
