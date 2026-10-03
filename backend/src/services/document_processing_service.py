import asyncio
import logging
import time
import json
from pathlib import Path

from fastapi import HTTPException, UploadFile

from backend.src.core.config import settings
from backend.src.dto.ocr_ner import ProcessDocumentOut
from backend.src.services.classification.document_classification import DocumentClassifier
from backend.src.services.ner.ner_service import NERService
from backend.src.services.ocr.ocr_service import OcrService
from backend.src.services.validation.extraction_validator import ExtractionValidator

logger = logging.getLogger(__name__)


class DocumentProcessingService:
    """Service for processing documents with OCR and NER"""

    def __init__(
        self,
        ocr_service: OcrService,
        ner_service: NERService,
        classifier: DocumentClassifier,
        validator: ExtractionValidator | None = None,
    ) -> None:
        self._ocr_service = ocr_service
        self._ner_service = ner_service
        self._classifier = classifier
        self._validator = validator
        self._log = logging.getLogger(__name__)

    def _validate_file(self, filename: str) -> None:
        ext = Path(filename).suffix.lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"Unsupported file type: {ext}")

    def _enrich_results(self, processed: list) -> None:
        """Дополняет rule_extraction через LLM и заменяет его в DTO."""
        for item in processed:
            if item.rule_extraction is None:
                continue

            item.rule_extraction = self._validator.enrich(
                text=item.paragraph_text,
                extraction=item.rule_extraction,
            )

    async def process_document(self, file: UploadFile) -> ProcessDocumentOut:
        total_start = time.time()

        self._validate_file(file.filename)

        try:
            contents = await file.read()

            # --- OCR ---
            ocr_start = time.time()
            ocr_results = await self._ocr_service.process_image(
                file_bytes=contents,
                filename=file.filename,
            )
            ocr_time = time.time() - ocr_start

            # --- Классификация ---
            first = ocr_results[0]
            classification = self._classifier.classify(
                first["recognized_text"],
                first["source"] == "text_layer",
            )
            self._log.info(
                "Classified: %s | source=%s",
                classification.doc_class.value,
                classification.source_kind.value,
            )

            # --- NER ---
            ner_start = time.time()
            processed = await asyncio.to_thread(
                self._ner_service.process_all,
                ocr_results,
                file.filename,
                classification.doc_class.value,
            )
            for item in processed:
                self._log.info(
                    "rule_extraction (before validation):\n%s",
                    json.dumps(item.rule_extraction.model_dump(), ensure_ascii=False, indent=2),
                )
            ner_time = time.time() - ner_start

            # --- LLM-валидация (опционально) ---
            validation_time = 0.0
            if settings.ENABLE_LLM_VALIDATION and self._validator:
                val_start = time.time()
                await asyncio.to_thread(self._enrich_results, processed)
                validation_time = time.time() - val_start

            total_time = time.time() - total_start

            self._log.info(
                "Document processed: OCR=%.2f s | NER=%.2f s | VAL=%.2f s | TOTAL=%.2f s | pages=%d",
                ocr_time, ner_time, validation_time, total_time, len(ocr_results),
            )
            return ProcessDocumentOut(success=True, processed_results=processed)

        except Exception as e:
            logger.exception(f"Document processing failed for {file.filename}")
            raise HTTPException(400, detail=str(e))

    def _validate_results(self, processed: list) -> None:
        """Прогоняет каждый результат через LLM-валидатор и пишет issues в DTO."""
        for item in processed:
            if item.rule_extraction is None:
                continue

            issues = self._validator.validate(
                text=item.paragraph_text,
                extraction=item.rule_extraction,
            )
            item.validation = issues