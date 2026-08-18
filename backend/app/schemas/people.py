"""Users, roles, skills and capacity payloads."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.enums import SkillLevel
from app.schemas.common import ORMModel

SKILL_LEVEL_RANK = {
    SkillLevel.BEGINNER.value: 1,
    SkillLevel.INTERMEDIATE.value: 2,
    SkillLevel.ADVANCED.value: 3,
    SkillLevel.EXPERT.value: 4,
}


class RoleOut(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    rank: int


class PermissionOut(ORMModel):
    id: uuid.UUID
    code: str
    module: str
    description: str | None = None


class UserSkillOut(BaseModel):
    skill_id: uuid.UUID
    name: str | None = None
    category: str | None = None
    level: str
    level_rank: int
    years_experience: float | None = None


class UserOut(ORMModel):
    id: uuid.UUID
    code: str
    email: str
    full_name: str
    designation: str | None = None
    department: str | None = None
    phone: str | None = None
    is_active: bool
    reports_to_id: uuid.UUID | None = None
    standard_daily_hours: float
    working_days_per_week: int
    last_login_at: datetime | None = None
    created_at: datetime
    roles: list[str] = []
    skills: list[UserSkillOut] = []

    @classmethod
    def from_model(cls, user) -> "UserOut":
        return cls(
            id=user.id,
            code=user.code,
            email=user.email,
            full_name=user.full_name,
            designation=user.designation,
            department=user.department,
            phone=user.phone,
            is_active=user.is_active,
            reports_to_id=user.reports_to_id,
            standard_daily_hours=float(user.standard_daily_hours or 0),
            working_days_per_week=user.working_days_per_week,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
            roles=sorted(user.role_names),
            skills=[
                UserSkillOut(
                    skill_id=us.skill_id,
                    name=us.skill.name if us.skill else None,
                    category=us.skill.category if us.skill else None,
                    level=us.level,
                    level_rank=us.level_rank,
                    years_experience=(
                        float(us.years_experience)
                        if us.years_experience is not None
                        else None
                    ),
                )
                for us in user.skills
            ],
        )


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    full_name: str = Field(min_length=1, max_length=160)
    designation: str | None = None
    department: str | None = None
    phone: str | None = None
    roles: list[str] = Field(min_length=1)
    reports_to_id: uuid.UUID | None = None
    standard_daily_hours: float = Field(8.0, gt=0, le=24)
    working_days_per_week: int = Field(5, ge=1, le=7)


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=160)
    designation: str | None = None
    department: str | None = None
    phone: str | None = None
    is_active: bool | None = None
    roles: list[str] | None = None
    reports_to_id: uuid.UUID | None = None
    standard_daily_hours: float | None = Field(None, gt=0, le=24)
    working_days_per_week: int | None = Field(None, ge=1, le=7)


class SkillOut(ORMModel):
    id: uuid.UUID
    name: str
    category: str | None = None
    description: str | None = None
    is_active: bool


class SkillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str | None = None
    description: str | None = None


class UserSkillAssign(BaseModel):
    skill_id: uuid.UUID
    level: str = SkillLevel.INTERMEDIATE.value
    years_experience: float | None = Field(None, ge=0, le=60)

    @field_validator("level")
    @classmethod
    def _known_level(cls, value: str) -> str:
        if value not in SKILL_LEVEL_RANK:
            raise ValueError(
                f"level must be one of {', '.join(SKILL_LEVEL_RANK)}"
            )
        return value


class LeaveCreate(BaseModel):
    user_id: uuid.UUID
    start_date: date
    end_date: date
    leave_type: str = "Planned"
    hours_per_day: float = Field(8.0, gt=0, le=24)
    reason: str | None = None

    @field_validator("end_date")
    @classmethod
    def _order(cls, value: date, info) -> date:
        start = info.data.get("start_date")
        if start and value < start:
            raise ValueError("end_date cannot be before start_date")
        return value


class LeaveOut(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    start_date: date
    end_date: date
    leave_type: str
    hours_per_day: float
    status: str
    reason: str | None = None


class HolidayCreate(BaseModel):
    holiday_date: date
    name: str = Field(min_length=1, max_length=120)
    region: str = "ALL"


class HolidayOut(ORMModel):
    id: uuid.UUID
    holiday_date: date
    name: str
    region: str


class CapacityOverride(BaseModel):
    user_id: uuid.UUID
    capacity_date: date
    available_hours: float = Field(ge=0, le=24)
    note: str | None = None


class CapacityDay(BaseModel):
    date: str
    available: float
    allocated: float
    utilization_percent: float | None = None


class CapacitySummary(BaseModel):
    user_id: str
    code: str | None = None
    full_name: str
    designation: str | None = None
    period_start: str
    period_end: str
    available_hours: float
    allocated_hours: float
    logged_hours: float
    utilization_percent: float | None = None
    utilization_band: str
    open_tasks: int
    next_deadline: str | None = None
    skills: list[dict] = []
    daily: list[CapacityDay] = []
    has_required_skill: bool | None = None
    skill_rank: int | None = None
    headroom_hours: float | None = None
