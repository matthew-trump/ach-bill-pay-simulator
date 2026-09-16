from fastapi import FastAPI

from mock_provider.settings import settings

app = FastAPI(title="Mock ACH Provider API", version="0.1.0")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}
