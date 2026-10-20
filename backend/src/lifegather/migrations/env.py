from alembic import context

from lifegather.assets import models as asset_models  # noqa: F401
from lifegather.auth import email_models  # noqa: F401
from lifegather.auth.models import Base
from lifegather.chat import models as chat_models  # noqa: F401
from lifegather.credentials import models as credential_models  # noqa: F401
from lifegather.documents import models as document_models  # noqa: F401
from lifegather.mailboxes import discovery_models  # noqa: F401
from lifegather.mailboxes import models as mailbox_models  # noqa: F401
from lifegather.maintenance import models as maintenance_models  # noqa: F401
from lifegather.memory import models as memory_models  # noqa: F401
from lifegather.photos import models as photo_models  # noqa: F401
from lifegather.purchases import models as purchase_models  # noqa: F401
from lifegather.reconciliation import models as reconciliation_models  # noqa: F401
from lifegather.reconciliation import (
    proposal_models,  # noqa: F401
    receipt_models,  # noqa: F401
)
from lifegather.scans import models as scan_models  # noqa: F401

connection = context.config.attributes["connection"]
context.configure(connection=connection, target_metadata=Base.metadata)
with context.begin_transaction():
    context.run_migrations()
