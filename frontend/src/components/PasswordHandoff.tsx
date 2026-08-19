/**
 * Shows a newly generated password once, for the administrator to pass on.
 *
 * It is deliberately awkward to dismiss by accident: this is the only moment
 * the password is readable. The server stores only a hash, so closing this
 * without noting it down means resetting again -- which is cheap, and much
 * better than a password that can be read out of the system later.
 */

import { Check, Copy, KeyRound } from "lucide-react";
import { useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { InlineAlert } from "@/components/ui/primitives";
import type { PasswordReset } from "@/types/api";

export function PasswordHandoff({
  reset,
  onClose,
}: {
  reset: PasswordReset;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(reset.password);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be refused; the password is on screen regardless.
      setCopied(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      size="sm"
      title="New password"
      description={`For ${reset.full_name}${
        reset.employee_code ? ` (${reset.employee_code})` : ""
      }`}
      footer={
        <button type="button" className="btn-primary" onClick={onClose}>
          I have passed it on
        </button>
      }
    >
      <div className="space-y-3">
        <div className="flex items-center gap-2 rounded-md border border-ink-200 bg-cream-50 px-3 py-2.5">
          <KeyRound className="h-4 w-4 shrink-0 text-ink-500" />
          <code className="min-w-0 flex-1 select-all break-all font-mono text-sm text-ink-900">
            {reset.password}
          </code>
          <button
            type="button"
            className="btn-ghost shrink-0 px-1.5"
            onClick={() => void copy()}
            title="Copy"
            aria-label="Copy the password"
          >
            {copied ? (
              <Check className="h-4 w-4 text-rag-green" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
          </button>
        </div>

        <InlineAlert tone="warn">
          This is the only time it can be read. Give it to them directly, and
          ask them to change it with the key icon in the sidebar.
        </InlineAlert>
      </div>
    </Modal>
  );
}
