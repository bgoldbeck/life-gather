from alembic import context

from lifegather.auth import email_models  # noqa: F401
from lifegather.auth.models import Base
from lifegather.chat import models as chat_models  # noqa: F401
from lifegather.credentials import models as credential_models  # noqa: F401
from lifegather.memory import models as memory_models  # noqa: F401
from lifegather.reconciliation import models as reconciliation_models  # noqa: F401
from lifegather.reconciliation import proposal_models  # noqa: F401

connection = context.config.attributes["connection"]
context.configure(connection=connection, target_metadata=Base.metadata)
with context.begin_transaction():
    context.run_migrations()
