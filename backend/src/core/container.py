from dependency_injector import containers, providers
from backend.src.core.config import settings
from backend.src.utils.image_utils import ImageUtils
from backend.src.utils.text_utils import TextUtils
from backend.src.utils.gpu_utils import GPUUtils

from backend.src.services.ocr.ocr_service import OcrService
from backend.src.services.ner.ner_service import NERService
from backend.src.services.document_processing_service import DocumentProcessingService


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(
        packages=[
            "backend.src.api.v1",
            "backend.src.services",
            "backend.src.services.ocr",
            "backend.src.services.ner",
            "backend.src.utils",
            "backend.src.core",
        ]
    )

    config = providers.Object(settings)

    # Утилиты
    image_utils = providers.Singleton(ImageUtils)
    text_utils = providers.Singleton(TextUtils)
    gpu_utils = providers.Singleton(GPUUtils)


    # Сервисы
    ocr_service = providers.Singleton(
        OcrService,
        image_utils=image_utils,
    )

    ner_service = providers.Singleton(
        NERService,
        text_utils=text_utils,
    )

    document_processing_service = providers.Singleton(
        DocumentProcessingService,
        ocr_service=ocr_service,
        ner_service=ner_service,
    )
