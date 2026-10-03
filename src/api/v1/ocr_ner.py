from fastapi import APIRouter, Depends, UploadFile, File, Form
from dependency_injector.wiring import inject, Provide

from src.core.container import Container
from src.dto.ocr_ner import ProcessDocumentOut
from src.services.document_processing_service import DocumentProcessingService

router = APIRouter(tags=["OCR and NER"])


@router.post("/process", response_model=ProcessDocumentOut)
@inject
async def process_document(
    file: UploadFile = File(..., description="Image or PDF file"),
    document_service: DocumentProcessingService = Depends(
        Provide[Container.document_processing_service]
    ),
):
    return await document_service.process_document(file)
