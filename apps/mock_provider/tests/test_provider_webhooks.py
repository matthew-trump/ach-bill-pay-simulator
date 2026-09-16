from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from mock_provider.main import create_app
from mock_provider.webhooks import canonical_json_bytes, verify_webhook_signature
from test_provider_core import AUTH_HEADERS, create_account_pair, create_transfer


def test_webhook_receiver_verifies_signature(tmp_path: Path) -> None:
    received: list[dict[str, object]] = []

    with receiver_server(received) as receiver:
        with provider_client(tmp_path) as client:
            endpoint = create_webhook_endpoint(client, receiver.url)
            receiver.secret = endpoint["secret"]
            source, destination = create_account_pair(client)
            transfer = create_transfer(client, source, destination)

            response = client.post(f"/_sandbox/transfers/{transfer['id']}/advance")

            assert response.status_code == 200
            assert len(received) == 1
            assert received[0]["signature_valid"] is True
            assert received[0]["body"]["type"] == "transfer.pending"

            deliveries = client.get("/v1/webhook-deliveries", headers=AUTH_HEADERS)
            assert deliveries.status_code == 200
            assert deliveries.json()[0]["endpoint_id"] == endpoint["id"]
            assert deliveries.json()[0]["response_status"] == 204


def test_duplicate_webhook_keeps_same_event_id(tmp_path: Path) -> None:
    received: list[dict[str, object]] = []

    with receiver_server(received) as receiver:
        with provider_client(tmp_path) as client:
            endpoint = create_webhook_endpoint(client, receiver.url)
            receiver.secret = endpoint["secret"]
            source, destination = create_account_pair(client)
            transfer = create_transfer(client, source, destination)
            client.post(f"/_sandbox/transfers/{transfer['id']}/advance")

            duplicate = client.post(f"/_sandbox/transfers/{transfer['id']}/duplicate-last-webhook")

            assert duplicate.status_code == 200
            assert len(received) == 2
            assert received[0]["body"]["id"] == received[1]["body"]["id"]
            assert duplicate.json()["id"] == received[0]["body"]["id"]


def test_failed_delivery_can_be_retried(tmp_path: Path) -> None:
    with provider_client(tmp_path) as client:
        create_webhook_endpoint(client, "http://127.0.0.1:9/webhooks/provider")
        source, destination = create_account_pair(client)
        transfer = create_transfer(client, source, destination)
        client.post(f"/_sandbox/transfers/{transfer['id']}/advance")

        deliveries = client.get("/v1/webhook-deliveries", headers=AUTH_HEADERS).json()
        assert deliveries[0]["response_status"] is None
        assert deliveries[0]["error"]

        retry = client.post(f"/_sandbox/webhook-deliveries/{deliveries[0]['id']}/retry")
        assert retry.status_code == 200
        assert retry.json()["attempt_number"] == 2
        assert retry.json()["event_id"] == deliveries[0]["event_id"]


def test_out_of_order_events_are_visible(tmp_path: Path) -> None:
    received: list[dict[str, object]] = []

    with receiver_server(received) as receiver:
        with provider_client(tmp_path) as client:
            endpoint = create_webhook_endpoint(client, receiver.url)
            receiver.secret = endpoint["secret"]
            source, destination = create_account_pair(client)
            transfer = create_transfer(client, source, destination)

            response = client.post(f"/_sandbox/transfers/{transfer['id']}/send-out-of-order-events")

            assert response.status_code == 200
            assert [event["type"] for event in response.json()] == [
                "transfer.succeeded",
                "transfer.processing",
                "transfer.pending",
            ]
            assert [item["body"]["type"] for item in received] == [
                "transfer.succeeded",
                "transfer.processing",
                "transfer.pending",
            ]


def provider_client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "provider-webhooks.sqlite3"
    return TestClient(create_app(f"sqlite:///{db_path}"))


def create_webhook_endpoint(client: TestClient, url: str) -> dict[str, str]:
    response = client.post(
        "/v1/webhook-endpoints",
        headers=AUTH_HEADERS,
        json={"url": url},
    )
    assert response.status_code == 201
    return response.json()


class Receiver:
    def __init__(self, url: str) -> None:
        self.url = url
        self.secret = ""


@contextmanager
def receiver_server(received: list[dict[str, object]]) -> Iterator[Receiver]:
    app = FastAPI()
    receiver = Receiver("")

    @app.post("/webhooks/provider")
    async def receive_webhook(request: Request) -> Response:
        body = await request.body()
        payload = await request.json()
        timestamp = int(request.headers["X-Mock-Webhook-Timestamp"])
        signature = request.headers["X-Mock-Webhook-Signature"]
        signature_valid = verify_webhook_signature(
            secret=receiver.secret,
            timestamp=timestamp,
            body=canonical_json_bytes(payload),
            signature=signature,
        )
        received.append({"body": payload, "signature_valid": signature_valid})
        assert body == canonical_json_bytes(payload)
        return Response(status_code=204)

    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)

    import threading

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        pass
    sockets = server.servers[0].sockets
    port = sockets[0].getsockname()[1]
    receiver.url = f"http://127.0.0.1:{port}/webhooks/provider"
    try:
        yield receiver
    finally:
        server.should_exit = True
        thread.join(timeout=5)
