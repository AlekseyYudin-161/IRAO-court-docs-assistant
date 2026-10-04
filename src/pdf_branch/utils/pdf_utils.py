import pypdfium2 as pdfium

from src.pdf_branch.core.config import settings


class PdfUtils:
    """Работа с текстовым слоем PDF (без OCR)."""

    @staticmethod
    def extract_text_layer(file_bytes: bytes) -> list[str]:
        """Текст каждой страницы из встроенного слоя. Пустая строка, если слоя нет."""
        pdf = pdfium.PdfDocument(file_bytes)
        try:
            pages: list[str] = []
            for page in pdf:
                textpage = page.get_textpage()
                try:
                    pages.append(textpage.get_text_range() or "")
                finally:
                    textpage.close()
                    page.close()
            return pages
        finally:
            pdf.close()

    @staticmethod
    def has_text_layer(pages: list[str]) -> bool:
        """Слой считаем настоящим, если в нём достаточно символов.

        Чистый скан даёт 0, ФССП-постановление — от ~200, электронный ИЛ — ~2600.
        """
        total = sum(len(p.strip()) for p in pages)
        return total >= settings.TEXT_LAYER_MIN_CHARS