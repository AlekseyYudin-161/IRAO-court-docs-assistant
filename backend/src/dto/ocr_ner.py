from pydantic import BaseModel, ConfigDict
from typing import Optional


class ExtractedEntitiesDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_type: str = ""
    file_name: str = ""
    names: list[str]
    dates: list[str]
    passport_number: list[str]
    snils_number: list[str]
    tin_number: list[str]
    money: list[str]
    addresses: list[str]
    paragraph_text: str = ""


class ProcessDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    success: bool
    processed_results: list[ExtractedEntitiesDTO]
