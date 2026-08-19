/**
 * Change your own password.
 *
 * Everyone a seed run creates starts on the same password, so until someone
 * changes theirs it is not a secret at all. This is the only way to do that
 * from the app, which makes it the difference between a system people can be
 * given accounts on and one they cannot.
 *
 * The server checks the current password before accepting a new one, so a
 * borrowed unlocked laptop is not enough to take an account over.
 */

import { useState } from "react";

import { Field, FormError, TextInput } from "@/components/ui/form";
import { Modal } from "@/components/ui/Modal";
import { InlineAlert, Spinner } from "@/components/ui/primitives";
import { useChangePassword } from "@/hooks/queries";

const MIN_LENGTH = 8;

export function ChangePasswordModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const change = useChangePassword();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState(false);

  const tooShort = next.length > 0 && next.length < MIN_LENGTH;
  const mismatch = confirm.length > 0 && next !== confirm;
  const unchanged = next.length > 0 && next === current;
  const ready =
    current.length > 0 &&
    next.length >= MIN_LENGTH &&
    next === confirm &&
    next !== current;

  const close = () => {
    setCurrent("");
    setNext("");
    setConfirm("");
    setDone(false);
    change.reset();
    onClose();
  };

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    change.mutate(
      { current_password: current, new_password: next },
      {
        onSuccess: () => {
          setDone(true);
          setCurrent("");
          setNext("");
          setConfirm("");
        },
      },
    );
  };

  return (
    <Modal
      open={open}
      onClose={close}
      size="sm"
      title="Change your password"
      description={
        done ? undefined : "You will stay signed in on this device."
      }
      footer={
        done ? (
          <button type="button" className="btn-primary" onClick={close}>
            Done
          </button>
        ) : (
          <>
            <button type="button" className="btn-secondary" onClick={close}>
              Cancel
            </button>
            <button
              type="submit"
              form="change-password"
              className="btn-primary"
              disabled={!ready || change.isPending}
            >
              {change.isPending && <Spinner className="h-4 w-4" />}
              Change password
            </button>
          </>
        )
      }
    >
      {done ? (
        <InlineAlert tone="success">
          Your password has been changed. Use the new one the next time you sign
          in.
        </InlineAlert>
      ) : (
        <form id="change-password" onSubmit={submit} className="space-y-3">
          <FormError error={change.error} />

          <Field label="Current password">
            <TextInput
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(event) => setCurrent(event.target.value)}
              required
            />
          </Field>

          <Field
            label="New password"
            hint={`At least ${MIN_LENGTH} characters.`}
            error={
              tooShort
                ? `Use at least ${MIN_LENGTH} characters.`
                : unchanged
                  ? "That is the password you already have."
                  : undefined
            }
          >
            <TextInput
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(event) => setNext(event.target.value)}
              required
            />
          </Field>

          <Field
            label="New password again"
            error={mismatch ? "The two do not match." : undefined}
          >
            <TextInput
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              required
            />
          </Field>
        </form>
      )}
    </Modal>
  );
}
