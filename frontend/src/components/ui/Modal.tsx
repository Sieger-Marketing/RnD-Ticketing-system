import clsx from "clsx";
import { X } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";

/**
 * Modal dialog.
 *
 * Escape closes it and the body stops scrolling while it is open, so a long
 * form does not leave the page behind it scrolling under the user's cursor.
 */
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = "md",
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg" | "xl";
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [open, onClose]);

  if (!open) return null;

  const width = {
    sm: "max-w-sm",
    md: "max-w-lg",
    lg: "max-w-2xl",
    xl: "max-w-4xl",
  }[size];

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink-900/40 p-4 sm:p-8">
      <div
        className="fixed inset-0"
        onClick={onClose}
        aria-hidden
      />
      <div
        role="dialog"
        aria-modal="true"
        className={clsx(
          "relative z-10 w-full rounded-lg bg-white shadow-pop",
          width,
        )}
      >
        <header className="flex items-start justify-between gap-4 border-b border-ink-200 px-5 py-3">
          <div>
            <h2 className="text-sm font-semibold text-ink-900">{title}</h2>
            {description && (
              <p className="mt-0.5 text-xs text-ink-500">{description}</p>
            )}
          </div>
          <button
            type="button"
            className="btn-ghost -mr-1 px-1.5"
            onClick={onClose}
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="max-h-[70vh] overflow-y-auto px-5 py-4">{children}</div>

        {footer && (
          <footer className="flex items-center justify-end gap-2 border-t border-ink-200 px-5 py-3">
            {footer}
          </footer>
        )}
      </div>
    </div>,
    document.body,
  );
}

/** Slide-over panel, for detail that should not lose the list behind it. */
export function Drawer({
  open,
  onClose,
  title,
  children,
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-ink-900/40" onClick={onClose} aria-hidden />
      <aside
        role="dialog"
        aria-modal="true"
        className="absolute inset-y-0 right-0 flex w-full max-w-xl flex-col bg-white shadow-pop"
      >
        <header className="flex items-center justify-between gap-4 border-b border-ink-200 px-5 py-3">
          <h2 className="text-sm font-semibold text-ink-900">{title}</h2>
          <button
            type="button"
            className="btn-ghost -mr-1 px-1.5"
            onClick={onClose}
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && (
          <footer className="flex items-center justify-end gap-2 border-t border-ink-200 px-5 py-3">
            {footer}
          </footer>
        )}
      </aside>
    </div>,
    document.body,
  );
}
