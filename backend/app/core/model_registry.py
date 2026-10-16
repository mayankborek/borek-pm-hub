"""Imports every model so Base.metadata knows all tables (used by Alembic and tests)."""

from app.projects import models as _projects  # noqa: F401
from app.tasks import models as _tasks  # noqa: F401
from app.users import models as _users  # noqa: F401
