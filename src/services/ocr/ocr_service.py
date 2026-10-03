import asyncio
from pathlib import Path
from typing import Any

import pytesseract

from src.core.config import settings
from src.utils.image_utils import ImageUtils
from src.utils.pdf_utils import PdfUtils


class OcrService:
    def __init__(
        self,
        image_utils: ImageUtils | None = None,
        pdf_utils: PdfUtils | None = None,
    ):
        self._image_utils = image_utils or ImageUtils()
        self._pdf_utils = pdf_utils or PdfUtils()

    async def process_image(
        self,
        file_bytes: bytes,
        filename: str,
    ) -> list[dict[str, Any]]:
        # PDF с текстовым слоем: OCR не нужен
        if Path(filename).suffix.lower() == ".pdf":
            layer = await asyncio.to_thread(
                self._pdf_utils.extract_text_layer, file_bytes
            )
            if self._pdf_utils.has_text_layer(layer):
                return [
                    {"page": n, "recognized_text": t.strip(), "source": "text_layer"}
                    for n, t in enumerate(layer, start=1)
                ]

        images = await asyncio.to_thread(
            self._image_utils.bytes_to_images,
            file_bytes,
            filename,
            dpi=settings.OCR_DPI,
        )

        all_results = []

        for page_num, image in enumerate(images, start=1):
            if await asyncio.to_thread(self._image_utils.is_blank_page, image):
                text = ""  # страницу оставляем в списке, чтобы не сбивалась нумерация
            else:
                image = await asyncio.to_thread(self._image_utils.preprocess_scan, image)
                text = await asyncio.to_thread(
                    pytesseract.image_to_string,
                    image,
                    lang="rus+eng",
                    config="--psm 4",
                )

            all_results.append(
                {
                    "page": page_num,
                    "recognized_text": text.strip(),
                    "source": "ocr",
                }
            )

        return all_results