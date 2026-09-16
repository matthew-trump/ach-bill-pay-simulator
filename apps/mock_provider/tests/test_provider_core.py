from pathlib import Path

from fastapi.testclient import TestClient
from mock_provider.main import create_app

API_KEY = "dev_mock_provider_key_do_not_use_for_real_systems"
AUTH_HEADERS = {"Authorization": f"Bearer {API_KEY}"}


def test_customer_and_bank_account_flow(tmp_path: Path) -> None:
    with provider_client(tmp_path) as client:
        customer = create_customer(client)

        account_response = client.post(
            f"/v1/customers/{customer['id']}/bank-accounts",
            headers=AUTH_HEADERS,
            json={
                "routing_number": "000000000",
                "account_number": "000123456789",
                "account_type": "checking",
            },
        )
        assert account_response.status_code == 201
        account = account_response.json()
        assert account["id"].startswith("ba_")
        assert account["last4"] == "6789"
        assert account["verification_status"] == "unverified"

        verify_response = client.post(
            f"/v1/bank-accounts/{account['id']}/verify",
            headers=AUTH_HEADERS,
        )
        assert verify_response.status_code == 200
        assert verify_response.json()["verification_status"] == "verified"


def test_transfer_idempotency_and_changed_request_rejection(tmp_path: Path) -> None:
    with provider_client(tmp_path) as client:
        source, destination = create_account_pair(client)
        request_body = transfer_body(source, destination, value="142.67")
        headers = AUTH_HEADERS | {"Idempotency-Key": "idem-transfer-1"}

        first = client.post("/v1/transfers", headers=headers, json=request_body)
        second = client.post("/v1/transfers", headers=headers, json=request_body)
        changed = client.post(
            "/v1/transfers",
            headers=headers,
            json=transfer_body(source, destination, value="143.00"),
        )

        assert first.status_code == 201
        assert second.status_code == 201
        assert changed.status_code == 409
        assert second.json()["id"] == first.json()["id"]
        assert first.json()["status"] == "created"


def test_transfer_state_machine_and_sandbox_controls(tmp_path: Path) -> None:
    with provider_client(tmp_path) as client:
        source, destination = create_account_pair(client)
        transfer = create_transfer(client, source, destination)

        pending = client.post(f"/_sandbox/transfers/{transfer['id']}/advance")
        processing = client.post(f"/_sandbox/transfers/{transfer['id']}/advance")
        succeeded = client.post(f"/_sandbox/transfers/{transfer['id']}/advance")
        returned = client.post(
            f"/_sandbox/transfers/{transfer['id']}/return",
            json={"return_code": "R01"},
        )
        illegal = client.post(f"/_sandbox/transfers/{transfer['id']}/advance")

        assert pending.json()["status"] == "pending"
        assert processing.json()["status"] == "processing"
        assert succeeded.json()["status"] == "succeeded"
        assert returned.json()["status"] == "returned"
        assert returned.json()["return_code"] == "R01"
        assert illegal.status_code == 409


def test_cancel_only_early_transfer_states(tmp_path: Path) -> None:
    with provider_client(tmp_path) as client:
        source, destination = create_account_pair(client)
        cancelable = create_transfer(client, source, destination, idempotency_key="cancelable")
        canceled = client.post(f"/v1/transfers/{cancelable['id']}/cancel", headers=AUTH_HEADERS)
        assert canceled.status_code == 200
        assert canceled.json()["status"] == "canceled"

        not_cancelable = create_transfer(
            client,
            source,
            destination,
            idempotency_key="not-cancelable",
        )
        client.post(f"/_sandbox/transfers/{not_cancelable['id']}/advance")
        client.post(f"/_sandbox/transfers/{not_cancelable['id']}/advance")
        conflict = client.post(f"/v1/transfers/{not_cancelable['id']}/cancel", headers=AUTH_HEADERS)
        assert conflict.status_code == 409


def provider_client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "provider.sqlite3"
    return TestClient(create_app(f"sqlite:///{db_path}"))


def create_customer(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/v1/customers",
        headers=AUTH_HEADERS,
        json={
            "external_user_id": "user_alice_example",
            "name": "Alice Example",
            "email": "alice@example.test",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_account_pair(client: TestClient) -> tuple[str, str]:
    customer = create_customer(client)
    source = create_bank_account(client, customer["id"], "000123456789")
    destination = create_bank_account(client, customer["id"], "000987654321")
    return source["id"], destination["id"]


def create_bank_account(
    client: TestClient,
    customer_id: str,
    account_number: str,
) -> dict[str, str]:
    response = client.post(
        f"/v1/customers/{customer_id}/bank-accounts",
        headers=AUTH_HEADERS,
        json={
            "routing_number": "000000000",
            "account_number": account_number,
            "account_type": "checking",
        },
    )
    assert response.status_code == 201
    return response.json()


def transfer_body(source: str, destination: str, value: str = "42.00") -> dict[str, object]:
    return {
        "source": source,
        "destination": destination,
        "amount": {"currency": "USD", "value": value},
        "metadata": {"payment_order_id": "pay_test", "leg": "funding"},
    }


def create_transfer(
    client: TestClient,
    source: str,
    destination: str,
    idempotency_key: str = "idem-state-machine",
) -> dict[str, object]:
    response = client.post(
        "/v1/transfers",
        headers=AUTH_HEADERS | {"Idempotency-Key": idempotency_key},
        json=transfer_body(source, destination),
    )
    assert response.status_code == 201
    return response.json()
