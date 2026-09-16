from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from sqlalchemy.orm import Session

from billpay_api.persistence.database import BillpayDatabase
from billpay_api.providers.mock_ach import MockAchProviderClient
from billpay_api.providers.types import AchProvider
from billpay_api.schemas import (
    PaymentOrderCreate,
    PaymentOrderResponse,
    ProviderEventIngestResponse,
    SeedResponse,
)
from billpay_api.services.payments import create_payment_order, ingest_provider_event
from billpay_api.services.seed import ensure_seed_data
from billpay_api.settings import settings


def create_app(
    *,
    database_url: str | None = None,
    provider: AchProvider | None = None,
) -> FastAPI:
    billpay_db = BillpayDatabase(database_url or settings.database_url)
    ach_provider = provider or MockAchProviderClient(
        base_url=settings.provider_base_url,
        api_key=settings.provider_api_key,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        billpay_db.create_all()
        yield

    app = FastAPI(title="ACH Bill Pay Simulator API", version="0.1.0", lifespan=lifespan)
    app.state.billpay_db = billpay_db
    app.state.ach_provider = ach_provider

    def get_session() -> Iterator[Session]:
        yield from billpay_db.session()

    def get_provider() -> AchProvider:
        return ach_provider

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    @app.post("/dev/seed", response_model=SeedResponse)
    def seed(session: Session = Depends(get_session)) -> SeedResponse:
        return ensure_seed_data(session)

    @app.post("/v1/payment-orders", response_model=PaymentOrderResponse)
    async def submit_payment_order(
        payload: PaymentOrderCreate,
        session: Session = Depends(get_session),
        provider: AchProvider = Depends(get_provider),
    ) -> PaymentOrderResponse:
        try:
            return await create_payment_order(
                session=session,
                provider=provider,
                payload=payload,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.post("/v1/provider-events", response_model=ProviderEventIngestResponse)
    async def receive_provider_event(
        request: Request,
        session: Session = Depends(get_session),
        provider: AchProvider = Depends(get_provider),
    ) -> ProviderEventIngestResponse:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="event payload must be an object",
            )
        return await ingest_provider_event(session=session, provider=provider, payload=payload)

    return app


app = create_app()
