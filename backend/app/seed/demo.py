"""Realistic demonstration data (spec section 40).

The point of this script is not to fill tables -- it is to produce a
department whose dashboards are worth looking at. It therefore drives the real
services (assignment, time logging, review, revision, roll-up) rather than
inserting finished-looking rows, so every number a dashboard shows was
actually produced by the workflow that the application enforces.

The generated department deliberately contains:

* projects that are on track, projects that are late, and projects finished
* designers who are overloaded and designers with spare capacity
* rework, both controllable and customer-driven
* blocked tasks, pending reviews and open revisions

Deterministic: the same seed produces the same department every time, so
screenshots and tests stay stable.
"""

from __future__ import annotations

import random
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    Priority,
    ProjectStatus,
    ReleaseStatus,
    ReviewResult,
    SkillLevel,
    TaskStatus,
)
from app.core.security import hash_password
from app.models.catalog import Customer, Product, ProductFamily
from app.models.execution import Review, Revision
from app.models.project import Project, ProjectMember
from app.models.release import DesignRelease
from app.models.task import Task
from app.models.template import DesignTemplate, DesignTemplateVersion, TemplateTask
from app.models.user import Holiday, LeaveRecord, Role, Skill, User, UserRole, UserSkill
from app.services import (
    code_service,
    health_service,
    kpi,
    release_service,
    review_service,
    rollup_service,
    task_service,
    template_service,
    time_service,
)

RNG = random.Random(20260818)
TODAY = date.today()

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

SKILLS = [
    ("CAD Modelling", "Technical"),
    ("Mechanical Design", "Technical"),
    ("Electrical Design", "Technical"),
    ("Structural Design", "Technical"),
    ("BOM Preparation", "Technical"),
    ("Simulation / FEA", "Technical"),
    ("Documentation", "Process"),
    ("Manufacturing Drawings", "Technical"),
    ("Automated Parking Systems", "Product"),
    ("Control Systems", "Technical"),
]

FAMILIES = [
    ("Automated Parking Systems", "Fully automated multi-level parking solutions"),
    ("Semi-Automatic Parking", "Operator-assisted stacker and puzzle systems"),
    ("Storage & Retrieval", "Automated storage and retrieval systems"),
]

PRODUCTS = [
    ("Tower Parking System", 0),
    ("Puzzle Parking System", 0),
    ("Automated Guided Vehicle Parking", 0),
    ("Two-Post Stacker", 1),
    ("Automated Storage & Retrieval System", 2),
]

CUSTOMERS = [
    ("Meridian Infra Developers", "CUST-MID", "Real Estate", "India"),
    ("Harbour Point Realty", "CUST-HPR", "Real Estate", "India"),
    ("Nordwind Logistik GmbH", "CUST-NWL", "Logistics", "Germany"),
    ("Calibre Hospitality Group", "CUST-CHG", "Hospitality", "UAE"),
    ("Vertex Industrial Parks", "CUST-VIP", "Industrial", "India"),
    ("Southbank Medical Trust", "CUST-SMT", "Healthcare", "Singapore"),
]

# (release type, [(task name, type, hours, skill index, complexity, mandatory,
#                  requires review, depends on previous)])
TEMPLATE_LIBRARY: list[tuple[str, list[tuple]]] = [
    (
        "Concept / Layout",
        [
            ("Site Survey Review", "Coordination", 6, 8, 2, True, False, False),
            ("Concept Layout", "Layout", 16, 1, 3, True, True, True),
            ("Capacity Calculation", "Calculation", 8, 1, 3, True, True, True),
            ("Concept Presentation", "Documentation", 6, 6, 2, True, True, True),
            ("Internal Concept Review", "Checking", 4, 6, 2, True, True, True),
        ],
    ),
    (
        "Mechanical Design",
        [
            ("GA Drawing", "Drawing", 20, 0, 4, True, True, False),
            ("Structural Layout", "Layout", 16, 3, 4, True, True, True),
            ("Component Placement", "Modelling", 14, 0, 3, True, True, True),
            ("Assembly Drawing", "Drawing", 18, 0, 4, True, True, True),
            ("Fabrication Drawing", "Drawing", 22, 7, 4, True, True, True),
            ("Mechanical BOM", "BOM", 10, 4, 2, True, True, True),
            ("Internal Checking", "Checking", 8, 6, 2, True, True, True),
            ("Final Release Pack", "Documentation", 6, 6, 2, True, True, True),
        ],
    ),
    (
        "Electrical Design",
        [
            ("Power Distribution Schematic", "Drawing", 14, 2, 4, True, True, False),
            ("Control Panel Layout", "Layout", 12, 9, 3, True, True, True),
            ("Cable Schedule", "Documentation", 8, 2, 2, True, True, True),
            ("Electrical BOM", "BOM", 8, 4, 2, True, True, True),
            ("Interlock Logic Review", "Checking", 6, 9, 3, True, True, True),
        ],
    ),
    (
        "Detailed Design",
        [
            ("Detailed Part Modelling", "Modelling", 24, 0, 4, True, True, False),
            ("Structural Verification", "Simulation", 16, 5, 5, True, True, True),
            ("Tolerance Study", "Calculation", 10, 1, 4, False, True, True),
            ("Detail Drawings", "Drawing", 26, 7, 4, True, True, True),
            ("Design Checking", "Checking", 10, 6, 3, True, True, True),
        ],
    ),
    (
        "Manufacturing Drawing",
        [
            ("Weldment Drawings", "Drawing", 18, 7, 4, True, True, False),
            ("Machining Drawings", "Drawing", 16, 7, 4, True, True, True),
            ("Surface Treatment Spec", "Documentation", 6, 6, 2, False, False, False),
            ("Manufacturing BOM", "BOM", 10, 4, 3, True, True, True),
            ("Drawing Release Check", "Checking", 6, 6, 2, True, True, True),
        ],
    ),
]

DESIGNERS = [
    ("Arun Prakash", "Senior Design Engineer", [0, 1, 8], 8.0),
    ("Meera Iyer", "Design Engineer", [0, 1, 7], 8.0),
    ("Rohit Nair", "Senior Design Engineer", [3, 5, 1], 8.0),
    ("Kavya Ramesh", "Design Engineer", [0, 4, 6], 8.0),
    ("Sandeep Rao", "Electrical Design Engineer", [2, 9, 4], 8.0),
    ("Priya Menon", "Design Engineer", [0, 7, 6], 7.0),
    ("Vikram Shetty", "Senior Design Engineer", [1, 3, 5], 8.0),
    ("Anjali Deshpande", "Design Engineer", [0, 6, 4], 8.0),
    ("Farhan Qureshi", "Electrical Design Engineer", [2, 9, 6], 8.0),
    ("Divya Krishnan", "Junior Design Engineer", [0, 6], 8.0),
]

LEADS = [
    ("Suresh Balan", "Mechanical Design Lead", [1, 0, 3]),
    ("Nithya Raghavan", "Detailing Lead", [7, 0, 4]),
    ("Imran Sheikh", "Electrical Design Lead", [2, 9, 5]),
]

# (name, customer index, product index, offset from today for start,
#  duration days, intended outcome)
PROJECT_PLAN = [
    ("Meridian Tower Parking - Phase 1", 0, 0, -150, 120, "completed"),
    ("Harbour Point Puzzle Parking", 1, 1, -120, 110, "completed"),
    ("Nordwind Logistics ASRS Retrofit", 2, 4, -95, 130, "late"),
    ("Calibre Hotel Valet Automation", 3, 2, -80, 105, "late"),
    ("Vertex Industrial Stacker Bank", 4, 3, -70, 90, "on_track"),
    ("Southbank Medical Staff Parking", 5, 1, -55, 95, "on_track"),
    ("Meridian Tower Parking - Phase 2", 0, 0, -40, 120, "on_track"),
    ("Harbour Point Basement Extension", 1, 0, -30, 100, "at_risk"),
    ("Nordwind Depot Expansion", 2, 4, -20, 110, "planning"),
    ("Vertex Warehouse AGV Pilot", 4, 2, -10, 90, "planning"),
]

HOLIDAYS = [
    (date(TODAY.year, 1, 26), "Republic Day"),
    (date(TODAY.year, 8, 15), "Independence Day"),
    (date(TODAY.year, 10, 2), "Gandhi Jayanti"),
    (date(TODAY.year, 12, 25), "Christmas"),
]


def _email(full_name: str) -> str:
    first, _, last = full_name.partition(" ")
    return f"{first.lower()}.{last.split()[-1].lower()}@designops.dev"


class _TimeCursor:
    """Hands out non-overlapping working intervals per person.

    The time service rejects overlapping entries and future dates, which are
    exactly the rules we want exercised -- so the seed has to schedule like a
    real timesheet: a bounded number of hours per person per working day, and
    spill onto another day once a day is full rather than running past
    midnight into the next one's slot.
    """

    #: A person books at most this many hours to one day.
    DAILY_CAP = 10.0

    def __init__(self) -> None:
        self._used: dict[tuple[uuid.UUID, date], float] = defaultdict(float)

    def take(
        self, user_id: uuid.UUID, preferred_day: date, hours: float
    ) -> tuple[date, datetime, datetime]:
        day = self._find_day(user_id, preferred_day, hours)
        used = self._used[(user_id, day)]
        start = datetime.combine(day, time(9, 0), tzinfo=UTC) + timedelta(hours=used)
        end = start + timedelta(hours=hours)
        self._used[(user_id, day)] = used + hours
        return day, start, end

    def _find_day(self, user_id: uuid.UUID, preferred: date, hours: float) -> date:
        def fits(day: date) -> bool:
            return (
                day.weekday() < 5
                and self._used[(user_id, day)] + hours <= self.DAILY_CAP
            )

        # Prefer the requested day, then later days -- but never the future.
        day = preferred
        while day <= TODAY:
            if fits(day):
                return day
            day += timedelta(days=1)

        # The forward window is full, so fall back to earlier days.
        day = preferred - timedelta(days=1)
        for _ in range(400):
            if fits(day):
                return day
            day -= timedelta(days=1)
        return preferred


def _make_user(
    db: Session,
    *,
    full_name: str,
    designation: str,
    role: Role,
    password: str,
    reports_to: User | None = None,
    daily_hours: float = 8.0,
) -> User:
    user = User(
        code=code_service.next_code(db, "user"),
        email=_email(full_name),
        hashed_password=hash_password(password),
        full_name=full_name,
        designation=designation,
        department="Design",
        standard_daily_hours=daily_hours,
        reports_to_id=reports_to.id if reports_to else None,
    )
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id, is_primary=True))
    db.flush()
    return user


def _publish_template(
    db: Session,
    *,
    name: str,
    release_type: str,
    rows: list[tuple],
    skills: list[Skill],
    product: Product | None,
    family: ProductFamily | None,
    author: User,
) -> DesignTemplateVersion:
    template = DesignTemplate(
        code=code_service.next_code(db, "template"),
        name=name,
        description=f"Standard {release_type} sequence.",
        release_type=release_type,
        product_id=product.id if product else None,
        product_family_id=family.id if family else None,
        created_by_id=author.id,
    )
    db.add(template)
    db.flush()

    version = DesignTemplateVersion(
        template_id=template.id, version_number=1, is_published=False
    )
    db.add(version)
    db.flush()

    for index, (
        task_name,
        task_type,
        hours,
        skill_index,
        complexity,
        mandatory,
        review,
        depends,
    ) in enumerate(rows, start=1):
        db.add(
            TemplateTask(
                version_id=version.id,
                sequence=index,
                name=task_name,
                task_type=task_type,
                default_estimated_hours=hours,
                default_priority=(
                    Priority.HIGH.value if complexity >= 4 else Priority.MEDIUM.value
                ),
                complexity=complexity,
                required_skill_id=skills[skill_index].id,
                is_mandatory=mandatory,
                requires_review=review,
                depends_on_sequence=index - 1 if depends and index > 1 else None,
            )
        )
    db.flush()
    db.refresh(version)
    template_service.publish_version(db, version, actor=author)
    return version


def run(db: Session, *, password: str = "Design@123") -> dict:
    if db.execute(select(Project.id).limit(1)).first():
        return {"skipped": "Demo data already present; nothing seeded."}

    roles = {r.name: r for r in db.execute(select(Role)).scalars()}
    stats: dict[str, int] = {}

    # -- reference data ---------------------------------------------------
    skills = []
    for skill_name, category in SKILLS:
        skill = Skill(name=skill_name, category=category)
        db.add(skill)
        skills.append(skill)
    db.flush()

    families = []
    for family_name, description in FAMILIES:
        family = ProductFamily(
            code=code_service.next_code(db, "product_family"),
            name=family_name,
            description=description,
        )
        db.add(family)
        families.append(family)
    db.flush()

    products = []
    for product_name, family_index in PRODUCTS:
        product = Product(
            code=code_service.next_code(db, "product"),
            name=product_name,
            product_family_id=families[family_index].id,
        )
        db.add(product)
        products.append(product)
    db.flush()

    customers = []
    for name, customer_code, industry, country in CUSTOMERS:
        customer = Customer(
            code=code_service.next_code(db, "customer"),
            name=name,
            customer_code=customer_code,
            industry=industry,
            country=country,
            contact_name="Procurement Desk",
            contact_email=f"projects@{customer_code.lower().replace(chr(45), chr(46))}.example.com",
        )
        db.add(customer)
        customers.append(customer)
    db.flush()

    for holiday_date, holiday_name in HOLIDAYS:
        db.add(Holiday(holiday_date=holiday_date, name=holiday_name, region="ALL"))
    db.flush()

    # -- people -----------------------------------------------------------
    director = _make_user(
        db,
        full_name="Rajesh Varma",
        designation="Director - Engineering",
        role=roles["Director"],
        password=password,
    )
    manager = _make_user(
        db,
        full_name="Lakshmi Subramanian",
        designation="Design Manager",
        role=roles["Design Manager"],
        password=password,
        reports_to=director,
    )

    leads: list[User] = []
    for full_name, designation, skill_indexes in LEADS:
        lead = _make_user(
            db,
            full_name=full_name,
            designation=designation,
            role=roles["Team Lead"],
            password=password,
            reports_to=manager,
        )
        for rank, skill_index in enumerate(skill_indexes):
            db.add(
                UserSkill(
                    user_id=lead.id,
                    skill_id=skills[skill_index].id,
                    level=SkillLevel.EXPERT.value if rank == 0 else SkillLevel.ADVANCED.value,
                    level_rank=4 if rank == 0 else 3,
                    years_experience=10 - rank,
                )
            )
        leads.append(lead)
    db.flush()

    designers: list[User] = []
    for index, (full_name, designation, skill_indexes, daily_hours) in enumerate(DESIGNERS):
        lead = leads[index % len(leads)]
        designer = _make_user(
            db,
            full_name=full_name,
            designation=designation,
            role=roles["Designer"],
            password=password,
            reports_to=lead,
            daily_hours=daily_hours,
        )
        for rank, skill_index in enumerate(skill_indexes):
            level, level_rank = (
                (SkillLevel.ADVANCED.value, 3)
                if rank == 0
                else (SkillLevel.INTERMEDIATE.value, 2)
            )
            if "Junior" in designation:
                level, level_rank = SkillLevel.BEGINNER.value, 1
            db.add(
                UserSkill(
                    user_id=designer.id,
                    skill_id=skills[skill_index].id,
                    level=level,
                    level_rank=level_rank,
                    years_experience=max(6 - rank * 2, 1),
                )
            )
        designers.append(designer)
    db.flush()

    # Two designers carry planned leave, so available hours differ from the
    # baseline and the capacity engine has something real to subtract.
    db.add(
        LeaveRecord(
            user_id=designers[5].id,
            start_date=TODAY + timedelta(days=3),
            end_date=TODAY + timedelta(days=7),
            leave_type="Planned",
            hours_per_day=8,
            status="Approved",
            reason="Annual leave",
        )
    )
    db.add(
        LeaveRecord(
            user_id=designers[9].id,
            start_date=TODAY + timedelta(days=1),
            end_date=TODAY + timedelta(days=2),
            leave_type="Sick",
            hours_per_day=8,
            status="Approved",
        )
    )
    db.flush()

    stats["users"] = 2 + len(leads) + len(designers)

    # -- templates --------------------------------------------------------
    versions: dict[str, DesignTemplateVersion] = {}
    for release_type, rows in TEMPLATE_LIBRARY:
        family = families[0] if release_type != "Detailed Design" else None
        product = products[0] if release_type == "Detailed Design" else None
        versions[release_type] = _publish_template(
            db,
            name=f"{release_type} - Standard",
            release_type=release_type,
            rows=rows,
            skills=skills,
            product=product,
            family=family if product is None else None,
            author=manager,
        )

    # A second published version, so the UI has real version history and
    # releases generated from v1 demonstrably keep pointing at v1.
    mech_template = db.get(DesignTemplate, versions["Mechanical Design"].template_id)
    draft = template_service.create_draft_version(
        db, mech_template, actor=manager, change_note="Added a dedicated weld check step"
    )
    db.add(
        TemplateTask(
            version_id=draft.id,
            sequence=len(TEMPLATE_LIBRARY[1][1]) + 1,
            name="Weld Verification",
            task_type="Checking",
            default_estimated_hours=6,
            default_priority=Priority.MEDIUM.value,
            complexity=3,
            required_skill_id=skills[3].id,
            is_mandatory=False,
            requires_review=True,
        )
    )
    db.flush()
    db.refresh(draft)
    template_service.publish_version(db, draft, actor=manager)
    stats["templates"] = len(TEMPLATE_LIBRARY)
    stats["template_versions"] = len(TEMPLATE_LIBRARY) + 1

    # -- projects, releases, tasks ---------------------------------------
    cursor = _TimeCursor()
    counters = {"projects": 0, "releases": 0, "tasks": 0, "time_entries": 0,
                "reviews": 0, "revisions": 0}

    release_types = [rt for rt, _ in TEMPLATE_LIBRARY]

    for (
        project_name,
        customer_index,
        product_index,
        start_offset,
        duration,
        outcome,
    ) in PROJECT_PLAN:
        # Release windows are laid out backwards from where this project's
        # last release should land, so the staged outcome is a property of the
        # schedule rather than something patched on afterwards.
        release_count = 3 if outcome == "planning" else RNG.randint(2, 3)
        windows = _release_windows(outcome, release_count)
        start = windows[0][0]
        required = windows[-1][1] + timedelta(days=RNG.randint(5, 12))
        if outcome == "late":
            required = TODAY - timedelta(days=RNG.randint(4, 15))

        project = Project(
            code=code_service.next_code(db, "project"),
            name=project_name,
            description=f"Design scope for {project_name}.",
            customer_id=customers[customer_index].id,
            product_id=products[product_index].id,
            project_type=RNG.choice(["New Product", "Customisation", "Repeat Order"]),
            sales_order=f"SO-{RNG.randint(10000, 99999)}",
            work_order=f"WO-{RNG.randint(10000, 99999)}",
            design_manager_id=manager.id,
            project_manager_id=manager.id,
            priority=(
                Priority.CRITICAL.value
                if outcome == "late"
                else RNG.choice([Priority.HIGH.value, Priority.MEDIUM.value])
            ),
            start_date=start,
            required_completion_date=required,
            internal_deadline=required - timedelta(days=7),
            customer_deadline=required,
            status=ProjectStatus.DESIGN_IN_PROGRESS.value,
            created_by_id=manager.id,
        )
        db.add(project)
        db.flush()
        counters["projects"] += 1

        chosen_types = release_types[:release_count]

        # Earlier releases in the sequence are finished; only the release the
        # department is currently working on is partially done. A project whose
        # first release is still half-open would read as catastrophically late
        # no matter what outcome we intended.
        trailing_share = {
            "completed": 1.0,
            "late": 0.5,
            "on_track": 0.55,
            "at_risk": 0.35,
            "planning": 0.0,
        }[outcome]

        # Phase one: lay out the whole design sequence before any of it is
        # executed. This mirrors how a manager works, and it matters
        # mechanically: completing a release auto-completes its project once
        # every release is closed, so creating and finishing release one
        # before release two exists would close the project immediately.
        planned_releases: list[tuple[DesignRelease, list, User, float]] = []
        for sequence, release_type in enumerate(chosen_types, start=1):
            version = versions[release_type]
            release_start, planned_end = windows[sequence - 1]
            is_last = sequence == release_count
            completed_share = trailing_share if is_last else 1.0
            lead = leads[(sequence - 1) % len(leads)]

            release = DesignRelease(
                code=code_service.next_code(db, "release"),
                project_id=project.id,
                sequence_number=sequence,
                name=f"DR-{sequence:03d} {release_type}",
                release_type=release_type,
                product_id=project.product_id,
                priority=project.priority,
                planned_start=release_start,
                planned_end=planned_end,
                status=ReleaseStatus.DRAFT.value,
                created_by_id=manager.id,
            )
            db.add(release)
            db.flush()
            counters["releases"] += 1

            release_service.assign_team_lead(db, release, lead, actor=manager)
            tasks = template_service.generate_tasks_for_release(
                db, release, version, actor=manager
            )
            counters["tasks"] += len(tasks)
            planned_releases.append((release, tasks, lead, completed_share))

        if outcome == "planning":
            for designer in designers[:4]:
                db.add(ProjectMember(project_id=project.id, user_id=designer.id))
            project.status = ProjectStatus.PLANNING.value
            db.flush()
            rollup_service.refresh_project(db, project)
            continue

        # Phase two: execute the sequence in order.
        for release, tasks, lead, completed_share in planned_releases:
            planned_end = release.planned_end
            release_service.transition(
                db, release, ReleaseStatus.PLANNING.value, actor=lead
            )
            release_service.transition(
                db, release, ReleaseStatus.IN_PROGRESS.value, actor=lead
            )

            team = [d for d in designers if d.reports_to_id == lead.id] or designers
            finish_count = int(len(tasks) * completed_share)

            for index, task in enumerate(tasks):
                designer = team[index % len(team)]
                task_service.assign(db, task, designer, actor=lead)

                if index < finish_count:
                    _drive_task_to_done(
                        db,
                        task=task,
                        designer=designer,
                        reviewer=lead,
                        cursor=cursor,
                        outcome=outcome,
                        counters=counters,
                    )
                    # The services stamp "now", which would make every task
                    # look like it was started and finished today. Rewrite the
                    # lifecycle to the schedule so cycle time, review
                    # turnaround and on-time delivery are real numbers.
                    _backdate_task(db, task=task, outcome=outcome)
                elif index == finish_count and outcome in {"late", "at_risk"}:
                    _leave_task_blocked(db, task=task, designer=designer)
                elif index == finish_count and outcome == "on_track":
                    _leave_task_in_review(
                        db,
                        task=task,
                        designer=designer,
                        reviewer=lead,
                        cursor=cursor,
                        counters=counters,
                    )
                elif index == finish_count + 1:
                    _leave_task_in_progress(
                        db, task=task, designer=designer, cursor=cursor, counters=counters
                    )

            # Every release except the one in flight is genuinely finished, so
            # the sequence reads as a project that has progressed rather than
            # one that stalled at release one.
            if completed_share >= 1.0:
                release_service.complete(
                    db,
                    release,
                    actor=manager,
                    can_override=True,
                    override_reason="Seeded historical release",
                )
                release.actual_end = min(
                    planned_end + timedelta(days=RNG.randint(-3, 4)), TODAY
                )

        for designer in designers[:4]:
            db.add(ProjectMember(project_id=project.id, user_id=designer.id))

        if outcome == "completed":
            # Completing the final release already closed the project through
            # the normal workflow; only the delivery date needs stating.
            project.actual_completion_date = min(
                required - timedelta(days=RNG.randint(1, 6)), TODAY
            )
        else:
            project.status = ProjectStatus.DESIGN_IN_PROGRESS.value
            project.actual_completion_date = None

        db.flush()
        rollup_service.refresh_project(db, project)

    # -- final recomputation ---------------------------------------------
    health_service.sweep_delays(db)
    for project in db.execute(select(Project)).scalars():
        rollup_service.refresh_project(db, project)

    stats.update(counters)
    stats["skills"] = len(SKILLS)
    stats["customers"] = len(CUSTOMERS)
    stats["products"] = len(PRODUCTS)
    return stats


# ---------------------------------------------------------------------------
# Task lifecycle helpers
# ---------------------------------------------------------------------------


def _log(
    db: Session,
    *,
    task: Task,
    designer: User,
    cursor: _TimeCursor,
    hours: float,
    day: date,
    counters: dict,
    description: str,
) -> None:
    entry_day, started_at, ended_at = cursor.take(designer.id, day, hours)
    time_service.log_manual(
        db,
        task=task,
        user=designer,
        entry_date=entry_day,
        hours=round(hours, 2),
        description=description,
        started_at=started_at,
        ended_at=ended_at,
        actor=designer,
    )
    counters["time_entries"] += 1


def _release_windows(outcome: str, count: int) -> list[tuple[date, date]]:
    """Lay out a project's release windows backwards from its final deadline.

    Anchoring on the *last* release is what makes the staged outcome hold: an
    on-track project's current release ends comfortably in the future, an
    at-risk one ends within days, and a late one has already missed.
    """
    if outcome == "planning":
        # Nothing has started yet, so the sequence is laid out forwards from a
        # future kickoff. Anchoring it backwards would leave a project that has
        # not begun holding releases that are already overdue.
        windows: list[tuple[date, date]] = []
        cursor = TODAY + timedelta(days=RNG.randint(5, 15))
        for _ in range(count):
            span = RNG.randint(24, 32)
            windows.append((cursor, cursor + timedelta(days=span)))
            cursor = cursor + timedelta(days=span + 3)
        return windows

    last_end = TODAY + timedelta(
        days={
            "completed": -RNG.randint(6, 25),
            "late": -RNG.randint(3, 12),
            "at_risk": RNG.randint(3, 7),
            "on_track": RNG.randint(18, 35),
        }[outcome]
    )

    windows: list[tuple[date, date]] = []
    end = last_end
    for _ in range(count):
        span = RNG.randint(24, 32)
        windows.insert(0, (end - timedelta(days=span), end))
        end = end - timedelta(days=span + 3)
    return windows


def _backdate_task(db: Session, *, task: Task, outcome: str) -> None:
    """Rewrite a completed task's lifecycle stamps onto its planned schedule.

    The workflow services stamp `datetime.now()`, which is correct in
    production and useless in a seed -- every task would show a cycle time of
    zero and a completion date of today. Rewriting the stamps afterwards is
    the only way to produce a believable history without faking the rows
    themselves, so the work really did go through the workflow and only the
    clock is adjusted.
    """
    if task.completed_at is None or task.planned_end is None:
        return

    drift = {
        "completed": RNG.randint(-4, 1),
        "on_track": RNG.randint(-3, 2),
        "at_risk": RNG.randint(-1, 5),
        "late": RNG.randint(3, 12),
    }.get(outcome, 0)
    finish = min(task.planned_end + timedelta(days=drift), TODAY)
    finish_dt = datetime.combine(finish, time(17, 0), tzinfo=UTC)

    reviews = (
        db.execute(
            select(Review)
            .where(Review.task_id == task.id)
            .order_by(Review.round_number)
        )
        .scalars()
        .all()
    )

    # The window has to be long enough to fit every review round before
    # completion, or a submission would land before the task started.
    estimated = float(task.estimated_hours or 8)
    cycle_days = max(int(estimated / 6), 1) + RNG.randint(0, 3) + 2 * len(reviews)

    start_dt = finish_dt - timedelta(days=cycle_days, hours=RNG.randint(0, 6))
    task.started_at = start_dt
    task.assigned_at = start_dt - timedelta(days=RNG.randint(1, 4))
    task.completed_at = finish_dt

    rounds = len(reviews)
    for index, review in enumerate(reviews):
        submitted = finish_dt - timedelta(
            days=(rounds - index) * 2, hours=RNG.randint(1, 6)
        )
        started = submitted + timedelta(hours=RNG.uniform(1, 10))
        reviewed = min(started + timedelta(hours=RNG.uniform(1, 20)), finish_dt)
        review.submitted_at = submitted
        review.review_started_at = started
        review.reviewed_at = reviewed
        review.turnaround_hours = kpi.review_turnaround_hours(submitted, reviewed)

    if reviews:
        task.submitted_at = reviews[-1].submitted_at

    for revision in db.execute(
        select(Revision).where(Revision.task_id == task.id)
    ).scalars():
        revision.raised_date = reviews[0].reviewed_at if reviews else start_dt
        if revision.resolved_date is not None:
            revision.resolved_date = finish_dt

    db.flush()


def _log_spread(
    db: Session,
    *,
    task: Task,
    designer: User,
    cursor: _TimeCursor,
    total_hours: float,
    start_offset: int,
    counters: dict,
    description: str,
) -> None:
    """Log `total_hours` as several realistic sittings across working days.

    Nobody books a 24-hour task as one entry, and the time service rejects it
    anyway, so effort is broken into 3-7 hour sittings walking forward in time.
    """
    remaining = round(total_hours, 2)
    offset = start_offset
    guard = 0
    while remaining > 0.01 and guard < 40:
        chunk = round(min(remaining, RNG.uniform(3, 7)), 2)
        _log(
            db,
            task=task,
            designer=designer,
            cursor=cursor,
            hours=chunk,
            day=_work_day(offset),
            counters=counters,
            description=description,
        )
        remaining = round(remaining - chunk, 2)
        offset = max(offset - 1, 1)
        guard += 1


def _ensure_delay_reason(task: Task) -> None:
    """Attach a delay reason to an overdue task before it moves on.

    The workflow refuses to advance an overdue task without one, so the seed
    has to supply it exactly as a designer would in the UI.
    """
    if task.planned_end and task.planned_end < TODAY and not task.delay_reason:
        task.delay_reason = RNG.choice(
            ["Resource Constraint", "Waiting for Input", "Technical Issue", "Rework"]
        )


def _work_day(offset_back: int) -> date:
    """A recent working day, `offset_back` days ago, skipping weekends."""
    day = TODAY - timedelta(days=offset_back)
    while day.weekday() > 4:
        day -= timedelta(days=1)
    return day


def _drive_task_to_done(
    db: Session,
    *,
    task: Task,
    designer: User,
    reviewer: User,
    cursor: _TimeCursor,
    outcome: str,
    counters: dict,
) -> None:
    """Run one task through the full execute -> review -> approve loop."""
    estimated = float(task.estimated_hours or 8)

    # Efficiency varies by project outcome, so the dashboards show a spread
    # rather than every task landing exactly on estimate.
    factor = {
        "completed": RNG.uniform(0.85, 1.05),
        "late": RNG.uniform(1.1, 1.45),
        "on_track": RNG.uniform(0.9, 1.1),
        "at_risk": RNG.uniform(1.05, 1.3),
    }.get(outcome, 1.0)
    actual = max(round(estimated * factor, 1), 0.5)

    if task_service.blocking_prerequisites(db, task):
        return
    task_service.transition(db, task, TaskStatus.IN_PROGRESS.value, actor=designer)

    _log_spread(
        db,
        task=task,
        designer=designer,
        cursor=cursor,
        total_hours=actual,
        start_offset=RNG.randint(10, 40),
        counters=counters,
        description=f"Work on {task.name}",
    )

    # An overdue task must carry a reason before it can move on -- the same
    # rule the UI enforces.
    _ensure_delay_reason(task)

    if not task.requires_review:
        task_service.transition(db, task, TaskStatus.COMPLETED.value, actor=designer)
        return

    review = review_service.submit_for_review(
        db, task=task, actor=designer, reviewer_id=reviewer.id
    )
    counters["reviews"] += 1
    review_service.start_review(db, review=review, actor=reviewer)

    needs_rework = RNG.random() < {
        "completed": 0.18,
        "late": 0.45,
        "on_track": 0.2,
        "at_risk": 0.4,
    }.get(outcome, 0.2)

    if not needs_rework:
        review_service.complete_review(
            db,
            review=review,
            actor=reviewer,
            result=ReviewResult.APPROVED.value,
            comments="Approved.",
        )
        return

    category, root_cause = RNG.choice(
        [
            ("Design Error", "Incorrect clearance assumption"),
            ("Customer Change", "Customer revised the bay layout"),
            ("Missing Information", "Civil drawing was not final at start"),
            ("Internal Review", "Drafting standard not followed"),
            ("Scope Change", "Additional level added to scope"),
        ]
    )
    _, revision = review_service.complete_review(
        db,
        review=review,
        actor=reviewer,
        result=ReviewResult.REVISION_REQUESTED.value,
        comments="Returned for correction.",
        revision_category=category,
        revision_reason=f"{category}: rework required before release.",
        root_cause=root_cause,
    )
    counters["revisions"] += 1

    # Rework: logged while the revision is open, so it is counted as rework
    # automatically rather than being flagged by hand.
    rework_hours = round(max(estimated * RNG.uniform(0.15, 0.4), 1.0), 1)
    _ensure_delay_reason(task)
    task_service.transition(db, task, TaskStatus.IN_PROGRESS.value, actor=designer)
    _log_spread(
        db,
        task=task,
        designer=designer,
        cursor=cursor,
        total_hours=rework_hours,
        start_offset=RNG.randint(2, 9),
        counters=counters,
        description=f"Rework - {category}",
    )

    second = review_service.submit_for_review(
        db, task=task, actor=designer, reviewer_id=reviewer.id
    )
    counters["reviews"] += 1
    review_service.start_review(db, review=second, actor=reviewer)
    review_service.complete_review(
        db,
        review=second,
        actor=reviewer,
        result=ReviewResult.APPROVED.value,
        comments="Rework verified and approved.",
    )
    # Most revisions get closed out, but some stay open -- closing the record
    # lags the actual rework in practice, and the revision queue should not
    # look permanently empty.
    if revision is not None and RNG.random() > 0.3:
        review_service.resolve_revision(db, revision=revision, actor=reviewer)


def _leave_task_blocked(db: Session, *, task: Task, designer: User) -> None:
    if task_service.blocking_prerequisites(db, task):
        return
    task_service.transition(db, task, TaskStatus.IN_PROGRESS.value, actor=designer)
    task_service.transition(
        db,
        task,
        TaskStatus.BLOCKED.value,
        actor=designer,
        note=RNG.choice(
            [
                "Awaiting final civil drawing from the customer.",
                "Waiting on approval of the structural loading assumption.",
                "Vendor has not confirmed the drive unit envelope.",
            ]
        ),
    )


def _leave_task_in_review(
    db: Session,
    *,
    task: Task,
    designer: User,
    reviewer: User,
    cursor: _TimeCursor,
    counters: dict,
) -> None:
    if task_service.blocking_prerequisites(db, task):
        return
    task_service.transition(db, task, TaskStatus.IN_PROGRESS.value, actor=designer)
    _log_spread(
        db,
        task=task,
        designer=designer,
        cursor=cursor,
        total_hours=round(float(task.estimated_hours or 8) * 0.9, 1),
        start_offset=RNG.randint(3, 8),
        counters=counters,
        description=f"Work on {task.name}",
    )
    if task.requires_review:
        _ensure_delay_reason(task)
        review_service.submit_for_review(
            db, task=task, actor=designer, reviewer_id=reviewer.id
        )
        counters["reviews"] += 1


def _leave_task_in_progress(
    db: Session, *, task: Task, designer: User, cursor: _TimeCursor, counters: dict
) -> None:
    # If an upstream task is still blocked or open, this one genuinely cannot
    # start -- leaving it Assigned is the honest state, and it is what the
    # bottleneck report is meant to surface.
    if task_service.blocking_prerequisites(db, task):
        return
    task_service.transition(db, task, TaskStatus.IN_PROGRESS.value, actor=designer)
    hours = round(float(task.estimated_hours or 8) * RNG.uniform(0.3, 0.6), 1)
    _log_spread(
        db,
        task=task,
        designer=designer,
        cursor=cursor,
        total_hours=hours,
        start_offset=RNG.randint(2, 6),
        counters=counters,
        description=f"In progress - {task.name}",
    )
    task.completion_percent = round(RNG.uniform(30, 70), 2)
    db.flush()
