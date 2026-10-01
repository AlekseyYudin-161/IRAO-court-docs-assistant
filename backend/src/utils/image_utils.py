import io
from pathlib import Path
import cv2
import pypdfium2 as pdfium
import numpy as np
from PIL import Image
from backend.src.core.config import settings


class ImageUtils:
    """Utilities for working with images"""

    @staticmethod
    def enhance_document_image(image, class_name):
        """
        Улучшает качество изображения документа

        Args:
            image: PIL Image объект
            class_name: класс изображения (для определения целевого размера)

        Returns:
            улучшенное бинарное изображение (numpy array)
        """
        img_np = np.array(image)

        # Конвертируем RGB в BGR для OpenCV
        if len(img_np.shape) == 3 and img_np.shape[2] == 3:
            img_cv = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
        else:
            img_cv = img_np

        # Конвертируем в оттенки серого
        if len(img_cv.shape) == 3:
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        else:
            gray = img_cv

        # Применяем адаптивную бинаризацию для лучшего результата
        # Используем метод Оцу для автоматического определения порога
        _, binary = cv2.threshold(
            gray,
            100,  # порог автоматически определяется методом Оцу
            255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU,
        )

        print(f"Улучшено изображение класса {class_name}: размер {binary.shape}")

        return binary

    @staticmethod
    def crop_image(image_input: np.ndarray, bbox_coords):
        """
        Вырезает область изображения по координатам bbox
        Поддерживает:
            - PIL Image
            - numpy.ndarray
        """
        # # Преобразуем numpy array в PIL Image
        if isinstance(image_input, np.ndarray):
            img = Image.fromarray(image_input)
        elif isinstance(image_input, Image.Image):
            img = image_input
        else:
            raise TypeError(f"Unsupported type for crop_image: {type(image_input)}")

        x1, y1, x2, y2 = bbox_coords
        cropped = img.crop((x1, y1, x2, y2))
        return cropped

    @staticmethod
    def bytes_to_images(file_bytes: bytes, filename: str, dpi: settings.OCR_DPI):
        """Конвертирует байты в список PIL Image."""
        ext = Path(filename).suffix.lower()
        if ext == ".pdf":
            images = []
            pdf = pdfium.PdfDocument(file_bytes)
            # Отрисовка страницы
            for page in pdf:
                scale = dpi / 72.0  # вычисляется коэф масштабирования
                bitmap = page.render(scale=scale)  # создается растровое изображение
                pil_image = bitmap.to_pil()  # конверт. в PIL Image
                images.append(pil_image)
            pdf.close()
            return images
        else:
            return [Image.open(io.BytesIO(file_bytes)).convert("RGB")]
