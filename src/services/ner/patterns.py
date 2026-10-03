PASSPORT_NUMBER_PATTERN = (
    r"\b\d{2}\s?\d{2}[ \u00a0]\d{6}\b"
)
SNILS_NUMBER_PATTERN = (
    r"\b\d{3}-\d{3}-\d{3}[\s-]\d{2}\b"
)
TIN_PATTERN = (
    r"ИНН[\s:№]*(\d{12}|\d{10})\b"
)