from datetime import UTC, datetime
from hmac import compare_digest
from hmac import new as hmac_new
from json import dumps

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mock_provider.ids import new_id
from mock_provider.models import ProviderEvent, Transfer, WebhookDelivery, WebhookEndpoint, utc_now
from mock_provider.services import response_from_transfer


def event_type_for_status(status: str) -> str:
    return f"transfer.{status}"


def canonical_json_bytes(payload: dict[str, object]) -> bytes:
    return dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def webhook_signature(*, secret: str, timestamp: int, body: bytes) -> str:
    signed_payload = str(timestamp).encode("utf-8") + b"." + body
    digest = hmac_new(secret.encode("utf-8"), signed_payload, "sha256").hexdigest()
    return f"sha256={digest}"


def verify_webhook_signature(
    *,
    secret: str,
    timestamp: int,
    body: bytes,
    signature: str,
) -> bool:
    expected = webhook_signature(secret=secret, timestamp=timestamp, body=body)
    return compare_digest(expected, signature)


def create_transfer_event(session: Session, transfer: Transfer) -> ProviderEvent:
    payload = {
        "id": new_id("evt"),
        "type": event_type_for_status(transfer.status),
        "created_at": utc_now().isoformat(),
        "data": {"transfer": response_from_transfer(transfer).model_dump()},
    }
    event = ProviderEvent(
        id=str(payload["id"]),
        type=str(payload["type"]),
        transfer_id=transfer.id,
        payload_json=payload,
    )
    session.add(event)
    return event


def create_duplicate_event(session: Session, transfer_id: str) -> ProviderEvent | None:
    return session.scalars(
        select(ProviderEvent)
        .where(ProviderEvent.transfer_id == transfer_id)
        .order_by(ProviderEvent.created_at.desc())
    ).first()


def create_out_of_order_events(session: Session, transfer: Transfer) -> list[ProviderEvent]:
    original_status = transfer.status
    events: list[ProviderEvent] = []
    for status in ("succeeded", "processing", "pending"):
        transfer.status = status
        events.append(create_transfer_event(session, transfer))
    transfer.status = original_status
    return events


def active_endpoints(session: Session) -> list[WebhookEndpoint]:
    return list(
        session.scalars(
            select(WebhookEndpoint)
            .where(WebhookEndpoint.status == "active")
            .order_by(WebhookEndpoint.created_at)
        )
    )


def deliver_event_to_active_endpoints(
    session: Session,
    event: ProviderEvent,
    *,
    timeout_seconds: float,
) -> list[WebhookDelivery]:
    return [
        deliver_event(session, event, endpoint, timeout_seconds=timeout_seconds)
        for endpoint in active_endpoints(session)
    ]


def deliver_event(
    session: Session,
    event: ProviderEvent,
    endpoint: WebhookEndpoint,
    *,
    timeout_seconds: float,
) -> WebhookDelivery:
    attempt_number = next_attempt_number(session, event.id, endpoint.id)
    body = canonical_json_bytes(event.payload_json)
    timestamp = int(datetime.now(UTC).timestamp())
    headers = {
        "Content-Type": "application/json",
        "X-Mock-Webhook-Timestamp": str(timestamp),
        "X-Mock-Webhook-Signature": webhook_signature(
            secret=endpoint.secret,
            timestamp=timestamp,
            body=body,
        ),
    }
    delivery = WebhookDelivery(
        id=new_id("wd"),
        event_id=event.id,
        endpoint_id=endpoint.id,
        attempt_number=attempt_number,
        request_headers=headers,
        request_body=event.payload_json,
    )
    try:
        response = httpx.post(endpoint.url, content=body, headers=headers, timeout=timeout_seconds)
        delivery.response_status = response.status_code
        delivery.response_body = response.text
        if 200 <= response.status_code < 300:
            delivery.delivered_at = utc_now()
    except httpx.HTTPError as exc:
        delivery.error = str(exc)
    session.add(delivery)
    return delivery


def next_attempt_number(session: Session, event_id: str, endpoint_id: str) -> int:
    latest = session.scalar(
        select(func.max(WebhookDelivery.attempt_number)).where(
            WebhookDelivery.event_id == event_id,
            WebhookDelivery.endpoint_id == endpoint_id,
        )
    )
    return int(latest or 0) + 1
