from fastapi import APIRouter
from . import ocr_ner


def get_api_router() -> APIRouter:
    r = APIRouter()
    r.include_router(ocr_ner.router)
    return r
