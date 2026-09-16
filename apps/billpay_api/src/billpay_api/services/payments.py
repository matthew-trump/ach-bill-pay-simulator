from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from billpay_api.ids import new_id
from billpay_api.persistence.models import (
    AuthorizationRecord,
    BankAccount,
    Bill,
    Biller,
    BillerAccount,
    PaymentLeg,
    PaymentOrder,
    ProviderEventInbox,
    User,
)
from billpay_api.providers.types import AchProvider
from billpay_api.schemas import (
    PaymentLegResponse,
    PaymentOrderCreate,
    PaymentOrderResponse,
    ProviderEventIngestResponse,
)
from billpay_api.settings import settings


async def create_payment_order(
    *,
    session: Session,
    provider: AchProvider,
    payload: PaymentOrderCreate,
) -> PaymentOrderResponse:
    existing = session.scalars(
        select(PaymentOrder).where(
            PaymentOrder.user_id == payload.user_id,
            PaymentOrder.idempotency_key == payload.idempotency_key,
        )
    ).one_or_none()
    if existing is not None:
        return payment_order_response(session, existing)

    user = _required(session, User, payload.user_id, "user not found")
    funding_account = _required(
        session, BankAccount, payload.funding_account_id, "funding account not found"
    )
    bill = _required(session, Bill, payload.bill_id, "bill not found")
    biller_account = _required(
        session,
        BillerAccount,
        bill.biller_account_id,
        "biller account not found",
    )
    _required(session, Biller, biller_account.biller_id, "biller not found")
    if funding_account.user_id != user.id or biller_account.user_id != user.id:
        raise ValueError("payment entities do not belong to the same user")

    order_id = new_id("pay")
    transfer = await provider.create_transfer(
        source_account_id=funding_account.provider_account_id,
        destination_account_id=settings.settlement_provider_account_id,
        amount=Decimal(bill.amount),
        idempotency_key=f"funding:{order_id}",
        metadata={"payment_order_id": order_id, "leg": "funding"},
    )
    order = PaymentOrder(
        id=order_id,
        user_id=user.id,
        bill_id=bill.id,
        funding_account_id=funding_account.id,
        amount=bill.amount,
        requested_date=date.today(),
        status="funding_pending",
        idempotency_key=payload.idempotency_key,
    )
    leg = PaymentLeg(
        id=new_id("leg"),
        payment_order_id=order.id,
        leg_type="funding",
        provider_transfer_id=transfer.provider_transfer_id,
        source_provider_account_id=funding_account.provider_account_id,
        destination_provider_account_id=settings.settlement_provider_account_id,
        amount=bill.amount,
        status=transfer.status,
        return_code=transfer.return_code,
        provider_created_at=datetime.now(UTC),
    )
    authorization = AuthorizationRecord(
        id=new_id("auth"),
        payment_order_id=order.id,
        authorization_version="sim-v1",
        authorization_text_hash=sha256(payload.authorization_text.encode("utf-8")).hexdigest(),
        accepted_at=datetime.now(UTC),
        account_last4=funding_account.last4,
        amount=bill.amount,
        simulated_session_metadata={"channel": "local-api"},
    )
    session.add(order)
    session.flush()
    session.add_all([leg, authorization])
    session.commit()
    return payment_order_response(session, order)


async def ingest_provider_event(
    *,
    session: Session,
    provider: AchProvider,
    payload: dict[str, object],
) -> ProviderEventIngestResponse:
    provider_event_id = str(payload["id"])
    event_type = str(payload["type"])
    existing = session.scalars(
        select(ProviderEventInbox).where(ProviderEventInbox.provider_event_id == provider_event_id)
    ).one_or_none()
    if existing is not None:
        return ProviderEventIngestResponse(
            provider_event_id=provider_event_id,
            duplicate=True,
            processed=existing.processed_at is not None,
        )

    inbox = ProviderEventInbox(
        id=new_id("inbox"),
        provider_event_id=provider_event_id,
        event_type=event_type,
        payload_json=payload,
    )
    session.add(inbox)
    try:
        transfer = _transfer_from_event(payload)
        provider_transfer_id = str(transfer["id"])
        leg = session.scalars(
            select(PaymentLeg).where(PaymentLeg.provider_transfer_id == provider_transfer_id)
        ).one_or_none()
        if leg is None:
            raise ValueError("payment leg not found for provider transfer")
        leg.status = str(transfer["status"])
        leg.return_code = _optional_str(transfer.get("return_code"))
        await _update_order_for_leg_event(session=session, provider=provider, leg=leg)
        inbox.processed_at = datetime.now(UTC)
        session.commit()
        return ProviderEventIngestResponse(
            provider_event_id=provider_event_id,
            duplicate=False,
            processed=True,
            payment_leg_id=leg.id,
        )
    except Exception as exc:
        inbox.processing_error = str(exc)
        session.commit()
        return ProviderEventIngestResponse(
            provider_event_id=provider_event_id,
            duplicate=False,
            processed=False,
        )


def payment_order_response(session: Session, order: PaymentOrder) -> PaymentOrderResponse:
    legs = session.scalars(
        select(PaymentLeg).where(PaymentLeg.payment_order_id == order.id)
    ).all()
    ordered_legs = sorted(legs, key=lambda leg: (0 if leg.leg_type == "funding" else 1, leg.id))
    return PaymentOrderResponse(
        id=order.id,
        user_id=order.user_id,
        bill_id=order.bill_id,
        funding_account_id=order.funding_account_id,
        amount=order.amount,
        status=order.status,
        idempotency_key=order.idempotency_key,
        legs=[
            PaymentLegResponse(
                id=leg.id,
                leg_type=leg.leg_type,
                provider_transfer_id=leg.provider_transfer_id,
                status=leg.status,
                return_code=leg.return_code,
            )
            for leg in ordered_legs
        ],
    )


async def _update_order_for_leg_event(
    *,
    session: Session,
    provider: AchProvider,
    leg: PaymentLeg,
) -> None:
    order = session.get(PaymentOrder, leg.payment_order_id)
    if order is None:
        return
    if leg.leg_type == "delivery":
        _update_order_for_delivery_event(order, leg)
        return
    if leg.leg_type != "funding":
        return

    delivery_leg = _delivery_leg_for_order(session, order.id)
    if leg.status == "succeeded":
        if delivery_leg is None:
            order.status = "funded"
            await _create_delivery_leg(
                session=session,
                provider=provider,
                order=order,
                funding_leg=leg,
            )
        else:
            _update_order_for_delivery_event(order, delivery_leg)
    elif leg.status == "failed":
        order.status = "action_required" if delivery_leg is not None else "failed"
    elif leg.status == "returned":
        order.status = "action_required" if delivery_leg is not None else "returned"
    else:
        order.status = "funding_pending"


async def _create_delivery_leg(
    *,
    session: Session,
    provider: AchProvider,
    order: PaymentOrder,
    funding_leg: PaymentLeg,
) -> None:
    bill = _required(session, Bill, order.bill_id, "bill not found")
    biller_account = _required(
        session,
        BillerAccount,
        bill.biller_account_id,
        "biller account not found",
    )
    biller = _required(session, Biller, biller_account.biller_id, "biller not found")
    transfer = await provider.create_transfer(
        source_account_id=settings.settlement_provider_account_id,
        destination_account_id=biller.provider_destination_account_id,
        amount=Decimal(order.amount),
        idempotency_key=f"delivery:{order.id}",
        metadata={"payment_order_id": order.id, "leg": "delivery"},
    )
    session.add(
        PaymentLeg(
            id=new_id("leg"),
            payment_order_id=order.id,
            leg_type="delivery",
            provider_transfer_id=transfer.provider_transfer_id,
            source_provider_account_id=settings.settlement_provider_account_id,
            destination_provider_account_id=biller.provider_destination_account_id,
            amount=order.amount,
            status=transfer.status,
            return_code=transfer.return_code,
            provider_created_at=datetime.now(UTC),
        )
    )
    funding_leg.settled_at = datetime.now(UTC)
    order.status = "delivery_pending"
    session.flush()


def _update_order_for_delivery_event(order: PaymentOrder, leg: PaymentLeg) -> None:
    if leg.status == "succeeded":
        order.status = "delivered"
        leg.settled_at = datetime.now(UTC)
    elif leg.status in {"failed", "returned"}:
        order.status = "action_required"
    else:
        order.status = "delivery_pending"


def _delivery_leg_for_order(session: Session, payment_order_id: str) -> PaymentLeg | None:
    return session.scalars(
        select(PaymentLeg).where(
            PaymentLeg.payment_order_id == payment_order_id,
            PaymentLeg.leg_type == "delivery",
        )
    ).one_or_none()


def _transfer_from_event(payload: dict[str, object]) -> dict[str, object]:
    data = payload["data"]
    if not isinstance(data, dict):
        raise ValueError("event data must be an object")
    transfer = data["transfer"]
    if not isinstance(transfer, dict):
        raise ValueError("event transfer must be an object")
    return transfer


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _required[ModelT](
    session: Session,
    model: type[ModelT],
    entity_id: str,
    message: str,
) -> ModelT:
    entity = session.get(model, entity_id)
    if entity is None:
        raise ValueError(message)
    return entity
