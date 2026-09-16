from decimal import Decimal

import httpx

from billpay_api.providers.types import AchProvider, TransferResult, TransferStatus


class MockAchProviderClient(AchProvider):
    def __init__(self, *, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def create_transfer(
        self,
        *,
        source_account_id: str,
        destination_account_id: str,
        amount: Decimal,
        idempotency_key: str,
        metadata: dict[str, str],
    ) -> TransferResult:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=5) as client:
            response = await client.post(
                "/v1/transfers",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Idempotency-Key": idempotency_key,
                },
                json={
                    "source": source_account_id,
                    "destination": destination_account_id,
                    "amount": {"currency": "USD", "value": f"{amount:.2f}"},
                    "metadata": metadata,
                },
            )
            response.raise_for_status()
        body = response.json()
        return TransferResult(
            provider_transfer_id=body["id"],
            status=TransferStatus(body["status"]),
            return_code=body.get("return_code"),
        )
