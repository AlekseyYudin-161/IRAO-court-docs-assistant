from yargy import Parser, rule, and_, not_
from yargy.interpretation import fact
from yargy.predicates import gram


def name_parser():
    Person = fact("Person", ["first", "middle", "last"])

    LAST = and_(
        gram("Surn"),
        not_(gram("Abbr")),
    )
    FIRST = and_(
        gram("Name"),
        not_(gram("Abbr")),
    )
    MIDDLE = and_(
        gram("Patr"),
        not_(gram("Abbr")),
    )

    PERSON_RULE = rule(
        LAST.interpretation(Person.last),
        FIRST.interpretation(Person.first),
        MIDDLE.interpretation(Person.middle),
    ).interpretation(Person)

    return Parser(PERSON_RULE)
