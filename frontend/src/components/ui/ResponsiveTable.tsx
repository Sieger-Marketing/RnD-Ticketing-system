/**
 * A table on a desktop, a list of cards on a phone.
 *
 * These screens carry eight to ten columns. Putting that in a horizontally
 * scrolling table on a 375px screen is technically responsive and practically
 * unusable: the reader loses the row they were on as soon as they scroll to
 * the column they wanted. Below the breakpoint each row becomes a card whose
 * primary fields lead and whose secondary fields are labelled, so nothing has
 * to be scrolled sideways to be read.
 *
 * Columns declare their own priority, so each screen decides what survives on
 * a small screen rather than the component guessing.
 */

import clsx from "clsx";
import type { ReactNode } from "react";

export interface Column<T> {
  /** Stable key, also used for the React key. */
  key: string;
  header: ReactNode;
  /** Cell contents for a row. */
  cell: (row: T) => ReactNode;
  /** Right-align numeric columns so they compare down the column. */
  align?: "left" | "right";
  /**
   * How the column behaves on a phone.
   *  - "primary": the card's headline (usually the name)
   *  - "meta": the small line under the headline (code, project)
   *  - "field": a labelled key/value pair in the card body
   *  - "hidden": desktop only
   */
  mobile?: "primary" | "meta" | "field" | "hidden";
  className?: string;
  headerClassName?: string;
}

export function ResponsiveTable<T>({
  rows,
  columns,
  rowKey,
  onRowClick,
  minWidth = "56rem",
  empty,
  footer,
}: {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  /** Width below which the desktop table starts scrolling. */
  minWidth?: string;
  empty?: ReactNode;
  footer?: ReactNode;
}) {
  if (rows.length === 0) return <>{empty}</>;

  const primary = columns.filter((c) => c.mobile === "primary");
  const meta = columns.filter((c) => c.mobile === "meta");
  const fields = columns.filter((c) => c.mobile === "field" || c.mobile === undefined);

  return (
    <>
      {/* Phones: one card per row. */}
      <ul className="divide-y divide-ink-100 md:hidden">
        {rows.map((row) => (
          <li
            key={rowKey(row)}
            className={clsx(
              "px-3 py-3",
              onRowClick && "cursor-pointer active:bg-cream-100",
            )}
            onClick={onRowClick ? () => onRowClick(row) : undefined}
          >
            {primary.map((column) => (
              <div key={column.key} className="text-sm font-medium text-ink-900">
                {column.cell(row)}
              </div>
            ))}

            {meta.length > 0 && (
              <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-2xs text-ink-500">
                {meta.map((column) => (
                  <span key={column.key}>{column.cell(row)}</span>
                ))}
              </div>
            )}

            {fields.length > 0 && (
              <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5 xs:grid-cols-3">
                {fields.map((column) => (
                  <div key={column.key} className="min-w-0">
                    <dt className="truncate text-[10px] uppercase tracking-wide text-ink-400">
                      {column.header}
                    </dt>
                    <dd className="truncate text-xs text-ink-800">
                      {column.cell(row)}
                    </dd>
                  </div>
                ))}
              </dl>
            )}
          </li>
        ))}
      </ul>

      {/* Tablet and up: the real table. */}
      <div className="hidden md:block">
        <div className="table-scroll">
          <table className="w-full" style={{ minWidth }}>
            <thead className="border-b border-ink-200 bg-cream-100">
              <tr>
                {columns
                  .filter((c) => c.mobile !== "hidden" || true)
                  .map((column) => (
                    <th
                      key={column.key}
                      className={clsx(
                        "th",
                        column.align === "right" && "text-right",
                        column.headerClassName,
                      )}
                    >
                      {column.header}
                    </th>
                  ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100">
              {rows.map((row) => (
                <tr
                  key={rowKey(row)}
                  className={clsx(
                    "hover:bg-cream-50",
                    onRowClick && "cursor-pointer",
                  )}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                >
                  {columns.map((column) => (
                    <td
                      key={column.key}
                      className={clsx(
                        "td",
                        column.align === "right" && "text-right",
                        column.className,
                      )}
                    >
                      {column.cell(row)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {footer}
    </>
  );
}

/**
 * For genuinely wide analytical grids -- a capacity heatmap, a trend table --
 * where turning rows into cards would destroy the comparison the grid exists
 * to make. Those scroll, but say so rather than leaving the reader to discover
 * that half the data is off-screen.
 */
export function WideScroll({
  children,
  hint = "Scroll sideways to see the full range.",
}: {
  children: ReactNode;
  hint?: string;
}) {
  return (
    <>
      <div className="table-scroll">{children}</div>
      <p className="scroll-hint">{hint}</p>
    </>
  );
}
