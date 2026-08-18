"""Model package.

Importing this module registers every mapped class with the SQLAlchemy
registry, which is what lets relationships refer to each other by name and
what lets Alembic see the full metadata.
"""

from app.models.catalog import Customer, Product, ProductFamily
from app.models.collab import Attachment, Comment, Notification
from app.models.execution import Review, Revision, TimeEntry
from app.models.project import Project, ProjectMember
from app.models.release import DesignRelease
from app.models.system import (
    AppSetting,
    AuditLog,
    DocumentCounter,
    IntegrationRecord,
    StatusHistory,
    SyncLog,
)
from app.models.task import Task, TaskDependency, TaskEstimateHistory
from app.models.template import DesignTemplate, DesignTemplateVersion, TemplateTask
from app.models.user import (
    Holiday,
    LeaveRecord,
    Permission,
    Role,
    RolePermission,
    Skill,
    User,
    UserCapacity,
    UserRole,
    UserSkill,
)

__all__ = [
    "AppSetting",
    "Attachment",
    "AuditLog",
    "Comment",
    "Customer",
    "DesignRelease",
    "DesignTemplate",
    "DesignTemplateVersion",
    "DocumentCounter",
    "Holiday",
    "IntegrationRecord",
    "LeaveRecord",
    "Notification",
    "Permission",
    "Product",
    "ProductFamily",
    "Project",
    "ProjectMember",
    "Review",
    "Revision",
    "Role",
    "RolePermission",
    "Skill",
    "StatusHistory",
    "SyncLog",
    "Task",
    "TaskDependency",
    "TaskEstimateHistory",
    "TemplateTask",
    "TimeEntry",
    "User",
    "UserCapacity",
    "UserRole",
    "UserSkill",
]
