import re


FSSP_PATTERN = re.compile(
    r"\bпостановлени[ея]\s+"
    r"(?:о|об)\s+"
    r"(?:возбуждении|прекращении|окончании|"
    r"приостановлении|отмене|взыскании|наложении)"
    r"(?:\s+исполнительного\s+производства)?\b"
)

WRIT_OF_EXECUTION_PATTERN = re.compile(
    r"\bисполнительный\s+лист\b"
)

COURT_ORDER_PATTERN = re.compile(
    r"\bсудебный\s+приказ\b"
)

ELECTRONIC_PATTERNS = [
    re.compile(r"Page\s+1\s+of\s+1"),
    re.compile(r"\bЭкз\."),
    re.compile(r"\d{2}[A-Z]{2}\d{4}#[\d\-]+/\d{4}#\d"),
]