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
import DesignerDashboard from "@/routes/DesignerDashboard";
import ExecutiveDashboard from "@/routes/ExecutiveDashboard";
import Login from "@/routes/Login";
import ManagerDashboard from "@/routes/ManagerDashboard";
import NotFound from "@/routes/NotFound";
import ProjectDetail from "@/routes/ProjectDetail";
import Projects from "@/routes/Projects";
import ReleaseDetail from "@/routes/ReleaseDetail";
import Releases from "@/routes/Releases";
import TeamLeadDashboard from "@/routes/TeamLeadDashboard";
import Templates from "@/routes/Templates";
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

/** Sends a signed-in user to the dashboard their primary role implies. */
function HomeRedirect() {
  const user = useAuth((s) => s.user);
  return <Navigate to={user?.home_route ?? "/my-work"} replace />;
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
