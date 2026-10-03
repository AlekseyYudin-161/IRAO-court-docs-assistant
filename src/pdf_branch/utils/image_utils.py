import io
from pathlib import Path

import cv2
import numpy as np
import pypdfium2 as pdfium
from PIL import Image


class ImageUtils:

    def bytes_to_images(self, file_bytes: bytes, filename: str, dpi: int,
                        page_indexes: list[int] | None = None) -> list[Image.Image]:
        if Path(filename).suffix.lower() != ".pdf":
            return [Image.open(io.BytesIO(file_bytes)).convert("RGB")]
        pdf = pdfium.PdfDocument(file_bytes)
        try:
            indexes = range(len(pdf)) if page_indexes is None else page_indexes
            return [pdf[i].render(scale=dpi / 72).to_pil().convert("RGB") for i in indexes]
        finally:
            pdf.close()

    def is_blank_page(self, image: Image.Image) -> bool:
        gray = np.array(image.convert("L"))
        return (gray < 110).mean() < 0.001

    def _deskew_angle(self, gray: np.ndarray) -> float:
        small = cv2.resize(gray, (1000, int(gray.shape[0] * 1000 / gray.shape[1])))
        _, bw = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        h, w = bw.shape

        def sharpness(angle: float) -> float:
            m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
            rotated = cv2.warpAffine(bw, m, (w, h), flags=cv2.INTER_NEAREST)
            return float(np.var(rotated.sum(axis=1, dtype=np.float64)))

        return max(np.arange(-5, 5.5, 0.5), key=sharpness)

    def preprocess_scan(self, image: Image.Image) -> Image.Image:
        gray = np.array(image.convert("L"))
        angle = self._deskew_angle(gray)
        h, w = gray.shape
        m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        gray = cv2.warpAffine(gray, m, (w, h), flags=cv2.INTER_CUBIC,
                              borderMode=cv2.BORDER_CONSTANT, borderValue=255)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return Image.fromarray(binary)