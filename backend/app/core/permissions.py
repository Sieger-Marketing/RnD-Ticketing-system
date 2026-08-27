"""The permission catalogue and the default role -> permission grants.

Routes name a permission, never a role. That is what makes spec section 6
implementable without `if role == "Director"` scattered through the codebase,
and what lets an administrator invent a fifth role later without a code change.

This module is the *seed* definition. Once seeded, grants live in the
role_permissions table and can be edited at runtime through Settings.
"""

from __future__ import annotations

from app.core.enums import RoleName


class P:
    """Permission codes, grouped by module."""

    # -- projects ---------------------------------------------------------
    PROJECT_VIEW_ALL = "project.view_all"
    PROJECT_VIEW_ASSIGNED = "project.view_assigned"
    PROJECT_CREATE = "project.create"
    PROJECT_UPDATE = "project.update"
    PROJECT_DELETE = "project.delete"

    # -- design releases --------------------------------------------------
    RELEASE_VIEW_ALL = "release.view_all"
    RELEASE_VIEW_ASSIGNED = "release.view_assigned"
    RELEASE_CREATE = "release.create"
    RELEASE_UPDATE = "release.update"
    RELEASE_ASSIGN_LEAD = "release.assign_lead"
    #: Permanent removal of a release and everything under it. Separate from
    #: RELEASE_UPDATE, which cancels: cancelling is a status a Team Lead owns,
    #: deleting destroys other people's logged hours.
    RELEASE_DELETE = "release.delete"
    RELEASE_ACCEPT = "release.accept"
    RELEASE_COMPLETE = "release.complete"
    #: Completing a release that still has open mandatory tasks.
    RELEASE_OVERRIDE_COMPLETION = "release.override_completion"
    RELEASE_APPROVE = "release.approve"

    # -- templates --------------------------------------------------------
    TEMPLATE_VIEW = "template.view"
    TEMPLATE_MANAGE = "template.manage"
    TEMPLATE_PUBLISH = "template.publish"
    TEMPLATE_APPLY = "template.apply"

    # -- tasks ------------------------------------------------------------
    TASK_VIEW_ALL = "task.view_all"
    TASK_VIEW_TEAM = "task.view_team"
    TASK_VIEW_OWN = "task.view_own"
    TASK_CREATE = "task.create"
    TASK_UPDATE = "task.update"
    TASK_DELETE = "task.delete"
    TASK_ASSIGN = "task.assign"
    TASK_REASSIGN = "task.reassign"
    TASK_ESTIMATE = "task.estimate"
    #: Start / pause / submit on a task you own.
    TASK_EXECUTE = "task.execute"

    # -- time -------------------------------------------------------------
    TIME_LOG_OWN = "time.log_own"
    TIME_VIEW_ALL = "time.view_all"
    TIME_VIEW_TEAM = "time.view_team"
    TIME_EDIT_ANY = "time.edit_any"

    # -- review & revision ------------------------------------------------
    REVIEW_PERFORM = "review.perform"
    REVIEW_VIEW_ALL = "review.view_all"
    REVISION_CREATE = "revision.create"
    REVISION_VIEW_ALL = "revision.view_all"
    REVISION_RESOLVE = "revision.resolve"

    # -- resources --------------------------------------------------------
    RESOURCE_VIEW_ALL = "resource.view_all"
    RESOURCE_VIEW_TEAM = "resource.view_team"
    RESOURCE_MANAGE = "resource.manage"
    SKILL_VIEW = "skill.view"
    SKILL_MANAGE = "skill.manage"

    # -- analytics & reporting -------------------------------------------
    ANALYTICS_VIEW_DEPARTMENT = "analytics.view_department"
    ANALYTICS_VIEW_TEAM = "analytics.view_team"
    ANALYTICS_VIEW_OWN = "analytics.view_own"
    REPORT_EXPORT = "report.export"

    # -- administration ---------------------------------------------------
    USER_VIEW = "user.view"
    USER_MANAGE = "user.manage"
    SETTINGS_VIEW = "settings.view"
    SETTINGS_MANAGE = "settings.manage"
    AUDIT_VIEW = "audit.view"
    INTEGRATION_MANAGE = "integration.manage"

    # -- files ------------------------------------------------------------
    FILE_UPLOAD = "file.upload"
    FILE_VIEW = "file.view"
    FILE_DELETE = "file.delete"


#: code -> (module, human description)
PERMISSION_CATALOG: dict[str, tuple[str, str]] = {
    P.PROJECT_VIEW_ALL: ("projects", "View every project in the department"),
    P.PROJECT_VIEW_ASSIGNED: ("projects", "View projects the user is involved in"),
    P.PROJECT_CREATE: ("projects", "Create a project"),
    P.PROJECT_UPDATE: ("projects", "Edit project details"),
    P.PROJECT_DELETE: (
        "projects",
        "Permanently delete a project, with its releases, tasks and logged time",
    ),
    P.RELEASE_VIEW_ALL: ("releases", "View every design release"),
    P.RELEASE_VIEW_ASSIGNED: ("releases", "View releases assigned to the user"),
    P.RELEASE_CREATE: ("releases", "Create a design release"),
    P.RELEASE_UPDATE: ("releases", "Edit a design release"),
    P.RELEASE_ASSIGN_LEAD: ("releases", "Assign a Team Lead to a release"),
    P.RELEASE_DELETE: (
        "releases",
        "Permanently delete a release, with its tasks and logged time",
    ),
    P.RELEASE_ACCEPT: ("releases", "Accept an assigned release"),
    P.RELEASE_COMPLETE: ("releases", "Mark a release complete"),
    P.RELEASE_OVERRIDE_COMPLETION: (
        "releases",
        "Complete a release with open mandatory tasks (audited override)",
    ),
    P.RELEASE_APPROVE: ("releases", "Approve a completed release"),
    P.TEMPLATE_VIEW: ("templates", "View design templates"),
    P.TEMPLATE_MANAGE: ("templates", "Create and edit templates and their tasks"),
    P.TEMPLATE_PUBLISH: ("templates", "Publish a new template version"),
    P.TEMPLATE_APPLY: ("templates", "Generate release tasks from a template"),
    P.TASK_VIEW_ALL: ("tasks", "View every task"),
    P.TASK_VIEW_TEAM: ("tasks", "View tasks belonging to the user's team"),
    P.TASK_VIEW_OWN: ("tasks", "View tasks assigned to the user"),
    P.TASK_CREATE: ("tasks", "Add a task to a release"),
    P.TASK_UPDATE: ("tasks", "Edit task details"),
    P.TASK_DELETE: (
        "tasks",
        "Permanently delete a task, with its time entries, reviews and revisions",
    ),
    P.TASK_ASSIGN: ("tasks", "Assign a task to a designer"),
    P.TASK_REASSIGN: ("tasks", "Move a task between designers"),
    P.TASK_ESTIMATE: ("tasks", "Set or revise estimated effort"),
    P.TASK_EXECUTE: ("tasks", "Start, pause, block and submit own tasks"),
    P.TIME_LOG_OWN: ("time", "Log time against own tasks"),
    P.TIME_VIEW_ALL: ("time", "View all time entries"),
    P.TIME_VIEW_TEAM: ("time", "View the team's time entries"),
    P.TIME_EDIT_ANY: ("time", "Correct another user's time entry"),
    P.REVIEW_PERFORM: ("reviews", "Review a submitted task"),
    P.REVIEW_VIEW_ALL: ("reviews", "View all reviews"),
    P.REVISION_CREATE: ("revisions", "Raise a revision"),
    P.REVISION_VIEW_ALL: ("revisions", "View all revisions"),
    P.REVISION_RESOLVE: ("revisions", "Close a revision"),
    P.RESOURCE_VIEW_ALL: ("resources", "View department-wide capacity"),
    P.RESOURCE_VIEW_TEAM: ("resources", "View the team's capacity"),
    P.RESOURCE_MANAGE: ("resources", "Edit capacity, leave and holidays"),
    P.SKILL_VIEW: ("resources", "View the skill matrix"),
    P.SKILL_MANAGE: ("resources", "Edit skills and skill levels"),
    P.ANALYTICS_VIEW_DEPARTMENT: ("analytics", "Department-wide analytics"),
    P.ANALYTICS_VIEW_TEAM: ("analytics", "Team-level analytics"),
    P.ANALYTICS_VIEW_OWN: ("analytics", "Personal performance"),
    P.REPORT_EXPORT: ("reports", "Export reports"),
    P.USER_VIEW: ("admin", "View users"),
    P.USER_MANAGE: ("admin", "Create and edit users and roles"),
    P.SETTINGS_VIEW: ("admin", "View configuration"),
    P.SETTINGS_MANAGE: ("admin", "Change KPI weights, thresholds and business rules"),
    P.AUDIT_VIEW: ("admin", "Read the audit log"),
    P.INTEGRATION_MANAGE: ("admin", "Configure external system integrations"),
    P.FILE_UPLOAD: ("files", "Upload attachments"),
    P.FILE_VIEW: ("files", "Download attachments"),
    P.FILE_DELETE: ("files", "Delete attachments"),
}


# ---------------------------------------------------------------------------
# Default grants, straight from spec section 6.
# ---------------------------------------------------------------------------

#: The Director is deliberately read-only. Executive visibility everywhere,
#: drill-down into everything, export -- but no operational mutations. This is
#: what keeps the Director dashboard about exceptions and trends rather than
#: another place to edit tasks from.
_DIRECTOR = [
    P.PROJECT_VIEW_ALL,
    P.RELEASE_VIEW_ALL,
    P.TASK_VIEW_ALL,
    P.TEMPLATE_VIEW,
    P.TIME_VIEW_ALL,
    P.REVIEW_VIEW_ALL,
    P.REVISION_VIEW_ALL,
    P.RESOURCE_VIEW_ALL,
    P.SKILL_VIEW,
    P.ANALYTICS_VIEW_DEPARTMENT,
    P.ANALYTICS_VIEW_TEAM,
    P.ANALYTICS_VIEW_OWN,
    P.REPORT_EXPORT,
    P.USER_VIEW,
    P.AUDIT_VIEW,
    P.FILE_VIEW,
]

#: Full operational control of the department.
_DESIGN_MANAGER = _DIRECTOR + [
    P.PROJECT_CREATE,
    P.PROJECT_UPDATE,
    P.PROJECT_DELETE,
    P.RELEASE_CREATE,
    P.RELEASE_UPDATE,
    P.RELEASE_DELETE,
    P.RELEASE_ASSIGN_LEAD,
    P.RELEASE_COMPLETE,
    P.RELEASE_OVERRIDE_COMPLETION,
    P.RELEASE_APPROVE,
    P.TEMPLATE_MANAGE,
    P.TEMPLATE_PUBLISH,
    P.TEMPLATE_APPLY,
    P.TASK_CREATE,
    P.TASK_UPDATE,
    P.TASK_DELETE,
    P.TASK_ASSIGN,
    P.TASK_REASSIGN,
    P.TASK_ESTIMATE,
    P.TIME_EDIT_ANY,
    P.REVIEW_PERFORM,
    P.REVISION_CREATE,
    P.REVISION_RESOLVE,
    P.RESOURCE_MANAGE,
    P.SKILL_MANAGE,
    P.USER_MANAGE,
    P.SETTINGS_VIEW,
    P.SETTINGS_MANAGE,
    P.INTEGRATION_MANAGE,
    P.FILE_UPLOAD,
    P.FILE_DELETE,
]

#: Drives the projects assigned to them: builds out the design releases, staffs
#: them, and runs the people executing them. Cannot create or edit projects,
#: publish templates or change department-wide configuration.
#:
#: RELEASE_CREATE and RELEASE_ASSIGN_LEAD are bounded by visibility, not by the
#: permission alone -- both endpoints filter to the projects and releases the
#: caller can see, so a lead can build out the project they were given and no
#: other. Without them a lead "driving" a project still needed the manager to
#: add every release, which is not driving it.
_TEAM_LEAD = [
    P.PROJECT_VIEW_ASSIGNED,
    # Start a project as well as run one. A Team Lead is often the first person
    # to hear about a job, and making them wait for a manager to type it in was
    # the step where work got done before it existed in the system. Safe to
    # hand over because visible_projects counts created_by_id, so a lead sees
    # what they created without being given sight of the whole department.
    P.PROJECT_CREATE,
    # Edit the projects they lead, bounded by visible_projects so this reaches
    # the projects handed to them and no others.
    #
    # Deliberately NOT project.delete, and not release.delete either. Deleting
    # is permanent and cascades: a project takes its releases, its tasks and
    # every hour anybody logged against them. A Team Lead can still cancel
    # either one -- status Cancelled, via PATCH /projects/{id} or
    # POST /releases/{id}/status -- which removes it from the working view
    # while leaving the history the KPIs are computed from intact.
    #
    # task.delete stays: one task is a blast radius somebody who runs the work
    # day to day can reasonably be trusted with, and it is the one people
    # actually need, because a mistyped task is added and noticed in the same
    # afternoon.
    P.PROJECT_UPDATE,
    P.RELEASE_VIEW_ASSIGNED,
    P.RELEASE_ACCEPT,
    P.RELEASE_CREATE,
    P.RELEASE_ASSIGN_LEAD,
    P.RELEASE_UPDATE,
    P.RELEASE_COMPLETE,
    P.TEMPLATE_VIEW,
    P.TEMPLATE_APPLY,
    P.TASK_VIEW_TEAM,
    P.TASK_VIEW_OWN,
    P.TASK_CREATE,
    P.TASK_UPDATE,
    P.TASK_DELETE,
    P.TASK_ASSIGN,
    P.TASK_REASSIGN,
    P.TASK_ESTIMATE,
    P.TASK_EXECUTE,
    P.TIME_LOG_OWN,
    P.TIME_VIEW_TEAM,
    P.REVIEW_PERFORM,
    P.REVIEW_VIEW_ALL,
    P.REVISION_CREATE,
    P.REVISION_VIEW_ALL,
    P.REVISION_RESOLVE,
    P.RESOURCE_VIEW_TEAM,
    P.SKILL_VIEW,
    P.ANALYTICS_VIEW_TEAM,
    P.ANALYTICS_VIEW_OWN,
    P.REPORT_EXPORT,
    P.USER_VIEW,
    P.FILE_UPLOAD,
    P.FILE_VIEW,
]

#: Personal workspace only.
_DESIGNER = [
    P.PROJECT_VIEW_ASSIGNED,
    P.RELEASE_VIEW_ASSIGNED,
    P.TASK_VIEW_OWN,
    P.TASK_EXECUTE,
    P.TIME_LOG_OWN,
    P.SKILL_VIEW,
    P.ANALYTICS_VIEW_OWN,
    P.FILE_UPLOAD,
    P.FILE_VIEW,
]

#: Everything. Deliberately not composed from the other roles -- it is
#: derived from the catalogue, so a permission added later is granted here
#: automatically and an administrator never silently loses the ability to
#: use a feature the moment it ships.
#:
#: Worth being clear about the trade: an account holding every permission
#: can create work, do it, and approve it. The self-review ban still
#: applies -- it keys on who the task is assigned to, not on role -- but
#: separation of duties otherwise rests on this account being used
#: sparingly rather than as somebody's day-to-day login.
_ADMINISTRATOR = sorted(PERMISSION_CATALOG)

DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    RoleName.ADMINISTRATOR.value: _ADMINISTRATOR,
    RoleName.DIRECTOR.value: sorted(set(_DIRECTOR)),
    RoleName.DESIGN_MANAGER.value: sorted(set(_DESIGN_MANAGER)),
    RoleName.TEAM_LEAD.value: sorted(set(_TEAM_LEAD)),
    RoleName.DESIGNER.value: sorted(set(_DESIGNER)),
}

#: Lower rank == wider authority. Used for "may I act on this person's data".
ROLE_RANKS: dict[str, int] = {
    RoleName.ADMINISTRATOR.value: 0,
    RoleName.DIRECTOR.value: 10,
    RoleName.DESIGN_MANAGER.value: 20,
    RoleName.TEAM_LEAD.value: 30,
    RoleName.DESIGNER.value: 40,
}

#: Where each role lands after login (spec section 39).
ROLE_HOME_ROUTE: dict[str, str] = {
    # An administrator is there to run the department, not to read the
    # boardroom summary, so they land on the operational screen.
    RoleName.ADMINISTRATOR.value: "/dashboard/manager",
    RoleName.DIRECTOR.value: "/dashboard/executive",
    RoleName.DESIGN_MANAGER.value: "/dashboard/manager",
    RoleName.TEAM_LEAD.value: "/dashboard/team-lead",
    RoleName.DESIGNER.value: "/my-work",
}
