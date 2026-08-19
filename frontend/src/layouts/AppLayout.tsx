/**
 * The application shell: sidebar, top bar, breadcrumbs, notification bell.
 *
 * Navigation is filtered by permission, so a Designer never sees a link to a
 * screen that would refuse them. Items are only listed here once the screen
 * behind them actually exists.
 */

import clsx from "clsx";
import {
  Bell,
  ClipboardCheck,
  Clock,
  ChevronRight,
  FileStack,
  FolderKanban,
  Layers,
  LayoutDashboard,
  LayoutGrid,
  ListChecks,
  LogOut,
  Menu,
  RotateCcw,
  Square,
  X,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import siegerLogo from "@/assets/sieger-logo.png";
import { Avatar, Spinner } from "@/components/ui/primitives";
import {
  useMarkAllRead,
  useNotifications,
  useRunningTimer,
  useStopTimer,
  useUnreadCount,
} from "@/hooks/queries";
import { relative } from "@/lib/format";
import { useAuth } from "@/store/auth";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  /** Shown when the user holds at least one of these. Empty means always. */
  anyOf?: string[];
}

const NAV_SECTIONS: { heading: string; items: NavItem[] }[] = [
  {
    heading: "Overview",
    items: [
      {
        to: "/dashboard/executive",
        label: "Executive",
        icon: <LayoutDashboard className="h-4 w-4" />,
        anyOf: ["analytics.view_department"],
      },
      {
        to: "/dashboard/manager",
        label: "Design Manager",
        icon: <LayoutDashboard className="h-4 w-4" />,
        anyOf: ["project.view_all"],
      },
      {
        to: "/dashboard/team-lead",
        label: "My Team",
        icon: <LayoutDashboard className="h-4 w-4" />,
        anyOf: ["analytics.view_team"],
      },
      {
        to: "/my-work",
        label: "My Work",
        icon: <ListChecks className="h-4 w-4" />,
      },
    ],
  },
  {
    heading: "Delivery",
    items: [
      {
        to: "/projects",
        label: "Projects",
        icon: <FolderKanban className="h-4 w-4" />,
      },
      {
        to: "/releases",
        label: "Design Releases",
        icon: <Layers className="h-4 w-4" />,
      },
      {
        to: "/tasks",
        label: "Tasks",
        icon: <ListChecks className="h-4 w-4" />,
      },
      {
        to: "/kanban",
        label: "Task Board",
        icon: <LayoutGrid className="h-4 w-4" />,
      },
      {
        to: "/reviews",
        label: "Reviews",
        icon: <ClipboardCheck className="h-4 w-4" />,
      },
      {
        to: "/revisions",
        label: "Revisions",
        icon: <RotateCcw className="h-4 w-4" />,
      },
      {
        to: "/timesheet",
        label: "Timesheet",
        icon: <Clock className="h-4 w-4" />,
      },
      {
        to: "/templates",
        label: "Templates",
        icon: <FileStack className="h-4 w-4" />,
        anyOf: ["template.view"],
      },
    ],
  },
];

function NotificationBell() {
  const [open, setOpen] = useState(false);
  const { data: count } = useUnreadCount();
  const { data: page, isLoading } = useNotifications({ page_size: 8 });
  const markAll = useMarkAllRead();

  const unread = count?.unread ?? 0;

  return (
    <div className="relative">
      <button
        type="button"
        className="btn-ghost relative px-2"
        onClick={() => setOpen((v) => !v)}
        aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
        aria-expanded={open}
      >
        <Bell className="h-4 w-4" />
        {unread > 0 && (
          <span className="absolute right-0.5 top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-rag-red px-1 text-[10px] font-semibold text-white">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <>
          <div
            className="fixed inset-0 z-10"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <div className="absolute right-0 z-20 mt-1 w-[min(20rem,calc(100vw-1.5rem))] rounded-lg border border-ink-200 bg-white shadow-pop">
            <div className="flex items-center justify-between border-b border-ink-200 px-3 py-2">
              <span className="text-xs font-semibold text-ink-800">Notifications</span>
              {unread > 0 && (
                <button
                  type="button"
                  className="text-xs text-signal-700 hover:underline disabled:opacity-50"
                  onClick={() => markAll.mutate()}
                  disabled={markAll.isPending}
                >
                  Mark all read
                </button>
              )}
            </div>
            <div className="max-h-80 overflow-y-auto">
              {isLoading && (
                <div className="flex justify-center py-6">
                  <Spinner />
                </div>
              )}
              {!isLoading && (page?.items.length ?? 0) === 0 && (
                <p className="px-3 py-6 text-center text-xs text-ink-500">
                  Nothing to catch up on.
                </p>
              )}
              {page?.items.map((n) => (
                <div
                  key={n.id}
                  className={clsx(
                    "border-b border-ink-100 px-3 py-2 last:border-0",
                    !n.is_read && "bg-signal-50/50",
                  )}
                >
                  <div className="flex items-start gap-2">
                    <span
                      className={clsx(
                        "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full",
                        n.severity === "Critical"
                          ? "bg-rag-red"
                          : n.severity === "Warning"
                            ? "bg-rag-amber"
                            : "bg-signal-500",
                      )}
                    />
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-ink-900">{n.title}</p>
                      {n.body && (
                        <p className="mt-0.5 line-clamp-2 text-2xs text-ink-600">
                          {n.body}
                        </p>
                      )}
                      <p className="mt-0.5 text-2xs text-ink-400">
                        {relative(n.created_at)}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

/**
 * The running timer, visible from every screen.
 *
 * A timer left running quietly inflates a task's actual hours and skews its
 * efficiency, so it should never be possible to forget one is going. Elapsed
 * time is computed client-side because a running entry reports hours = 0 until
 * it is stopped, and nothing pushes updates.
 */
function RunningTimer() {
  const { data } = useRunningTimer();
  const stop = useStopTimer();
  const [, tick] = useState(0);

  useEffect(() => {
    if (!data) return;
    const timer = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(timer);
  }, [data]);

  if (!data) return null;

  const seconds = Math.max(
    0,
    (Date.now() - new Date(data.started_at ?? Date.now()).getTime()) / 1000,
  );
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);

  return (
    <div className="flex items-center gap-2 rounded-md border border-signal-200 bg-signal-50 px-2 py-1">
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-signal-600" />
      <Link
        to={`/tasks/${data.task_id}`}
        className="hidden max-w-[9rem] truncate text-xs text-signal-700 hover:underline sm:block"
        title={data.task_name ?? undefined}
      >
        {data.task_code}
      </Link>
      <span className="font-mono text-xs tabular text-signal-700">
        {h}:{String(m).padStart(2, "0")}
      </span>
      <button
        type="button"
        className="btn-ghost px-1 py-0.5"
        onClick={() => stop.mutate()}
        disabled={stop.isPending}
        aria-label="Stop the running timer"
        title="Stop timer"
      >
        {stop.isPending ? <Spinner /> : <Square className="h-3 w-3 text-rag-red" />}
      </button>
    </div>
  );
}

function Breadcrumbs() {
  const { pathname } = useLocation();
  const parts = pathname.split("/").filter(Boolean);
  if (parts.length === 0) return null;

  const label = (part: string) =>
    part
      .replace(/-/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-xs text-ink-500">
      <Link to="/" className="hover:text-ink-800">
        Home
      </Link>
      {parts.map((part, index) => (
        <span key={index} className="flex items-center gap-1">
          <ChevronRight className="h-3 w-3 text-ink-300" />
          <span className={index === parts.length - 1 ? "text-ink-800" : undefined}>
            {label(part)}
          </span>
        </span>
      ))}
    </nav>
  );
}

export default function AppLayout() {
  const { user, signOut, canAny } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  // Navigating on a phone should close the drawer, or the new page is hidden
  // behind it.
  useEffect(() => setMobileOpen(false), [location.pathname]);

  const sections = NAV_SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter((item) => !item.anyOf || canAny(...item.anyOf)),
  })).filter((section) => section.items.length > 0);

  const handleSignOut = () => {
    signOut();
    navigate("/login", { replace: true });
  };

  return (
    <div className="flex h-full">
      <aside
        className={clsx(
          "fixed inset-y-0 left-0 z-40 flex w-[17rem] max-w-[85vw] flex-col border-r border-ink-200 bg-white transition-transform lg:static lg:z-30 lg:w-60 lg:max-w-none lg:translate-x-0 lg:shadow-none",
          mobileOpen ? "shadow-pop" : "",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex h-14 items-center justify-between border-b border-ink-200 px-4">
          <Link to="/" className="flex min-w-0 items-center gap-2">
            <img
              src={siegerLogo}
              alt="Sieger"
              className="h-7 w-auto shrink-0"
              width={1533}
              height={525}
            />
            <span className="min-w-0 border-l border-ink-200 pl-2">
              <span className="block truncate font-display text-xs font-semibold leading-tight text-ink-900">
                Design Ops
              </span>
              <span className="block truncate text-[10px] leading-tight text-signal-700">
                Partnering Progress
              </span>
            </span>
          </Link>
          <button
            type="button"
            className="btn-ghost px-1 lg:hidden"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-2 py-3">
          {sections.map((section) => (
            <div key={section.heading} className="mb-4">
              <p className="px-2 pb-1 text-2xs font-semibold uppercase tracking-wide text-ink-400">
                {section.heading}
              </p>
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    clsx(
                      "flex items-center gap-2 rounded-md px-2 py-2 text-sm transition-colors lg:py-1.5",
                      isActive
                        ? "bg-signal-50 font-medium text-signal-700"
                        : "text-ink-700 hover:bg-ink-100",
                    )
                  }
                >
                  {item.icon}
                  {item.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="border-t border-ink-200 p-3">
          <div className="flex items-center gap-2">
            <Avatar name={user?.full_name} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-medium text-ink-900">
                {user?.full_name}
              </p>
              <p className="truncate text-2xs text-ink-500">{user?.primary_role}</p>
            </div>
            <button
              type="button"
              className="btn-ghost px-1.5"
              onClick={handleSignOut}
              title="Sign out"
              aria-label="Sign out"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      {mobileOpen && (
        <div
          className="fixed inset-0 z-20 bg-ink-900/30 lg:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden
        />
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between gap-2 border-b border-ink-200 bg-white px-3 sm:px-4">
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="btn-ghost px-2 lg:hidden"
              onClick={() => setMobileOpen(true)}
              aria-label="Open navigation"
            >
              <Menu className="h-5 w-5" />
            </button>
            <div className="hidden sm:block">
              <Breadcrumbs />
            </div>
            <img
              src={siegerLogo}
              alt="Sieger"
              className="h-6 w-auto sm:hidden"
              width={1533}
              height={525}
            />
          </div>
          <div className="flex items-center gap-2">
            <RunningTimer />
            <NotificationBell />
          </div>
        </header>

        <main className="min-w-0 flex-1 overflow-y-auto p-3 pb-safe sm:p-4 lg:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
