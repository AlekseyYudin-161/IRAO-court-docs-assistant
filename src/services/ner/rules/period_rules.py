import re

from .models import Candidate
from .text_utils import clean_value


PERIOD_PATTERNS = [
    r"""за\s+период.*?с\s+(?P<start>
        \d{1,2}[./-]\d{1,2}[./-]\d{2,4}
        |
        \d{1,2}\s+[а-яА-Я]+\s+\d{4}
    )
    .*?
    по\s+(?P<end>
        \d{1,2}[./-]\d{1,2}[./-]\d{2,4}
        |
        \d{1,2}\s+[а-яА-Я]+\s+\d{4}
    )
    """,

    r"""
    период.*?с\s+
    (?P<start>\d{1,2}[./-]\d{1,2}[./-]\d{2,4})
    .*?
    по\s+
    (?P<end>\d{1,2}[./-]\d{1,2}[./-]\d{2,4})
    """,
]


def extract_period(text: str) -> tuple[Candidate | None, Candidate | None]:

    for pattern in PERIOD_PATTERNS:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE | re.DOTALL | re.VERBOSE,
        )

        if not match:
            continue

        return (
            Candidate(
                value=clean_value(match.group("start")),
                start=match.start("start"),
                end=match.end("start"),
                confidence=0.95,
            ),
            Candidate(
                value=clean_value(match.group("end")),
                start=match.start("end"),
                end=match.end("end"),
                confidence=0.95,
            ),
        )

    return None, None
