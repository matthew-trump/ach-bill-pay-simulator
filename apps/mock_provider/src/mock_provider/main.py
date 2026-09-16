from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from mock_provider.api import make_sandbox_router, make_v1_router
from mock_provider.database import ProviderDatabase
from mock_provider.settings import settings


def create_app(database_url: str | None = None) -> FastAPI:
    provider_db = ProviderDatabase(database_url or settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        provider_db.create_all()
        yield

    app = FastAPI(title="Simulated ACH Provider API", version="0.1.0", lifespan=lifespan)
    app.state.provider_db = provider_db

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    app.include_router(make_v1_router(get_session=provider_db.session, api_key=settings.api_key))
    app.include_router(make_sandbox_router(get_session=provider_db.session))
    return app


app = create_app()
