from fastapi import FastAPI

from billpay_api.settings import settings

app = FastAPI(title="Mock ACH Bill-Pay API", version="0.1.0")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}
