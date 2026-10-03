from dependency_injector import containers, providers
from src.core.config import settings
from src.utils.image_utils import ImageUtils
from src.utils.text_utils import TextUtils
from src.utils.pdf_utils import PdfUtils

from src.services.ocr.ocr_service import OcrService
from src.services.ner.ner_service import NERService
from src.services.document_processing_service import DocumentProcessingService
from src.services.classification.document_classification import DocumentClassifier
from src.services.validation.extraction_validator import ExtractionValidator


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(
        packages=[
            "src.api.v1",
            "src.services",
            "src.services.ocr",
            "src.services.ner",
            "src.utils",
            "src.core",
        ]
    )

    config = providers.Object(settings)

    # Утилиты
    image_utils = providers.Singleton(ImageUtils)
    text_utils = providers.Singleton(TextUtils)
    pdf_utils = providers.Singleton(PdfUtils)

    document_classifier = providers.Singleton(DocumentClassifier)
    extraction_validator = providers.Singleton(ExtractionValidator)

    # Сервисы
    ocr_service = providers.Singleton(
        OcrService,
        image_utils=image_utils,
        pdf_utils=pdf_utils,
    )

    ner_service = providers.Singleton(
        NERService,
        text_utils=text_utils,
    )

    document_processing_service = providers.Singleton(
        DocumentProcessingService,
        ocr_service=ocr_service,
        ner_service=ner_service,
        classifier=document_classifier,
        validator=extraction_validator,
    )