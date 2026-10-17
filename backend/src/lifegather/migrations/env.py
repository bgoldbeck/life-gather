from alembic import context

from lifegather.auth.models import Base
from lifegather.credentials import models as credential_models  # noqa: F401

connection = context.config.attributes["connection"]
context.configure(connection=connection, target_metadata=Base.metadata)
with context.begin_transaction():
    context.run_migrations()
