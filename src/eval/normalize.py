"""Нормализация значений перед сравнением с разметкой (карточка D, шаг 3).

strict — то, что заказчик видит как «то же значение»: 4000 == 4000.0 == «4 000,00 руб.»,
         «11 ноября 2025 г.» == 2025-11-11, регистр/ё/пробелы не важны.
loose  — дополнительно прощает формат адреса, падеж ФИО и хвостовую пунктуацию номеров.
Пусто == пусто — совпадение; «0» против пусто — ошибка (README оргов: пусто ≠ 0).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

# --- типы столбцов (имена — как в templates/ оргов, включая «отчетство») -----------------
MONEY = {"дз_осн", "дз_пени", "дз_пошлина", "IdDebtSum", "rub_deb", "rub_peni", "rub_poshlina", "rub_post"}
DATES = {"дата рождения", "дело_дата", "период_дз_начало", "период_дз_оконч",
         "DocDate", "IdDocDate", "IdDeloDate", "date_start", "date_end"}
INTS = {"соответчики_кол-во", "DebtorType", "IdType"}
IDS = {"паспорт", "снилс", "инн", "дело_номер", "IdDocNo", "IdDeloNo", "IpNo", "дом", "кв"}
PERSON = {"фамилия", "имя", "отчетство", "фио", "DbtrName"}
PERSON_LIST = {"соответчики_фио"}
ADDRESS = {"улица", "street", "DbtrAdr"}

# Ключевые реквизиты, по которым орги проверяют закрытую выборку (ответ бота 29.09)
KEY_GROUPS = {
    "суммы": ["дз_осн", "дз_пени", "дз_пошлина", "IdDebtSum", "rub_deb", "rub_peni", "rub_poshlina", "rub_post"],
    "даты": ["дело_дата", "период_дз_начало", "период_дз_оконч", "DocDate", "IdDocDate", "IdDeloDate",
             "date_start", "date_end"],
    "ФИО": ["фио", "DbtrName", "соответчики_фио"],
    "номера": ["дело_номер", "IdDeloNo", "IdDocNo", "IpNo"],
}
KEY_COLUMNS = {c for cols in KEY_GROUPS.values() for c in cols}

# Не участвуют в macro: ключ строки и столбцы, которые в наборе всегда пусты
KEY_FIELDS = {"Файл", "FileName"}
OUT_OF_MACRO = {"снилс"}

MONTHS = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6, "июл": 7,
          "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12}
# латиница, похожая на кириллицу (частая ошибка OCR в номерах «-ИП», «№»)
HOMO = str.maketrans("ABCEHKMOPTXaceopxy", "АВСЕНКМОРТХасеорху")


def kind(col: str) -> str:
    for name, group in (("money", MONEY), ("date", DATES), ("int", INTS), ("id", IDS),
                        ("person", PERSON), ("person_list", PERSON_LIST), ("address", ADDRESS)):
        if col in group:
            return name
    return "text"


def _text(v: str) -> str:
    v = unicodedata.normalize("NFKC", str(v)).replace("\u00a0", " ")
    v = v.casefold().replace("ё", "е")
    return re.sub(r"\s+", " ", v).strip()


def norm_money(v: str) -> str:
    s = _text(v)
    if not s:
        return ""
    s = re.sub(r"(руб(лей|ля|ль)?\.?|₽|коп\.?)", "", s)
    s = s.replace(" ", "").replace(",", ".")
    s = re.sub(r"\.(?=.*\.)", "", s)           # «1.234.56» → «1234.56»: точка-разделитель тысяч
    try:
        return str(Decimal(s).quantize(Decimal("0.01")))
    except InvalidOperation:
        return s


def norm_date(v: str) -> str:
    s = _text(v)
    if not s:
        return ""
    if m := re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ t].*)?", s):      # ISO, в т.ч. «2025-11-11 00:00:00»
        y, mo, d = map(int, m.groups())
    elif m := re.fullmatch(r"(\d{1,2})[./](\d{1,2})[./](\d{4})(?:\s*г\.?)?", s):
        d, mo, y = map(int, m.groups())
    elif m := re.fullmatch(r"«?(\d{1,2})»?\s+([а-я]+)\s+(\d{4})(?:\s*(г\.?|года))?", s):
        d, word, y = int(m[1]), m[2], int(m[3])
        mo = next((n for stem, n in sorted(MONTHS.items(), key=lambda x: -len(x[0])) if word.startswith(stem)), 0)
    else:
        return s
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return s


def norm_int(v: str) -> str:
    s = _text(v)
    if not s:
        return ""
    try:
        return str(int(Decimal(s.replace(",", "."))))
    except InvalidOperation:
        return s


def norm_id(v: str, loose: bool = False) -> str:
    s = _text(v).upper().replace(" ", "")
    s = re.sub(r"^№", "", s)
    if loose:
        s = s.translate(HOMO).rstrip(".,;:")
    return s


_ADDR_TYPES = r"\b(г|город|ул|улица|пр|пр-кт|просп|проспект|пер|переулок|б-р|бульвар|ш|шоссе|пл|площадь|наб|набережная|д|дом|кв|квартира|с|стр|к|корп|корпус)\b\.?"


def norm_address_loose(v: str) -> str:
    s = _text(v)
    s = re.sub(_ADDR_TYPES, " ", s)
    s = re.sub(r"[^\w\s/-]", " ", s)
    s = re.sub(r"(\d+)-?(я|й|ая|ий|ой)\b", r"\1", s)       # «5-я» ≡ «5»
    return " ".join(sorted(s.split()))                       # «22 Пробная» ≡ «Пробная 22»


def _stems(name: str) -> list[str]:
    name = re.sub(r"\(.*?\)", " ", _text(name))
    return [w[:4] for w in re.findall(r"[а-яa-z]+", name)]


def norm_person(v: str, loose: bool = False) -> str:
    return " ".join(_stems(v)) if loose else _text(v)


def norm_person_list(v: str, loose: bool = False) -> str:
    s = _text(v)
    if not s:
        return ""
    names = [n.strip() for n in re.split(r",|;", s) if n.strip()]
    return " | ".join(sorted(norm_person(n, loose) for n in names))   # мультимножество: порядок не важен


def normalize(col: str, v, loose: bool = False) -> str:
    if v is None:
        return ""
    v = str(v)
    k = kind(col)
    if k == "money":
        return norm_money(v)
    if k == "date":
        return norm_date(v)
    if k == "int":
        return norm_int(v)
    if k == "id":
        return norm_id(v, loose)
    if k == "person":
        return norm_person(v, loose)
    if k == "person_list":
        return norm_person_list(v, loose)
    if k == "address" and loose:
        return norm_address_loose(v)
    s = _text(v)
    return re.sub(r"[\s.,;:]+$", "", s) if loose else s


def equal(col: str, pred, gold, loose: bool = False) -> bool:
    return normalize(col, pred, loose) == normalize(col, gold, loose)
