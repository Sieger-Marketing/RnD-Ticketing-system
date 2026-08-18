import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { InlineAlert, Spinner } from "@/components/ui/primitives";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/store/auth";

export default function Login() {
  const { user, initializing, signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!initializing && user) {
    const from = (location.state as { from?: Location } | null)?.from?.pathname;
    return <Navigate to={from ?? user.home_route} replace />;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const signedIn = await signIn(email.trim(), password);
      // Land on the dashboard the role implies, decided by the server.
      navigate(signedIn.home_route, { replace: true });
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Sign-in failed. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-ink-100 px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <span className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-brand-600 text-sm font-bold text-white">
            DO
          </span>
          <h1 className="text-lg font-semibold text-ink-900">Design Operations</h1>
          <p className="mt-0.5 text-sm text-ink-500">
            Sign in to your design department workspace
          </p>
        </div>

        <form onSubmit={handleSubmit} className="card space-y-4 p-5" noValidate>
          {error && <InlineAlert tone="error">{error}</InlineAlert>}

          <div>
            <label className="label" htmlFor="email">
              Email address
            </label>
            <input
              id="email"
              className="input"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
            />
          </div>

          <div>
            <label className="label" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              className="input"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          <button
            type="submit"
            className="btn-primary w-full"
            disabled={busy || !email || !password}
          >
            {busy && <Spinner />}
            {busy ? "Signing in" : "Sign in"}
          </button>
        </form>

        <p className="mt-4 text-center text-2xs text-ink-400">
          Access is governed by your role. Contact your Design Manager if you need
          different permissions.
        </p>
      </div>
    </div>
  );
}
