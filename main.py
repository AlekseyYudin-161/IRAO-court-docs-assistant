import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.src.api.v1 import get_api_router
from backend.src.core.config import settings
from backend.src.core.container import Container
from backend.src.core.log import setup_logging


def create_app(container: Container = None) -> FastAPI:
    setup_logging(logging.DEBUG if settings.debug else logging.INFO)

    if container is None:
        container = Container()
        container.check_dependencies()
        container.wire()
        container.ocr_service()

    app = FastAPI(
        title=settings.title,
        description=settings.description,
        version=settings.version,
        docs_url=settings.api_prefix + "/docs",
    )

    app.container = container

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(get_api_router(), prefix=settings.api_prefix)

    @app.get("/ocr")
    async def root():
        return {
            "message": "Court Docs Helper API",
            "version": "1.0.0",
            "endpoints": ["/api/v1/process", "/api/v1/docs"],
        }

    return app


app = create_app()
