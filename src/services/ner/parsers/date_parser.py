from yargy import Parser, rule, and_, or_
from yargy.interpretation import fact
from yargy.predicates import in_caseless, eq, gte, lte
from yargy.predicates import type as T


def date_parser():
    Date = fact("Date", ["day", "month", "year"])

    MONTHS = {
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря",
    }
    INT = T("INT")

    QUOTE = or_(eq("«"), eq("»"), eq('"'))

    DATE_RULE_TEXT = rule(
        QUOTE.optional(),
        INT.interpretation(Date.day),
        QUOTE.optional(),
        in_caseless(MONTHS).interpretation(Date.month),
        INT.interpretation(Date.year),
    ).interpretation(Date)

    DAY = and_(INT, gte(1), lte(31))
    MONTH = and_(INT, gte(1), lte(12))
    YEAR = and_(INT, gte(1900), lte(2100))

    SEP = or_(eq("."), eq("-"), eq("/"), eq(" "))

    DATE_RULE_NUMBERS = rule(
        DAY.interpretation(Date.day),
        SEP,
        MONTH.interpretation(Date.month),
        SEP,
        YEAR.interpretation(Date.year),
    ).interpretation(Date)

    return Parser(or_(DATE_RULE_TEXT, DATE_RULE_NUMBERS).interpretation(Date))
