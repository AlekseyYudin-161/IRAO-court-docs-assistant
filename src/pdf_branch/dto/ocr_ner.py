from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from src.pdf_branch.services.ner.rules.models import RuleExtraction


class ValidationIssue(BaseModel):
    field: str
    ok: bool
    reason: str = ""

class ExtractedEntitiesDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_type: str = ""
    file_name: str = ""
    #
    # names: list[str]
    # dates: list[str]
    # passport_number: list[str]
    # snils_number: list[str]
    # tin_number: list[str]
    # money: list[str]
    # addresses: list[str]
    paragraph_text: str = ""


    rule_extraction: RuleExtraction | None = None

class ProcessDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    success: bool
    processed_results: list[ExtractedEntitiesDTO]
