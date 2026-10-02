import os

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

load_dotenv()



class Settings(BaseModel):
    app_name: str = "court-docs-helper"
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    device: str = os.getenv("DEVICE", "gpu")

    # API
    api_prefix: str = os.getenv("API_PREFIX", "/api/v1")
    title: str = "Court Docs Helper API"
    description: str = "API for OCR document processing"
    version: str = "1.0.0"

    CONF_THRESHOLD: float = float(os.getenv("CONF_THRESHOLD", 0.25))
    OCR_DPI: int = int(os.getenv("OCR_DPI", 400))

    ALLOWED_EXTENSIONS: frozenset[str] = frozenset({
        ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".pdf"
    })

    TEXT_LAYER_MIN_CHARS: int = int(os.getenv("TEXT_LAYER_MIN_CHARS", 100))

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True
    )


settings = Settings()
