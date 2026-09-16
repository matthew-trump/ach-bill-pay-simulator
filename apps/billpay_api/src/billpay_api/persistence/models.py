from datetime import UTC, date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from billpay_api.persistence.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "billpay_users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_customer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class BankAccount(Base):
    __tablename__ = "billpay_bank_accounts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("billpay_users.id"), nullable=False)
    provider_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    bank_name: Mapped[str] = mapped_column(String(120), nullable=False)
    account_type: Mapped[str] = mapped_column(String(32), nullable=False)
    last4: Mapped[str] = mapped_column(String(4), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Biller(Base):
    __tablename__ = "billpay_billers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_destination_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_reference_pattern: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class BillerAccount(Base):
    __tablename__ = "billpay_biller_accounts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("billpay_users.id"), nullable=False)
    biller_id: Mapped[str] = mapped_column(ForeignKey("billpay_billers.id"), nullable=False)
    customer_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    display_mask: Mapped[str] = mapped_column(String(32), nullable=False)
    nickname: Mapped[str] = mapped_column(String(120), nullable=False)


class Bill(Base):
    __tablename__ = "billpay_bills"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    biller_account_id: Mapped[str] = mapped_column(
        ForeignKey("billpay_biller_accounts.id"), nullable=False
    )
    amount: Mapped[str] = mapped_column(String(32), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class PaymentOrder(Base):
    __tablename__ = "billpay_payment_orders"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("billpay_users.id"), nullable=False)
    bill_id: Mapped[str] = mapped_column(ForeignKey("billpay_bills.id"), nullable=False)
    funding_account_id: Mapped[str] = mapped_column(
        ForeignKey("billpay_bank_accounts.id"), nullable=False
    )
    amount: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class PaymentLeg(Base):
    __tablename__ = "billpay_payment_legs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payment_order_id: Mapped[str] = mapped_column(
        ForeignKey("billpay_payment_orders.id"), nullable=False
    )
    leg_type: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_transfer_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    source_provider_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    destination_provider_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    return_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    provider_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthorizationRecord(Base):
    __tablename__ = "billpay_authorization_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payment_order_id: Mapped[str] = mapped_column(
        ForeignKey("billpay_payment_orders.id"), nullable=False
    )
    authorization_version: Mapped[str] = mapped_column(String(32), nullable=False)
    authorization_text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    account_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    amount: Mapped[str] = mapped_column(String(32), nullable=False)
    simulated_session_metadata: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)


class ProviderEventInbox(Base):
    __tablename__ = "billpay_provider_event_inbox"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider_event_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
