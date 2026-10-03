from dataclasses import dataclass
from enum import Enum
from typing import Any


from pydantic import BaseModel, Field


class SourceType(str, Enum):
    RULE = "rule"
    NER = "ner"
    REGEX = "regex"


@dataclass(frozen=True)
class Candidate:
    value: str
    start: int
    end: int
    source: SourceType = SourceType.RULE
    confidence: float = 1.0

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass
class PersonCandidate:
    fio: Candidate

    surname: Candidate | None = None
    first_name: Candidate | None = None
    patronymic: Candidate | None = None

    birth_date: Candidate | None = None
    passport: Candidate | None = None
    snils: Candidate | None = None
    inn: Candidate | None = None


from pydantic import BaseModel, Field


class RuleExtraction(BaseModel):
    street: str | None = None
    house: str | None = None
    flat: str | None = None

    surname: str | None = None
    first_name: str | None = None
    patronymic: str | None = None
    fio: str | None = None

    birth_date: str | None = None

    passport: str | None = None
    snils: str | None = None
    inn: str | None = None

    case_number: str | None = None
    case_date: str | None = None

    period_start: str | None = None
    period_end: str | None = None

    debt_main: str | None = None
    debt_penalty: str | None = None
    debt_duty: str | None = None

    co_debtors_count: int = 0
    co_debtors: list[str] = Field(default_factory=list)

class RuleResult(BaseModel):
    value: Any | None = None
    confidence: float = 0.0
    source: str = "rule"