/**
 * Routing.
 *
 * Route guards mirror the backend's permission gates. They are a usability
 * measure, not a security one -- the API enforces authorisation regardless of
 * what the client renders -- so their job is to avoid showing a user a screen
 * that would only return 403.
 */

import { useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { LoadingBlock } from "@/components/ui/primitives";
import AppLayout from "@/layouts/AppLayout";
import Catalog from "@/routes/Catalog";
import Connections from "@/routes/Connections";
import DesignerDashboard from "@/routes/DesignerDashboard";
import ExecutiveDashboard from "@/routes/ExecutiveDashboard";
import Login from "@/routes/Login";
import ManagerDashboard from "@/routes/ManagerDashboard";
import NotFound from "@/routes/NotFound";
import ProjectDetail from "@/routes/ProjectDetail";
import Projects from "@/routes/Projects";
import ReleaseDetail from "@/routes/ReleaseDetail";
import Insights from "@/routes/Insights";
import Kanban from "@/routes/Kanban";
import Releases from "@/routes/Releases";
import Reports from "@/routes/Reports";
import Reviews from "@/routes/Reviews";
import Revisions from "@/routes/Revisions";
import Standards from "@/routes/Standards";
import TeamLeadDashboard from "@/routes/TeamLeadDashboard";
import TaskDetail from "@/routes/TaskDetail";
import Tasks from "@/routes/Tasks";
import Templates from "@/routes/Templates";
import Timesheet from "@/routes/Timesheet";
import Users from "@/routes/Users";
import { useAuth } from "@/store/auth";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, initializing } = useAuth();
  const location = useLocation();

  if (initializing) return <LoadingBlock label="Restoring your session" />;
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
  return <>{children}</>;
}

function RequirePermission({
  anyOf,
  children,
}: {
  anyOf: string[];
  children: React.ReactNode;
}) {
  const canAny = useAuth((s) => s.canAny);
  const user = useAuth((s) => s.user);
  if (!canAny(...anyOf)) {
    // Send them somewhere they can actually use rather than showing a wall.
    return <Navigate to={user?.home_route ?? "/my-work"} replace />;
  }
  return <>{children}</>;
}

/**
 * Sends a signed-in user to the dashboard their primary role implies.
 *
 * home_route is "/" for a user with no role the server recognises, and "/"
 * renders this component -- so redirecting blindly loops until React Router
 * throws and the screen goes blank. A user with no usable role gets their
 * personal queue and an honest message instead.
 */
function HomeRedirect() {
  const user = useAuth((s) => s.user);
  const target = user?.home_route;
  if (!target || target === "/") return <Navigate to="/my-work" replace />;
  return <Navigate to={target} replace />;
}

export default function App() {
  const restore = useAuth((s) => s.restore);

  useEffect(() => {
    void restore();
  }, [restore]);

  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<HomeRedirect />} />

        <Route
          path="/dashboard/executive"
          element={
            <RequirePermission anyOf={["analytics.view_department"]}>
              <ExecutiveDashboard />
            </RequirePermission>
          }
        />
        <Route
          path="/dashboard/manager"
          element={
            <RequirePermission anyOf={["project.view_all"]}>
              <ManagerDashboard />
            </RequirePermission>
          }
        />
        <Route
          path="/dashboard/team-lead"
          element={
            <RequirePermission anyOf={["analytics.view_team", "analytics.view_department"]}>
              <TeamLeadDashboard />
            </RequirePermission>
          }
        />
        <Route path="/my-work" element={<DesignerDashboard />} />

        {/* Projects and releases are readable by anyone who can see a task;
            the API scopes the rows each role is entitled to. */}
        <Route path="/projects" element={<Projects />} />
        <Route path="/projects/:projectId" element={<ProjectDetail />} />
        <Route path="/releases" element={<Releases />} />
        <Route path="/releases/:releaseId" element={<ReleaseDetail />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/tasks/:taskId" element={<TaskDetail />} />
        <Route path="/kanban" element={<Kanban />} />
        <Route path="/reviews" element={<Reviews />} />
        <Route path="/revisions" element={<Revisions />} />
        <Route path="/timesheet" element={<Timesheet />} />

        {/* The release standard is reference material for the whole team --
            a designer benefits from seeing where their release sits. */}
        <Route path="/standards" element={<Standards />} />

        <Route
          path="/insights"
          element={
            <RequirePermission anyOf={["analytics.view_department", "analytics.view_team"]}>
              <Insights />
            </RequirePermission>
          }
        />
        <Route
          path="/reports"
          element={
            <RequirePermission anyOf={["report.export"]}>
              <Reports />
            </RequirePermission>
          }
        />

        <Route
          path="/connections"
          element={
            <RequirePermission anyOf={["settings.view"]}>
              <Connections />
            </RequirePermission>
          }
        />

        <Route
          path="/catalogue"
          element={
            <RequirePermission anyOf={["project.view_all", "settings.manage"]}>
              <Catalog />
            </RequirePermission>
          }
        />

        <Route
          path="/people"
          element={
            <RequirePermission anyOf={["user.view"]}>
              <Users />
            </RequirePermission>
          }
        />

        <Route
          path="/templates"
          element={
            <RequirePermission anyOf={["template.view"]}>
              <Templates />
            </RequirePermission>
          }
        />

        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
