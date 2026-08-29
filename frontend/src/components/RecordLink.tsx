/**
 * A name that goes to the thing it names.
 *
 * Two details make this worth a component rather than a `<Link>` at each call
 * site. Most of these names sit inside rows that are themselves clickable, so
 * the click must be stopped from reaching the row -- otherwise following a
 * project name from a task list navigates to the task instead, which looks
 * like the link is broken. And a name whose id is missing must render as plain
 * text rather than as a link to nowhere: an entry whose project was deleted,
 * or a payload from an API that predates the id being sent, should read as
 * un-clickable rather than take somebody to a 404.
 */

import { Link } from "react-router-dom";
import type { ReactNode } from "react";

import { DASH } from "@/lib/format";
import type { UUID } from "@/types/api";

type Kind = "project" | "release" | "task";

const PATH: Record<Kind, string> = {
  project: "/projects",
  release: "/releases",
  task: "/tasks",
};

export function RecordLink({
  kind,
  id,
  children,
  className = "",
  title,
}: {
  kind: Kind;
  /** No id means no link: the name renders as plain text. */
  id: UUID | null | undefined;
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  if (children === null || children === undefined || children === "") {
    return <span className={className}>{DASH}</span>;
  }

  if (!id) {
    return (
      <span className={className} title={title}>
        {children}
      </span>
    );
  }

  return (
    <Link
      to={`${PATH[kind]}/${id}`}
      className={`hover:text-signal-700 hover:underline ${className}`}
      title={title}
      // The row underneath is usually a link too. Without this, clicking the
      // project name inside a task row opens the task.
      onClick={(event) => event.stopPropagation()}
    >
      {children}
    </Link>
  );
}
