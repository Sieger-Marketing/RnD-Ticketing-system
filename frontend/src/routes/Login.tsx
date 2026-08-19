import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import siegerLogo from "@/assets/sieger-logo.png";
import { InlineAlert, Spinner } from "@/components/ui/primitives";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/store/auth";

export default function Login() {
  const { user, initializing, signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!initializing && user) {
    const from = (location.state as { from?: Location } | null)?.from?.pathname;
    const home = user.home_route && user.home_route !== "/" ? user.home_route : "/my-work";
    return <Navigate to={from ?? home} replace />;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const signedIn = await signIn(identifier.trim(), password);
      // Land on the dashboard the role implies, decided by the server. "/"
      // means the server had no route for this user's role; sending them there
      // would bounce them straight back into HomeRedirect.
      const target =
        signedIn.home_route && signedIn.home_route !== "/"
          ? signedIn.home_route
          : "/my-work";
      navigate(target, { replace: true });
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Sign-in failed. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-cream-200 px-4 py-8 sm:py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <img
            src={siegerLogo}
            alt="Sieger"
            className="mx-auto mb-4 h-12 w-auto sm:h-14"
            width={1533}
            height={525}
          />
          <h1 className="font-display text-lg font-semibold text-ink-900">
            Design Operations
          </h1>
          <p className="mt-0.5 text-sm text-ink-500">
            Sign in to your design department workspace
          </p>
        </div>

        <form onSubmit={handleSubmit} className="card space-y-4 p-5" noValidate>
          {error && <InlineAlert tone="error">{error}</InlineAlert>}

          <div>
            <label className="label" htmlFor="identifier">
              Employee code or email
            </label>
            <input
              id="identifier"
              className="input"
              // Deliberately not type="email": most people here sign in as
              // SIES00267, and the browser would refuse to submit that.
              type="text"
              inputMode="text"
              autoCapitalize="characters"
              autoComplete="username"
              required
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              placeholder="SIES00267 or you@sieger.in"
            />
            <p className="mt-1 text-xs text-ink-500">
              Designers sign in with their employee code. Managers and the
              administrator use their email address.
            </p>
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
            disabled={busy || !identifier || !password}
          >
            {busy && <Spinner />}
            {busy ? "Signing in" : "Sign in"}
          </button>
        </form>

        <p className="mt-4 text-center text-2xs text-ink-400">
          Access is governed by your role. Contact your Design Manager if you need
          different permissions.
        </p>
        <p className="mt-5 text-center font-display text-2xs font-medium uppercase tracking-[0.2em] text-signal-700">
          Partnering Progress
        </p>
      </div>
    </div>
  );
}
