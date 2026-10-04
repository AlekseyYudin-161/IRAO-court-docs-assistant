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

    ENABLE_LLM_VALIDATION: bool = False
    OLLAMA_URL: str = "http://localhost:11434/api/chat"
    OLLAMA_MODEL: str = "qwen3:8b"
    OLLAMA_TIMEOUT: int = 300
    OLLAMA_SYSTEM_PROMPT: str = """Ты — строгий валидатор извлечения данных из судебных документов.
        Тебе дают:
        1) Фрагмент исходного текста документа (OCR).
        2) JSON с извлечёнными полями.
        
        Твоя задача — проверить КАЖДОЕ поле и вернуть ТОЛЬКО JSON-массив объектов
        вида {"field": "<имя>", "ok": true|false, "reason": "<кратко>"}.
        
        Правила:
        - Если значение поля соответствует тексту — ok=true, reason="".
        - Если значение null, но в тексте есть подходящее значение — ok=false, reason="пропущено: <что>".
        - Если значение не null и есть в тексте — ok=true.
        - Если значение не null и НЕ подтверждается текстом — ok=false, reason="не найдено в тексте".
        - Для co_debtors и co_debtors_count: co_debtors_count должен равняться len(co_debtors).
        - Не выдумывай поля. Проверяй только те, что перечислены.
        - Никаких пояснений вне JSON. Только JSON-массив.
    """


    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True
    )


settings = Settings()
