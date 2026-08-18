"""Import surface for Alembic autogenerate.

Alembic only sees tables that have been imported by the time it inspects
Base.metadata, so pulling in the model package here is what makes
`alembic revision --autogenerate` complete.
"""

from app.db.base_class import Base  # noqa: F401
from app.models import *  # noqa: F401,F403
