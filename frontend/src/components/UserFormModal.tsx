/**
 * Add someone to the department, or change what they are.
 *
 * The same form does both, because the fields are the same and the difference
 * that matters -- a new person needs a password, an existing one does not --
 * is one field, not one screen.
 *
 * A new person's password is generated here rather than invented by whoever is
 * filling the form. People asked to make up a password for someone else reuse
 * the same one, and a password that came out of a head is a password that is
 * about to be written on a sticky note.
 */

import { useEffect, useMemo, useState } from "react";

import { Field, FormError, Select, TextInput } from "@/components/ui/form";
import { Modal } from "@/components/ui/Modal";
import { InlineAlert, Spinner } from "@/components/ui/primitives";
import { useCreateUser, useUpdateUser } from "@/hooks/queries";
import type { PasswordReset, Role, User } from "@/types/api";

/** No O/0 or l/1/I: this gets read aloud and typed by hand. */
const ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789";

function generatePassword(length = 12): string {
  const values = new Uint32Array(length);
  crypto.getRandomValues(values);
  return Array.from(values, (v) => ALPHABET[v % ALPHABET.length]).join("");
}

/** sies00267@sieger.in -- email is the table's key; the code is the identity. */
function placeholderEmail(employeeCode: string): string {
  return `${employeeCode.trim().toLowerCase()}@sieger.in`;
}

export function UserFormModal({
  open,
  user,
  roles,
  leaders,
  onClose,
  onCreated,
}: {
  open: boolean;
  user?: User;
  roles: Role[];
  /** People who can be reported to. */
  leaders: User[];
  onClose: () => void;
  onCreated: (handoff: PasswordReset | null) => void;
}) {
  const editing = Boolean(user);
  const create = useCreateUser();
  const update = useUpdateUser(user?.id ?? "00000000-0000-0000-0000-000000000000");
  const pending = create.isPending || update.isPending;

  const [employeeCode, setEmployeeCode] = useState("");
  const [email, setEmail] = useState("");
  const [emailTouched, setEmailTouched] = useState(false);
  const [fullName, setFullName] = useState("");
  const [designation, setDesignation] = useState("");
  const [role, setRole] = useState("Designer");
  const [reportsTo, setReportsTo] = useState("");
  const [dailyHours, setDailyHours] = useState(8);
  const [isActive, setIsActive] = useState(true);

  useEffect(() => {
    if (!open) return;
    setEmployeeCode(user?.employee_code ?? "");
    setEmail(user?.email ?? "");
    setEmailTouched(Boolean(user));
    setFullName(user?.full_name ?? "");
    setDesignation(user?.designation ?? "");
    setRole(user?.roles[0] ?? "Designer");
    setReportsTo(user?.reports_to_id ?? "");
    setDailyHours(user?.standard_daily_hours ?? 8);
    setIsActive(user?.is_active ?? true);
    create.reset();
    update.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, user]);

  // Someone with no mailbox still needs the unique key filled, so it follows
  // the employee code until the administrator types a real address.
  useEffect(() => {
    if (editing || emailTouched) return;
    setEmail(employeeCode.trim() ? placeholderEmail(employeeCode) : "");
  }, [employeeCode, emailTouched, editing]);

  const roleOptions = useMemo(
    () => roles.map((r) => ({ value: r.name, label: r.name })),
    [roles],
  );

  const leaderOptions = useMemo(
    () => [
      { value: "", label: "Nobody" },
      ...leaders.map((l) => ({
        value: l.id,
        label: `${l.full_name} — ${l.roles[0] ?? "no role"}`,
      })),
    ],
    [leaders],
  );

  const ready = fullName.trim().length > 0 && email.trim().length > 0 && role;

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!ready) return;

    const common = {
      employee_code: employeeCode.trim() || null,
      full_name: fullName.trim(),
      designation: designation.trim() || null,
      department: "Design",
      roles: [role],
      reports_to_id: reportsTo || null,
      standard_daily_hours: dailyHours,
    };

    if (editing && user) {
      update.mutate(
        { ...common, is_active: isActive },
        { onSuccess: () => onCreated(null) },
      );
      return;
    }

    const password = generatePassword();
    create.mutate(
      { ...common, email: email.trim().toLowerCase(), password },
      {
        onSuccess: (created) =>
          onCreated({
            user_id: created.id,
            employee_code: created.employee_code,
            full_name: created.full_name,
            password,
          }),
      },
    );
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="md"
      title={editing ? `Edit ${user?.full_name}` : "Add someone"}
      description={
        editing
          ? undefined
          : "They will be able to sign in straight away with the password this generates."
      }
      footer={
        <>
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="submit"
            form="user-form"
            className="btn-primary"
            disabled={!ready || pending}
          >
            {pending && <Spinner className="h-4 w-4" />}
            {editing ? "Save" : "Add"}
          </button>
        </>
      }
    >
      <form id="user-form" onSubmit={submit} className="space-y-3">
        <FormError error={create.error ?? update.error} />

        <div className="grid gap-3 sm:grid-cols-2">
          <Field
            label="Employee code"
            hint="What they sign in with. Leave blank for someone who uses their email."
          >
            <TextInput
              value={employeeCode}
              onChange={(event) => setEmployeeCode(event.target.value)}
              placeholder="SIES00267"
              autoCapitalize="characters"
            />
          </Field>

          <Field label="Full name">
            <TextInput
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              required
            />
          </Field>
        </div>

        <Field
          label="Email address"
          hint={
            editing
              ? undefined
              : "Used to identify the account. A placeholder is filled in for someone with no mailbox."
          }
        >
          <TextInput
            type="email"
            value={email}
            onChange={(event) => {
              setEmailTouched(true);
              setEmail(event.target.value);
            }}
            required
            disabled={editing}
          />
        </Field>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Role">
            <Select
              value={role}
              onChange={(event) => setRole(event.target.value)}
              options={roleOptions}
            />
          </Field>

          <Field
            label="Reports to"
            hint="Drives capacity and the team dashboards."
          >
            <Select
              value={reportsTo}
              onChange={(event) => setReportsTo(event.target.value)}
              options={leaderOptions}
            />
          </Field>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Designation">
            <TextInput
              value={designation}
              onChange={(event) => setDesignation(event.target.value)}
              placeholder="Design Engineer"
            />
          </Field>

          <Field label="Standard hours a day">
            <TextInput
              type="number"
              min={1}
              max={24}
              step={0.5}
              value={dailyHours}
              onChange={(event) => setDailyHours(Number(event.target.value))}
            />
          </Field>
        </div>

        {editing && (
          <label className="flex items-start gap-2 rounded-md border border-ink-200 px-3 py-2">
            <input
              type="checkbox"
              className="mt-1"
              checked={isActive}
              onChange={(event) => setIsActive(event.target.checked)}
            />
            <span className="min-w-0 text-sm text-ink-900">
              Still with the department
              <span className="mt-0.5 block text-xs text-ink-500">
                Unticking stops them signing in. Their name stays on the work
                they did, which is why nobody is ever deleted.
              </span>
            </span>
          </label>
        )}

        {!editing && (
          <InlineAlert tone="info">
            A password is generated when you add them, and shown once for you to
            pass on.
          </InlineAlert>
        )}
      </form>
    </Modal>
  );
}
