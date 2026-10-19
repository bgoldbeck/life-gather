"""The existing exact scoped order identity, shared by discovery and evidence."""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.memory.service import MemoryError, fingerprint, normalized
from lifegather.reconciliation.models import Purchase


def purchase_in(
    db: Session,
    actor: Account,
    source_id: str,
    retailer: str,
    account_scope: str,
    order_id: str,
    now: int,
    *,
    create: bool = True,
) -> Purchase:
    key = fingerprint([normalized(retailer), account_scope, order_id])
    row = db.scalar(
        select(Purchase)
        .where(Purchase.user_id == actor.id, Purchase.identity_key == key)
        .limit(1)
    )
    if row is None:
        if not create:
            raise MemoryError(
                "A payment must link to an existing purchase; "
                "it cannot establish item contents"
            )
        row = Purchase(
            id=str(uuid4()),
            user_id=actor.id,
            recorded_at=now,
            identity_key=key,
            retailer=retailer,
            account_scope=account_scope,
            order_id=order_id,
            source_id=source_id,
        )
        db.add(row)
        db.flush()
    return row
