from dependency_injector import containers, providers
from src.pdf_branch.core.config import settings
from src.pdf_branch.utils.image_utils import ImageUtils
from src.pdf_branch.utils.text_utils import TextUtils
from src.pdf_branch.utils.pdf_utils import PdfUtils

from src.pdf_branch.services.ocr.ocr_service import OcrService
from src.pdf_branch.services.ner.ner_service import NERService
from src.pdf_branch.services.document_processing_service import DocumentProcessingService
from src.pdf_branch.services.classification.document_classification import DocumentClassifier


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(
        packages=[
            "src.pdf_branch.api.v1",
            "src.pdf_branch.services",
            "src.pdf_branch.services.ocr",
            "src.pdf_branch.services.ner",
            "src.pdf_branch.utils",
            "src.pdf_branch.core",
        ]
    )

    config = providers.Object(settings)

    # Утилиты
    image_utils = providers.Singleton(ImageUtils)
    text_utils = providers.Singleton(TextUtils)
    pdf_utils = providers.Singleton(PdfUtils)

    document_classifier = providers.Singleton(DocumentClassifier)

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
    )