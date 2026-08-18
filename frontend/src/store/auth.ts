/**
 * Session state.
 *
 * The token lives in localStorage so a refresh does not sign the user out; the
 * user object is re-fetched from `/auth/me` on boot rather than persisted, so
 * a revoked role or permission takes effect on the next page load instead of
 * lingering in stale client state.
 */

import { create } from "zustand";

import { get, post, setStoredToken, getStoredToken } from "@/lib/api";
import type { CurrentUser, TokenResponse } from "@/types/api";

interface AuthState {
  user: CurrentUser | null;
  token: string | null;
  /** True until the initial `/auth/me` check has settled. */
  initializing: boolean;
  signIn: (email: string, password: string) => Promise<CurrentUser>;
  signOut: () => void;
  restore: () => Promise<void>;
  can: (...permissions: string[]) => boolean;
  canAny: (...permissions: string[]) => boolean;
  hasRole: (...roles: string[]) => boolean;
}

export const useAuth = create<AuthState>((set, getState) => ({
  user: null,
  token: getStoredToken(),
  initializing: true,

  async signIn(email, password) {
    const data = await post<TokenResponse>("/api/auth/login", { email, password });
    setStoredToken(data.access_token);
    set({ token: data.access_token, user: data.user, initializing: false });
    return data.user;
  },

  signOut() {
    setStoredToken(null);
    set({ token: null, user: null, initializing: false });
  },

  async restore() {
    const token = getStoredToken();
    if (!token) {
      set({ token: null, user: null, initializing: false });
      return;
    }
    try {
      const user = await get<CurrentUser>("/api/auth/me");
      set({ token, user, initializing: false });
    } catch {
      // Expired or revoked: the interceptor has already cleared the token.
      set({ token: null, user: null, initializing: false });
    }
  },

  can(...permissions) {
    const held = getState().user?.permissions;
    if (!held) return false;
    return permissions.every((p) => held.includes(p));
  },

  canAny(...permissions) {
    const held = getState().user?.permissions;
    if (!held) return false;
    return permissions.some((p) => held.includes(p));
  },

  hasRole(...roles) {
    const held = getState().user?.roles;
    if (!held) return false;
    return roles.some((r) => held.includes(r));
  },
}));

/** Permission codes the UI references. Mirrors backend app/core/permissions.py. */
export const P = {
  projectViewAll: "project.view_all",
  projectCreate: "project.create",
  projectUpdate: "project.update",
  releaseCreate: "release.create",
  releaseUpdate: "release.update",
  releaseAssignLead: "release.assign_lead",
  releaseAccept: "release.accept",
  releaseComplete: "release.complete",
  releaseOverrideCompletion: "release.override_completion",
  templateView: "template.view",
  templateManage: "template.manage",
  templateApply: "template.apply",
  taskViewAll: "task.view_all",
  taskViewTeam: "task.view_team",
  taskCreate: "task.create",
  taskUpdate: "task.update",
  taskAssign: "task.assign",
  taskEstimate: "task.estimate",
  taskExecute: "task.execute",
  timeLogOwn: "time.log_own",
  reviewPerform: "review.perform",
  revisionCreate: "revision.create",
  resourceViewAll: "resource.view_all",
  resourceViewTeam: "resource.view_team",
  resourceManage: "resource.manage",
  skillView: "skill.view",
  analyticsDepartment: "analytics.view_department",
  analyticsTeam: "analytics.view_team",
  analyticsOwn: "analytics.view_own",
  reportExport: "report.export",
  userView: "user.view",
  userManage: "user.manage",
  settingsView: "settings.view",
  settingsManage: "settings.manage",
  auditView: "audit.view",
} as const;
