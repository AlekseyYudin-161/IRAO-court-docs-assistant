import asyncio
import logging
import time
from pathlib import Path

from fastapi import HTTPException, UploadFile

from backend.src.core.config import settings
from backend.src.dto.ocr_ner import ProcessDocumentOut
from backend.src.services.classification.document_classification import DocumentClassifier
from backend.src.services.ner.ner_service import NERService
from backend.src.services.ocr.ocr_service import OcrService

logger = logging.getLogger(__name__)


class DocumentProcessingService:
    """Service for processing documents with OCR and NER"""

    def __init__(
        self,
        ocr_service: OcrService,
        ner_service: NERService,
        classifier: DocumentClassifier,
    ) -> None:
        self._ocr_service = ocr_service
        self._ner_service = ner_service
        self._classifier = classifier
        self._log = logging.getLogger(__name__)

    def _validate_file(self, filename: str) -> None:
        """Validate file extension"""
        ext = Path(filename).suffix.lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"Unsupported file type: {ext}")

    async def process_document(self, file: UploadFile) -> ProcessDocumentOut:
        """Process a document with OCR and NER"""
        total_start = time.time()

        self._validate_file(file.filename)

        try:
            contents = await file.read()

            # OCR (текстовый слой или распознавание)
            ocr_start = time.time()
            ocr_results = await self._ocr_service.process_image(
                file_bytes=contents,
                filename=file.filename,
            )
            ocr_time = time.time() - ocr_start

            # Классификация по первой странице
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

            # NER
            ner_start = time.time()
            processed = await asyncio.to_thread(
                self._ner_service.process_all,
                ocr_results,
                file.filename,
                classification.doc_class.value,
            )
            ner_time = time.time() - ner_start
            total_time = time.time() - total_start

            self._log.info(
                "Document processed: OCR=%.2f s | NER=%.2f s | TOTAL=%.2f s | pages=%d",
                ocr_time, ner_time, total_time, len(ocr_results),
            )
            return ProcessDocumentOut(success=True, processed_results=processed)

        except Exception as e:
            logger.exception(f"Document processing failed for {file.filename}")
            raise HTTPException(400, detail=str(e))