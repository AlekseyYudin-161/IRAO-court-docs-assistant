import re


def normalize_spaces(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_for_rules(text: str) -> str:
    text = text.replace("\xa0", " ")

    # OCR часто даёт разные варианты кавычек
    text = text.replace("«", '"')
    text = text.replace("»", '"')
    text = text.replace("“", '"')
    text = text.replace("”", '"')

    # длинные тире
    text = text.replace("—", "-")
    text = text.replace("–", "-")

    text = re.sub(r"[ \t]+", " ", text)

    return text


def clean_value(value: str) -> str:
    value = value.strip()
    value = re.sub(r"\s+", " ", value)
    return value


def overlap(
    start1: int,
    end1: int,
    start2: int,
    end2: int,
) -> bool:
    return start1 < end2 and end1 > start2


def find_first_pattern(
    text: str,
    patterns: list[str],
    flags: int = re.IGNORECASE | re.MULTILINE,
):
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return match

    return None


def context(
    text: str,
    start: int,
    end: int,
    before: int = 150,
    after: int = 150,
) -> str:
    return text[
        max(0, start - before):
        min(len(text), end + after)
    ]