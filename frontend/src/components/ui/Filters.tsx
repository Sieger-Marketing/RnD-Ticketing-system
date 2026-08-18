/**
 * List controls: search, multi-select filters, pagination.
 *
 * Filtering and paging happen on the server -- the browser never receives the
 * whole task table -- so these components only own the query parameters.
 */

import clsx from "clsx";
import { ChevronLeft, ChevronRight, Search, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

export function SearchInput({
  value,
  onChange,
  placeholder = "Search",
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}) {
  // Debounced so typing a project name does not fire a request per keystroke.
  const [draft, setDraft] = useState(value);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => setDraft(value), [value]);

  useEffect(() => {
    if (draft === value) return;
    const timer = setTimeout(() => onChangeRef.current(draft), 300);
    return () => clearTimeout(timer);
  }, [draft, value]);

  return (
    <div className={clsx("relative", className)}>
      <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-400" />
      <input
        className="input pl-8 pr-7"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder={placeholder}
        type="search"
      />
      {draft && (
        <button
          type="button"
          className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-400 hover:text-ink-700"
          onClick={() => {
            setDraft("");
            onChange("");
          }}
          aria-label="Clear search"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

/** Toggleable chips. Selecting none means "no filter", not "nothing". */
export function ChipFilter({
  label,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: string[];
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1">
      <span className="mr-1 text-2xs font-medium uppercase tracking-wide text-ink-500">
        {label}
      </span>
      {options.map((option) => {
        const active = selected.includes(option);
        return (
          <button
            key={option}
            type="button"
            className={clsx(
              "rounded-full border px-2 py-0.5 text-2xs transition-colors",
              active
                ? "border-brand-600 bg-brand-600 text-white"
                : "border-ink-300 bg-white text-ink-600 hover:bg-ink-100",
            )}
            onClick={() =>
              onChange(
                active
                  ? selected.filter((s) => s !== option)
                  : [...selected, option],
              )
            }
          >
            {option}
          </button>
        );
      })}
      {selected.length > 0 && (
        <button
          type="button"
          className="ml-1 text-2xs text-brand-600 hover:underline"
          onClick={() => onChange([])}
        >
          clear
        </button>
      )}
    </div>
  );
}

export function FilterBar({ children }: { children: ReactNode }) {
  return (
    <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-ink-200 bg-white p-3">
      {children}
    </div>
  );
}

export function Pagination({
  page,
  pages,
  total,
  pageSize,
  onPage,
}: {
  page: number;
  pages: number;
  total: number;
  pageSize: number;
  onPage: (page: number) => void;
}) {
  if (total === 0) return null;

  const first = (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);

  return (
    <div className="flex items-center justify-between gap-3 border-t border-ink-200 px-3 py-2">
      <p className="text-2xs text-ink-500">
        {first}–{last} of {total.toLocaleString()}
      </p>
      <div className="flex items-center gap-1">
        <button
          type="button"
          className="btn-secondary px-2 py-1"
          onClick={() => onPage(page - 1)}
          disabled={page <= 1}
          aria-label="Previous page"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
        </button>
        <span className="px-2 text-2xs text-ink-600">
          {page} / {pages || 1}
        </span>
        <button
          type="button"
          className="btn-secondary px-2 py-1"
          onClick={() => onPage(page + 1)}
          disabled={page >= pages}
          aria-label="Next page"
        >
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
