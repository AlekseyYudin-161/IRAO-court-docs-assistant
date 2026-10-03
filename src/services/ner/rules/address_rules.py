import re

from .models import Candidate


ADDRESS_PATTERNS = [
    r"адрес\s+должника",
    r"адрес\s+места\s+жительства",
    r"место\s+жительства",
    r"проживающ(?:его|ая)\s+по\s+адресу",
    r"зарегистрирован(?:ного|ная)\s+по\s+адресу",
]

FLAT_PATTERN = (
    r"(?:кв(?:артира)?\.?|кв-ра)\s*"
    r"(?P<flat>\d+[А-Яа-яA-Za-z]?)"
)

HOUSE_PATTERN = (
    r"д(?:ом)?\.?\s*"
    r"(?P<house>\d+[А-Яа-яA-Za-z]?)"
)

STREET_PATTERN = r"""
    (?P<street>
        (?:ул\.?|улица|проспект|пр-т|переулок|пер\.?|шоссе|
        наб\.?|набережная|площадь|пл\.?|бульвар|бул\.?)
        \s+
        [А-Яа-яA-Za-z0-9 .-]+?
    )
    (?=\s+д(?:ом)?\.?|\s+кв(?:артира)?\.?|,|$)
"""


def extract_debtor_address(
    text: str,
    addresses: list[Candidate],
) -> Candidate | None:

    for pattern in ADDRESS_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            address = next(
                (
                    address
                    for address in addresses
                    if 0 <= address.start - match.end() <= 150
                ),
                None,
            )

            if address:
                return address

    return None


def split_address(
    address: str,
) -> tuple[str | None, str | None, str | None]:

    if not address:
        return None, None, None

    flat_match = re.search(
        FLAT_PATTERN,
        address,
        re.IGNORECASE,
    )

    house_match = re.search(
        HOUSE_PATTERN,
        address,
        re.IGNORECASE,
    )

    street_match = re.search(
        STREET_PATTERN,
        address,
        re.IGNORECASE | re.VERBOSE,
    )

    return (
        street_match.group("street").strip() if street_match else None,
        house_match.group("house") if house_match else None,
        flat_match.group("flat") if flat_match else None,
    )