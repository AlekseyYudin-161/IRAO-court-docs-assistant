import re

from .text_utils import window_after

STREET_WITH_TYPE = False   # True -> "ул. Садовая", False -> "Садовая"

_TYPES = (r"ул(?:ица)?|проспект|пр-т|пер(?:еулок)?|шоссе|наб(?:ережная)?|пл(?:ощадь)?|"
          r"бульвар|бул|проезд|тупик|аллея")

# тип улицы, потом название до запятой / «д.» / «кв» / номера дома
STREET_RE = re.compile(
    rf"(?<![а-яё])(?P<type>{_TYPES})(?:\.\s*|\s+)(?P<name>[^\n,;]{{2,60}}?)"
    r"(?=\s*[,;\n]|\s+д(?:ом)?\.?\s*\d|\s+кв|\s+\d|\s*$)",
    re.IGNORECASE,
)
FLAT_RE = re.compile(r"(?<![а-яё])(?:кв(?:артира|-ра)?|ком(?:ната)?)\.?\s*(?P<f>\d[\w/\-]*)", re.IGNORECASE)
HOUSE_RE = re.compile(
    r"[\s,]*(?:д(?:ом)?\.?\s*)?(?P<h>\d+(?:\s?(?-i:[А-ЯA-Z])(?![а-яёА-ЯA-Z]))?(?:[/\-]\d+)?)",
    re.IGNORECASE,
)

def extract_address(chunk: str) -> tuple[str | None, str | None, str | None]:
    street = STREET_RE.search(chunk)
    if not street:
        return None, None, None
    name = " ".join(street["name"].split()).strip(" .")
    if STREET_WITH_TYPE:
        name = f"{street['type'].lower()}. {name}"

    rest = chunk[street.end():street.end() + 80]
    h, f = HOUSE_RE.match(rest), FLAT_RE.search(rest)
    house = h["h"].strip("-/") if h else None
    flat = f["f"].strip("-/") if f else None
    if house and not flat and (dm := re.fullmatch(r"(\d+)-(\d+)", house)):   # «128-16» → дом 128, кв 16
        house, flat = dm.group(1), dm.group(2)
    return name, house, flat