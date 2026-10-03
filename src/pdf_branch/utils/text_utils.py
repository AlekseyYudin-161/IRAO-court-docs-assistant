import re


class TextUtils:
    @staticmethod
    def normalize_text(text: str) -> str:
        # Удаление лишних пробелов, мусорных символов
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"I", "1", text).strip()
        text = re.sub(r"''", '"', text).strip()
        text = re.sub(r"\n", " ", text).strip()
        text = re.sub(r"\?", "7", text).strip()
        text = re.sub(r"\\!", "1", text).strip()
        text = re.sub(r"\\", "", text).strip()
        text = re.sub(r"\\", "", text).strip()
        text = re.sub(
            r"(?<![а-яА-Яa-zA-Z])[\d\sО]+(?![а-яА-Яa-zA-Z])",
            lambda m: m.group(0).replace("О", "0"),
            text,
        )

        return text
