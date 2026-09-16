from datetime import date

from sqlalchemy.orm import Session

from billpay_api.persistence.models import BankAccount, Bill, Biller, BillerAccount, User
from billpay_api.schemas import SeedResponse

SEEDED_USER_ID = "user_alice_example"
SEEDED_FUNDING_ACCOUNT_ID = "ba_ref_alice_checking"
SEEDED_BILLER_ID = "biller_desert_electric"
SEEDED_BILLER_ACCOUNT_ID = "biller_acct_desert_electric"
SEEDED_BILL_ID = "bill_desert_electric_001"


def ensure_seed_data(session: Session) -> SeedResponse:
    if session.get(User, SEEDED_USER_ID) is None:
        session.add(
            User(
                id=SEEDED_USER_ID,
                email="alice@example.test",
                name="Alice Example",
                provider_customer_id="cus_seed_alice",
                status="active",
            )
        )
    if session.get(BankAccount, SEEDED_FUNDING_ACCOUNT_ID) is None:
        session.add(
            BankAccount(
                id=SEEDED_FUNDING_ACCOUNT_ID,
                user_id=SEEDED_USER_ID,
                provider_account_id="ba_seed_alice_checking",
                bank_name="Fictional Test Bank",
                account_type="checking",
                last4="6789",
                verification_status="verified",
            )
        )
    if session.get(Biller, SEEDED_BILLER_ID) is None:
        session.add(
            Biller(
                id=SEEDED_BILLER_ID,
                name="Desert Electric",
                provider_destination_account_id="ba_seed_desert_electric",
                customer_reference_pattern="DE-[0-9]{6}",
                status="active",
            )
        )
    if session.get(BillerAccount, SEEDED_BILLER_ACCOUNT_ID) is None:
        session.add(
            BillerAccount(
                id=SEEDED_BILLER_ACCOUNT_ID,
                user_id=SEEDED_USER_ID,
                biller_id=SEEDED_BILLER_ID,
                customer_reference="DE-000123",
                display_mask="DE-***123",
                nickname="Home electric",
            )
        )
    if session.get(Bill, SEEDED_BILL_ID) is None:
        session.add(
            Bill(
                id=SEEDED_BILL_ID,
                biller_account_id=SEEDED_BILLER_ACCOUNT_ID,
                amount="142.67",
                due_date=date(2026, 10, 15),
                description="Fictional monthly electric bill",
                status="due",
            )
        )
    session.commit()
    return SeedResponse(
        user_id=SEEDED_USER_ID,
        funding_account_id=SEEDED_FUNDING_ACCOUNT_ID,
        bill_id=SEEDED_BILL_ID,
    )
