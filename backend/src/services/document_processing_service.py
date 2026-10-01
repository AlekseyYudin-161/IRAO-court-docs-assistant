import time
import logging
from pathlib import Path
from typing import List

from fastapi import HTTPException, UploadFile

from backend.src.dto.ocr_ner import (
    ProcessDocumentOut,
    ExtractedEntitiesDTO
)
from backend.src.core.config import settings
from backend.src.services.ocr.ocr_service import OcrService
from backend.src.services.ner.ner_service import NERService

logger = logging.getLogger(__name__)


class DocumentProcessingService:
    """Service for processing documents with OCR and NER"""

    def __init__(
        self,
        ocr_service: OcrService,
        ner_service: NERService,
    ) -> None:
        self._ocr_service = ocr_service
        self._ner_service = ner_service
        self._log = logging.getLogger(__name__)

    def _validate_file(self, filename: str) -> None:
        """Validate file extension"""
        ext = Path(filename).suffix.lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"Unsupported file type: {ext}")

    async def process_document(
        self, file: UploadFile
    ) -> ProcessDocumentOut:
        """
        Process a document with OCR and NER
        """
        total_start = time.time()

        #  Валидация файла
        self._validate_file(file.filename)

        try:
            # Чтение
            contents = await file.read()

            # OCR
            ocr_start = time.time()
            ocr_results = await self._ocr_service.process_image(
                file_bytes=contents,
                filename=file.filename,
            )

            ocr_time = time.time() - ocr_start
            # NER
            ner_start = time.time()

            # Запуск пайплайна
            processed: List[ExtractedEntitiesDTO] = self._ner_service.process_all(
                ocr_results,
                file.filename,
            )

            ner_time = time.time() - ner_start

            total_time = time.time() - total_start

            processed_dtos = [
                ExtractedEntitiesDTO.model_validate(item) for item in processed
            ]
            print(
                f"Document processed: OCR={ocr_time:2f} s | NER={ner_time:2f} s | TOTAL_TIME={total_time:2f} s | Num of parapgraphs={len(ocr_results)}d",
            )
            return ProcessDocumentOut(
                success=True,
                processed_results=processed_dtos,
            )

        except Exception as e:
            logger.exception(f"Document processing failed for {file.filename}")
            raise HTTPException(400, detail=str(e))
