import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile

from src.pdf_branch.core.config import settings
from src.pdf_branch.dto.ocr_ner import ProcessDocumentOut
from src.pdf_branch.services.classification.document_classification import Classification, DocumentClassifier
from src.pdf_branch.services.ner.ner_service import NERService
from src.pdf_branch.services.ocr.ocr_service import OcrService

logger = logging.getLogger(__name__)


@dataclass
class Analysis:
    ocr: list[dict]
    classification: Classification
    processed: list
    timings_ms: dict[str, int]


class DocumentProcessingService:
    """OCR + классификация + правила (NER). LLM здесь нет: он вызывается через src.llm.client."""

    def __init__(
        self,
        ocr_service: OcrService,
        ner_service: NERService,
        classifier: DocumentClassifier,
    ) -> None:
        self._ocr_service = ocr_service
        self._ner_service = ner_service
        self._classifier = classifier

    def _validate_file(self, filename: str) -> None:
        ext = Path(filename).suffix.lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"Unsupported file type: {ext}")

    async def analyze(self, contents: bytes, filename: str) -> Analysis:
        self._validate_file(filename)

        t0 = time.perf_counter()
        ocr = await self._ocr_service.process_image(file_bytes=contents, filename=filename)
        if not ocr:
            raise ValueError(f"Не удалось получить страницы из {filename}")
        t1 = time.perf_counter()

        first = ocr[0]
        cls = self._classifier.classify(first["recognized_text"], first["source"] == "text_layer")
        logger.info("Classified: %s | source=%s", cls.doc_class.value, cls.source_kind.value)

        processed = await asyncio.to_thread(
            self._ner_service.process_all, ocr, filename, cls.doc_class.value
        )
        t2 = time.perf_counter()

        timings = {"ocr": int((t1 - t0) * 1000), "ner": int((t2 - t1) * 1000)}
        logger.info("Processed %s: OCR=%d ms | NER=%d ms | pages=%d",
                    filename, timings["ocr"], timings["ner"], len(ocr))
        return Analysis(ocr, cls, processed, timings)

    async def process_document(self, file: UploadFile) -> ProcessDocumentOut:
        try:
            a = await self.analyze(await file.read(), file.filename)
            return ProcessDocumentOut(success=True, processed_results=a.processed)
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Document processing failed for %s", file.filename)
            raise HTTPException(400, detail=str(e))