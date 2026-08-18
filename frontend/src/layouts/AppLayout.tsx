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
  ChevronRight,
  FileStack,
  FolderKanban,
  Layers,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  X,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { Avatar, Spinner } from "@/components/ui/primitives";
import { useMarkAllRead, useNotifications, useUnreadCount } from "@/hooks/queries";
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
          <div className="absolute right-0 z-20 mt-1 w-80 rounded-lg border border-ink-200 bg-white shadow-pop">
            <div className="flex items-center justify-between border-b border-ink-200 px-3 py-2">
              <span className="text-xs font-semibold text-ink-800">Notifications</span>
              {unread > 0 && (
                <button
                  type="button"
                  className="text-xs text-brand-600 hover:underline disabled:opacity-50"
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
                    !n.is_read && "bg-brand-50/40",
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
                            : "bg-brand-500",
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
          "fixed inset-y-0 left-0 z-30 flex w-60 flex-col border-r border-ink-200 bg-white transition-transform lg:static lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex h-14 items-center justify-between border-b border-ink-200 px-4">
          <Link to="/" className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded bg-brand-600 text-xs font-bold text-white">
              DO
            </span>
            <span className="text-sm font-semibold text-ink-900">Design Ops</span>
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
                      "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors",
                      isActive
                        ? "bg-brand-50 font-medium text-brand-700"
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
        <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-ink-200 bg-white px-4">
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="btn-ghost px-1.5 lg:hidden"
              onClick={() => setMobileOpen(true)}
              aria-label="Open navigation"
            >
              <Menu className="h-4 w-4" />
            </button>
            <Breadcrumbs />
          </div>
          <div className="flex items-center gap-1">
            <NotificationBell />
          </div>
        </header>

        <main className="min-w-0 flex-1 overflow-y-auto p-4 lg:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
