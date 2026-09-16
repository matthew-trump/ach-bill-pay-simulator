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
        self.next_id = 1

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
        transfer_id = f"tr_fake_{metadata['leg']}_{self.next_id:03d}"
        self.next_id += 1
        return TransferResult(
            provider_transfer_id=transfer_id,
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
        assert provider.calls[0].destination_account_id == "ba_seed_billpay_settlement"
        assert provider.calls[0].metadata["leg"] == "funding"


def test_successful_funding_starts_one_delivery_leg_without_duplicate_effects(
    tmp_path: Path,
) -> None:
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
        assert repeat_order["status"] == "delivery_pending"
        assert repeat_order["legs"][0]["status"] == "succeeded"
        assert len(repeat_order["legs"]) == 2
        assert repeat_order["legs"][1]["leg_type"] == "delivery"
        assert repeat_order["legs"][1]["provider_transfer_id"] == "tr_fake_delivery_002"
        assert len(provider.calls) == 2
        assert provider.calls[1].source_account_id == "ba_seed_billpay_settlement"
        assert provider.calls[1].destination_account_id == "ba_seed_desert_electric"
        assert provider.calls[1].idempotency_key == f"delivery:{order['id']}"
        assert provider.calls[1].metadata["leg"] == "delivery"


def test_funding_success_posts_balanced_ledger_once_for_retried_events(tmp_path: Path) -> None:
    provider = FakeAchProvider()
    with billpay_client(tmp_path, provider) as client:
        seed = client.post("/dev/seed").json()
        order = submit_seed_payment(client, seed, "pay-ledger-funding")
        funding_transfer_id = order["legs"][0]["provider_transfer_id"]

        first = client.post(
            "/v1/provider-events",
            json=provider_event(
                event_id="evt_ledger_funding_first",
                transfer_id=funding_transfer_id,
                status="succeeded",
                leg="funding",
            ),
        )
        retried_with_new_event_id = client.post(
            "/v1/provider-events",
            json=provider_event(
                event_id="evt_ledger_funding_retry_new_id",
                transfer_id=funding_transfer_id,
                status="succeeded",
                leg="funding",
            ),
        )
        payment = client.get(f"/v1/payment-orders/{order['id']}").json()

        assert first.status_code == 200
        assert retried_with_new_event_id.status_code == 200
        assert len(payment["ledger_transactions"]) == 1
        transaction = payment["ledger_transactions"][0]
        assert transaction["transaction_type"] == "funding_succeeded"
        assert sum(entry["debit_cents"] for entry in transaction["entries"]) == 14267
        assert sum(entry["credit_cents"] for entry in transaction["entries"]) == 14267
        assert len(provider.calls) == 2


def test_delivery_success_marks_payment_delivered(tmp_path: Path) -> None:
    provider = FakeAchProvider()
    with billpay_client(tmp_path, provider) as client:
        seed = client.post("/dev/seed").json()
        order = submit_seed_payment(client, seed, "pay-delivery-success")
        funding_event = provider_event(
            event_id="evt_funding_succeeded",
            transfer_id=order["legs"][0]["provider_transfer_id"],
            status="succeeded",
            leg="funding",
        )
        client.post("/v1/provider-events", json=funding_event)
        order_with_delivery = submit_seed_payment(client, seed, "pay-delivery-success")
        delivery_leg = order_with_delivery["legs"][1]

        response = client.post(
            "/v1/provider-events",
            json=provider_event(
                event_id="evt_delivery_succeeded",
                transfer_id=delivery_leg["provider_transfer_id"],
                status="succeeded",
                leg="delivery",
            ),
        )
        final_order = submit_seed_payment(client, seed, "pay-delivery-success")

        assert response.status_code == 200
        assert final_order["status"] == "delivered"
        assert final_order["legs"][1]["status"] == "succeeded"


def test_delivery_success_posts_second_balanced_ledger_transaction(tmp_path: Path) -> None:
    provider = FakeAchProvider()
    with billpay_client(tmp_path, provider) as client:
        seed = client.post("/dev/seed").json()
        order = submit_seed_payment(client, seed, "pay-ledger-delivery")
        client.post(
            "/v1/provider-events",
            json=provider_event(
                event_id="evt_ledger_delivery_funding",
                transfer_id=order["legs"][0]["provider_transfer_id"],
                status="succeeded",
                leg="funding",
            ),
        )
        order_with_delivery = client.get(f"/v1/payment-orders/{order['id']}").json()
        client.post(
            "/v1/provider-events",
            json=provider_event(
                event_id="evt_ledger_delivery_success",
                transfer_id=order_with_delivery["legs"][1]["provider_transfer_id"],
                status="succeeded",
                leg="delivery",
            ),
        )

        final_order = client.get(f"/v1/payment-orders/{order['id']}").json()
        invariants = client.get("/v1/ledger/invariants").json()
        accounts = {
            account["id"]: account for account in client.get("/v1/ledger/accounts").json()
        }

        assert final_order["status"] == "delivered"
        assert [tx["transaction_type"] for tx in final_order["ledger_transactions"]] == [
            "funding_succeeded",
            "delivery_succeeded",
        ]
        for transaction in final_order["ledger_transactions"]:
            assert len(transaction["entries"]) == 2
            assert sum(entry["debit_cents"] for entry in transaction["entries"]) == sum(
                entry["credit_cents"] for entry in transaction["entries"]
            )
        assert invariants == {"balanced": True, "unbalanced_transaction_ids": []}
        assert accounts["ledger_platform_settlement_cash"]["balance_cents"] == 0
        assert accounts["ledger_customer_bill_payment_liability"]["balance_cents"] == 0


def test_funding_failure_before_delivery_marks_payment_failed(tmp_path: Path) -> None:
    provider = FakeAchProvider()
    with billpay_client(tmp_path, provider) as client:
        seed = client.post("/dev/seed").json()
        order = submit_seed_payment(client, seed, "pay-funding-fails")

        response = client.post(
            "/v1/provider-events",
            json=provider_event(
                event_id="evt_funding_failed",
                transfer_id=order["legs"][0]["provider_transfer_id"],
                status="failed",
                leg="funding",
            ),
        )
        final_order = submit_seed_payment(client, seed, "pay-funding-fails")

        assert response.status_code == 200
        assert final_order["status"] == "failed"
        assert len(final_order["legs"]) == 1
        assert len(provider.calls) == 1


def test_delivery_failure_after_funding_marks_action_required(tmp_path: Path) -> None:
    provider = FakeAchProvider()
    with billpay_client(tmp_path, provider) as client:
        seed = client.post("/dev/seed").json()
        order = submit_seed_payment(client, seed, "pay-delivery-fails")
        client.post(
            "/v1/provider-events",
            json=provider_event(
                event_id="evt_funding_for_failed_delivery",
                transfer_id=order["legs"][0]["provider_transfer_id"],
                status="succeeded",
                leg="funding",
            ),
        )
        order_with_delivery = submit_seed_payment(client, seed, "pay-delivery-fails")

        response = client.post(
            "/v1/provider-events",
            json=provider_event(
                event_id="evt_delivery_failed",
                transfer_id=order_with_delivery["legs"][1]["provider_transfer_id"],
                status="failed",
                leg="delivery",
            ),
        )
        final_order = submit_seed_payment(client, seed, "pay-delivery-fails")

        assert response.status_code == 200
        assert final_order["status"] == "action_required"
        assert final_order["legs"][1]["status"] == "failed"


def test_late_funding_return_after_delivery_marks_action_required(tmp_path: Path) -> None:
    provider = FakeAchProvider()
    with billpay_client(tmp_path, provider) as client:
        seed = client.post("/dev/seed").json()
        order = submit_seed_payment(client, seed, "pay-late-return")
        client.post(
            "/v1/provider-events",
            json=provider_event(
                event_id="evt_funding_before_late_return",
                transfer_id=order["legs"][0]["provider_transfer_id"],
                status="succeeded",
                leg="funding",
            ),
        )
        order_with_delivery = submit_seed_payment(client, seed, "pay-late-return")
        client.post(
            "/v1/provider-events",
            json=provider_event(
                event_id="evt_delivery_before_late_return",
                transfer_id=order_with_delivery["legs"][1]["provider_transfer_id"],
                status="succeeded",
                leg="delivery",
            ),
        )

        response = client.post(
            "/v1/provider-events",
            json=provider_event(
                event_id="evt_late_funding_return",
                transfer_id=order["legs"][0]["provider_transfer_id"],
                status="returned",
                return_code="R01",
                leg="funding",
            ),
        )
        final_order = submit_seed_payment(client, seed, "pay-late-return")

        assert response.status_code == 200
        assert final_order["status"] == "action_required"
        assert final_order["legs"][0]["status"] == "returned"
        assert final_order["legs"][0]["return_code"] == "R01"
        assert final_order["legs"][1]["status"] == "succeeded"


def submit_seed_payment(
    client: TestClient,
    seed: dict[str, str],
    idempotency_key: str,
) -> dict[str, object]:
    return client.post(
        "/v1/payment-orders",
        json={
            "user_id": seed["user_id"],
            "bill_id": seed["bill_id"],
            "funding_account_id": seed["funding_account_id"],
            "idempotency_key": idempotency_key,
            "authorization_text": "I authorize this simulated ACH debit.",
        },
    ).json()


def billpay_client(tmp_path: Path, provider: FakeAchProvider) -> TestClient:
    db_path = tmp_path / "billpay.sqlite3"
    return TestClient(create_app(database_url=f"sqlite:///{db_path}", provider=provider))


def provider_event(
    *,
    event_id: str,
    transfer_id: str,
    status: str,
    leg: str = "funding",
    return_code: str | None = None,
) -> dict[str, object]:
    return {
        "id": event_id,
        "type": f"transfer.{status}",
        "created_at": "2026-09-18T12:05:00Z",
        "data": {
            "transfer": {
                "id": transfer_id,
                "status": status,
                "return_code": return_code,
                "amount": {"currency": "USD", "value": "142.67"},
                "metadata": {"payment_order_id": "pay_test", "leg": leg},
            }
        },
    }
