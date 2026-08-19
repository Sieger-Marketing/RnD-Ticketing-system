/**
 * People administration.
 *
 * The department changes: someone joins, someone moves from designer to team
 * lead, someone leaves, someone forgets a password on a Monday morning. All of
 * that has to be doable here, by the design manager, without a developer and
 * without a database client.
 *
 * The reporting line is the part worth getting right. Capacity, "my team" and
 * review routing are all derived from who reports to whom, so this screen
 * shows that structure rather than hiding it behind an id field: designers
 * point at a team lead, team leads at the design manager.
 */

import { KeyRound, Pencil, Plus, UserPlus, Users2 } from "lucide-react";
import { useMemo, useState } from "react";

import { UserFormModal } from "@/components/UserFormModal";
import { PasswordHandoff } from "@/components/PasswordHandoff";
import { ResponsiveTable } from "@/components/ui/ResponsiveTable";
import {
  Avatar,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  SkeletonRows,
} from "@/components/ui/primitives";
import { useResetPassword, useRoles, useUsers } from "@/hooks/queries";
import { DASH, shortDate } from "@/lib/format";
import { P, useAuth } from "@/store/auth";
import type { PasswordReset, User } from "@/types/api";

/** Roles that can be reported to, most senior first. */
const LEADERSHIP = ["Director", "Design Manager", "Team Lead"];

export default function Users() {
  const can = useAuth((s) => s.can);
  const manages = can(P.userManage);

  const users = useUsers({ page_size: 200, active_only: false });
  const roles = useRoles();
  const reset = useResetPassword();

  const [query, setQuery] = useState("");
  const [showInactive, setShowInactive] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [creating, setCreating] = useState(false);
  const [handoff, setHandoff] = useState<PasswordReset | null>(null);

  const byId = useMemo(() => {
    const map = new Map<string, User>();
    for (const user of users.data?.items ?? []) map.set(user.id, user);
    return map;
  }, [users.data]);

  const shown = useMemo(() => {
    const items = users.data?.items ?? [];
    const term = query.trim().toLowerCase();
    return items
      .filter((u) => showInactive || u.is_active)
      .filter(
        (u) =>
          !term ||
          u.full_name.toLowerCase().includes(term) ||
          (u.employee_code ?? "").toLowerCase().includes(term) ||
          u.email.toLowerCase().includes(term) ||
          u.roles.some((r) => r.toLowerCase().includes(term)),
      )
      .sort((a, b) => {
        // Leadership first, so the structure reads top-down.
        const rank = (u: User) => {
          const index = LEADERSHIP.findIndex((r) => u.roles.includes(r));
          return index === -1 ? LEADERSHIP.length : index;
        };
        return rank(a) - rank(b) || a.full_name.localeCompare(b.full_name);
      });
  }, [users.data, query, showInactive]);

  const leaders = useMemo(
    () =>
      (users.data?.items ?? []).filter(
        (u) => u.is_active && u.roles.some((r) => LEADERSHIP.includes(r)),
      ),
    [users.data],
  );

  const resetFor = (user: User) => {
    reset.mutate(user.id, { onSuccess: (result) => setHandoff(result) });
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title="People"
        subtitle="Who is in the department, what they may do, and who they report to."
        actions={
          manages && (
            <button
              type="button"
              className="btn-primary"
              onClick={() => setCreating(true)}
            >
              <UserPlus className="h-4 w-4" />
              Add someone
            </button>
          )
        }
      />

      {users.isError && <ErrorState onRetry={() => void users.refetch()} />}
      {users.isLoading && <SkeletonRows rows={6} cols={4} />}

      {users.data && (
        <>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <input
              type="search"
              className="input sm:max-w-xs"
              placeholder="Find by name, code or role"
              aria-label="Find a person"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <label className="flex items-center gap-2 text-xs text-ink-600">
              <input
                type="checkbox"
                checked={showInactive}
                onChange={(event) => setShowInactive(event.target.checked)}
              />
              Include people who have left
            </label>
            <span className="text-xs text-ink-500 sm:ml-auto">
              {shown.length} of {users.data.items.length}
            </span>
          </div>

          {shown.length === 0 ? (
            <Card>
              <EmptyState
                title="Nobody matches that"
                description="Try a name, an employee code, or a role."
                icon={<Users2 className="h-6 w-6" />}
              />
            </Card>
          ) : (
            <Card bodyClassName="">
              <ResponsiveTable
                rows={shown}
                rowKey={(user) => user.id}
                minWidth="52rem"
                columns={[
                  {
                    key: "person",
                    mobile: "primary",
                    header: "Person",
                    cell: (user) => (
                      <div className="flex items-center gap-2">
                        <Avatar name={user.full_name} />
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-ink-900">
                            {user.full_name}
                            {!user.is_active && (
                              <span className="ml-2 rounded-full bg-ink-100 px-2 py-0.5 text-2xs font-medium text-ink-500">
                                left
                              </span>
                            )}
                          </p>
                          <p className="truncate text-xs text-ink-500">
                            {user.designation ?? DASH}
                          </p>
                        </div>
                      </div>
                    ),
                  },
                  {
                    key: "identity",
                    mobile: "meta",
                    header: "Signs in with",
                    cell: (user) => (
                      <span className="font-mono text-xs text-ink-700">
                        {user.employee_code ?? user.email}
                      </span>
                    ),
                  },
                  {
                    key: "role",
                    mobile: "field",
                    header: "Role",
                    cell: (user) =>
                      user.roles.length ? (
                        <span className="text-sm text-ink-800">
                          {user.roles.join(", ")}
                        </span>
                      ) : (
                        <span className="text-xs text-rag-amber">no role</span>
                      ),
                  },
                  {
                    key: "reports_to",
                    mobile: "field",
                    header: "Reports to",
                    cell: (user) => (
                      <span className="text-sm text-ink-700">
                        {user.reports_to_id
                          ? (byId.get(user.reports_to_id)?.full_name ?? DASH)
                          : DASH}
                      </span>
                    ),
                  },
                  {
                    key: "last_login",
                    mobile: "field",
                    header: "Last signed in",
                    cell: (user) => (
                      <span className="text-xs text-ink-500">
                        {user.last_login_at ? shortDate(user.last_login_at) : "never"}
                      </span>
                    ),
                  },
                  {
                    key: "actions",
                    align: "right",
                    mobile: "field",
                    header: "",
                    cell: (user) =>
                      manages && (
                        <div className="flex items-center justify-end gap-1">
                          <button
                            type="button"
                            className="btn-ghost px-1.5"
                            title={`Reset the password for ${user.full_name}`}
                            aria-label={`Reset the password for ${user.full_name}`}
                            onClick={() => resetFor(user)}
                            disabled={reset.isPending}
                          >
                            <KeyRound className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            className="btn-ghost px-1.5"
                            title={`Edit ${user.full_name}`}
                            aria-label={`Edit ${user.full_name}`}
                            onClick={() => setEditing(user)}
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                        </div>
                      ),
                  },
                ]}
              />
            </Card>
          )}

          {leaders.length === 0 && (
            <Card>
              <div className="flex items-start gap-3">
                <Plus className="mt-0.5 h-4 w-4 shrink-0 text-rag-amber" />
                <div className="text-sm text-ink-700">
                  <p className="font-medium text-ink-900">
                    Nobody holds a leadership role yet.
                  </p>
                  <p className="mt-0.5 text-xs text-ink-600">
                    Until someone is a Design Manager, no project can be created
                    and no work can be approved. Edit a person and give them the
                    role, then point the designers at their team lead.
                  </p>
                </div>
              </div>
            </Card>
          )}
        </>
      )}

      {creating && (
        <UserFormModal
          open
          roles={roles.data ?? []}
          leaders={leaders}
          onClose={() => setCreating(false)}
          onCreated={(result) => {
            setCreating(false);
            setHandoff(result);
          }}
        />
      )}

      {editing && (
        <UserFormModal
          open
          user={editing}
          roles={roles.data ?? []}
          leaders={leaders.filter((l) => l.id !== editing.id)}
          onClose={() => setEditing(null)}
          onCreated={() => setEditing(null)}
        />
      )}

      {handoff && (
        <PasswordHandoff reset={handoff} onClose={() => setHandoff(null)} />
      )}
    </div>
  );
}
