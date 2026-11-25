"""Imports every model so Base.metadata knows all tables (used by Alembic and tests)."""

from app.audit import models as _audit  # noqa: F401
from app.capacity import models as _capacity  # noqa: F401
from app.change_requests import models as _change_requests  # noqa: F401
from app.finance import models as _finance  # noqa: F401
from app.milestones import models as _milestones  # noqa: F401
from app.notifications import models as _notifications  # noqa: F401
from app.organisations import models as _organisations  # noqa: F401
from app.picklists import models as _picklists  # noqa: F401
from app.project_reports import models as _project_reports  # noqa: F401
from app.projects import models as _projects  # noqa: F401
from app.registers import models as _registers  # noqa: F401
from app.reporting import models as _reporting  # noqa: F401
from app.requirements import models as _requirements  # noqa: F401
from app.sprints import models as _sprints  # noqa: F401
from app.task_links import models as _task_links  # noqa: F401
from app.tasks import models as _tasks  # noqa: F401
from app.users import models as _users  # noqa: F401
