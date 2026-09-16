from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from billpay_api.main import create_app
from billpay_api.providers.types import TransferResult, TransferStatus
from fastapi.testclient import TestClient


@dataclass
class TransferCall:
    source_account_id: str
    destination_account_id: str
    amount: Decimal
    idempotency_key: str
    metadata: dict[str, str]


class FakeAchProvider:
    def __init__(self) -> None:
        self.calls: list[TransferCall] = []

    async def create_transfer(
        self,
        *,
        source_account_id: str,
        destination_account_id: str,
        amount: Decimal,
        idempotency_key: str,
        metadata: dict[str, str],
    ) -> TransferResult:
        self.calls.append(
            TransferCall(
                source_account_id=source_account_id,
                destination_account_id=destination_account_id,
                amount=amount,
                idempotency_key=idempotency_key,
                metadata=metadata,
            )
        )
        return TransferResult(
            provider_transfer_id="tr_fake_funding_001",
            status=TransferStatus.CREATED,
        )


def test_submitting_payment_creates_exactly_one_funding_transfer(tmp_path: Path) -> None:
    provider = FakeAchProvider()
    with billpay_client(tmp_path, provider) as client:
        seed = client.post("/dev/seed").json()
        request_body = {
            "user_id": seed["user_id"],
            "bill_id": seed["bill_id"],
            "funding_account_id": seed["funding_account_id"],
            "idempotency_key": "pay-once",
            "authorization_text": "I authorize this simulated ACH debit.",
        }

        first = client.post("/v1/payment-orders", json=request_body)
        second = client.post("/v1/payment-orders", json=request_body)

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["id"] == second.json()["id"]
        assert first.json()["status"] == "funding_pending"
        assert first.json()["legs"][0]["provider_transfer_id"] == "tr_fake_funding_001"
        assert len(provider.calls) == 1
        assert provider.calls[0].source_account_id == "ba_seed_alice_checking"
        assert provider.calls[0].destination_account_id == "ba_seed_desert_electric"
        assert provider.calls[0].metadata["leg"] == "funding"


def test_provider_event_updates_funding_leg_without_duplicate_effects(tmp_path: Path) -> None:
    provider = FakeAchProvider()
    with billpay_client(tmp_path, provider) as client:
        seed = client.post("/dev/seed").json()
        order = client.post(
            "/v1/payment-orders",
            json={
                "user_id": seed["user_id"],
                "bill_id": seed["bill_id"],
                "funding_account_id": seed["funding_account_id"],
                "idempotency_key": "pay-event",
                "authorization_text": "I authorize this simulated ACH debit.",
            },
        ).json()

        event = provider_event(
            event_id="evt_duplicate_test",
            transfer_id=order["legs"][0]["provider_transfer_id"],
            status="succeeded",
        )
        first = client.post("/v1/provider-events", json=event)
        duplicate = client.post("/v1/provider-events", json=event)

        assert first.status_code == 200
        assert duplicate.status_code == 200
        assert first.json()["processed"] is True
        assert first.json()["duplicate"] is False
        assert duplicate.json()["duplicate"] is True
        assert duplicate.json()["processed"] is True

        repeat_order = client.post(
            "/v1/payment-orders",
            json={
                "user_id": seed["user_id"],
                "bill_id": seed["bill_id"],
                "funding_account_id": seed["funding_account_id"],
                "idempotency_key": "pay-event",
                "authorization_text": "I authorize this simulated ACH debit.",
            },
        ).json()
        assert repeat_order["status"] == "funded"
        assert repeat_order["legs"][0]["status"] == "succeeded"
        assert len(provider.calls) == 1


def billpay_client(tmp_path: Path, provider: FakeAchProvider) -> TestClient:
    db_path = tmp_path / "billpay.sqlite3"
    return TestClient(create_app(database_url=f"sqlite:///{db_path}", provider=provider))


def provider_event(*, event_id: str, transfer_id: str, status: str) -> dict[str, object]:
    return {
        "id": event_id,
        "type": f"transfer.{status}",
        "created_at": "2026-09-18T12:05:00Z",
        "data": {
            "transfer": {
                "id": transfer_id,
                "status": status,
                "return_code": None,
                "amount": {"currency": "USD", "value": "142.67"},
                "metadata": {"payment_order_id": "pay_test", "leg": "funding"},
            }
        },
    }
