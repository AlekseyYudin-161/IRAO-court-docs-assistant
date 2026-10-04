from .extractors import (
    NameExtractor,
    DateExtractor,
    CostExtractor,
    AddressExtractor,
    PassportNumberExtractor,
    SnilsNumberExtractor,
    TINExtractor,
    RegexExtractor,
)
from .patterns import (
    PASSPORT_NUMBER_PATTERN,
    SNILS_NUMBER_PATTERN,
    TIN_PATTERN,
)
from .ner_service import NERService

from .rules import (
    Candidate,
    PersonCandidate,
    RuleExtraction,
    RuleResult,
    RuleResolver,
)
from .rules.address_rules import extract_address
from .rules.case_rules import (
    extract_case_number,
    extract_case_date,
)
from .rules.debt_rules import (
    extract_main_debt,
    extract_penalty,
    extract_duty,
)
from .rules.period_rules import extract_period
from .rules.person_rules import (
    extract_debtor_block,
    extract_co_debtors,
    extract_birth_date,
    is_official,
    signature,
)
from .rules.text_utils import (
    normalize_spaces,
    normalize_for_rules,
    clean_value,
    overlap,
    find_first_pattern,
    context,
    window_after,
)

__all__ = [
    # Extractors
    "NameExtractor",
    "DateExtractor",
    "CostExtractor",
    "AddressExtractor",
    "PassportNumberExtractor",
    "SnilsNumberExtractor",
    "TINExtractor",
    "RegexExtractor",

    # Pipeline
    "NERService",

    # Patterns
    "PASSPORT_NUMBER_PATTERN",
    "SNILS_NUMBER_PATTERN",
    "TIN_PATTERN",

    # Rules: models
    "Candidate",
    "PersonCandidate",
    "RuleExtraction",
    "RuleResult",
    "RuleResolver",

    # Rules: address
    "extract_address",

    # Rules: case
    "extract_case_number",
    "extract_case_date",

    # Rules: debt
    "extract_main_debt",
    "extract_penalty",
    "extract_duty",

    # Rules: period
    "extract_period",

    # Rules: person
    "extract_debtor_block",
    "extract_co_debtors",
    "extract_birth_date",
    "is_official",
    "signature",

    # Rules: text utils
    "normalize_spaces",
    "normalize_for_rules",
    "clean_value",
    "overlap",
    "find_first_pattern",
    "context",
    "window_after",
]