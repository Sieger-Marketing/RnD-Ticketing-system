/**
 * Form controls.
 *
 * `Field` owns the label, hint and error slot so every form reports validation
 * the same way, and so a 422 from the API can be dropped straight onto the
 * field it names.
 */

import clsx from "clsx";
import type { ReactNode, SelectHTMLAttributes, InputHTMLAttributes, TextareaHTMLAttributes } from "react";

import { ApiError } from "@/lib/api";
import { InlineAlert } from "@/components/ui/primitives";

export function Field({
  label,
  htmlFor,
  hint,
  error,
  required,
  children,
  className,
}: {
  label: string;
  htmlFor?: string;
  hint?: ReactNode;
  error?: string;
  required?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <label className="label" htmlFor={htmlFor}>
        {label}
        {required && <span className="ml-0.5 text-rag-red">*</span>}
      </label>
      {children}
      {error ? (
        <p className="mt-1 text-2xs text-rag-red">{error}</p>
      ) : hint ? (
        <p className="mt-1 text-2xs text-ink-500">{hint}</p>
      ) : null}
    </div>
  );
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={clsx("input", props.className)} />;
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={clsx("input", props.className)} rows={props.rows ?? 3} />;
}

export function Select({
  options,
  placeholder,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & {
  options: { value: string; label: string }[];
  placeholder?: string;
}) {
  return (
    <select {...props} className={clsx("input", props.className)}>
      {placeholder && <option value="">{placeholder}</option>}
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

/**
 * Renders a failed mutation.
 *
 * Field-level messages from a 422 are listed rather than collapsed into the
 * generic message, because "planned_end cannot be before planned_start" is
 * actionable and "Validation failed" is not.
 */
export function FormError({ error }: { error: unknown }) {
  if (!error) return null;

  if (error instanceof ApiError) {
    const fields = error.fieldErrors;
    return (
      <InlineAlert tone="error">
        <p className="font-medium">{error.message}</p>
        {fields.length > 0 && (
          <ul className="mt-1 space-y-0.5">
            {fields.map((f, i) => (
              <li key={i}>
                <span className="font-mono">{f.field}</span>: {f.message}
              </li>
            ))}
          </ul>
        )}
      </InlineAlert>
    );
  }

  return (
    <InlineAlert tone="error">
      {error instanceof Error ? error.message : "Something went wrong."}
    </InlineAlert>
  );
}
