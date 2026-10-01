import asyncio
from typing import Any

import pytesseract

from backend.src.core.config import settings
from backend.src.utils.image_utils import ImageUtils


class OcrService:
    def __init__(self, image_utils: ImageUtils | None = None):
        self._image_utils = image_utils or ImageUtils()

    async def process_image(
        self,
        file_bytes: bytes,
        filename: str,
    ) -> list[dict[str, Any]]:
        images = await asyncio.to_thread(
            self._image_utils.bytes_to_images,
            file_bytes,
            filename,
            dpi=settings.OCR_DPI,
        )

        all_results = []

        for page_num, image in enumerate(images, start=1):
            text = await asyncio.to_thread(
                pytesseract.image_to_string,
                image,
                lang="rus+eng",
                config="--psm 3",
            )

            all_results.append(
                {
                    "page": page_num,
                    "recognized_text": text.strip(),
                }
            )

        return all_results