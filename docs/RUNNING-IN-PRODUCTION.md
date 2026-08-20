# Running this in production

The department's data lives in PostgreSQL on a machine Sieger owns. Everything
else follows from that.

## The shape

```
  designer's browser
        |
        |  HTTPS
        v
  Tailscale Funnel  .......  https://<machine>.<tailnet>.ts.net
        |                     a real certificate, no open ports
        |  localhost
        v
  FastAPI (uvicorn)  ......  serves the API *and* the built app
        |
        |  localhost:5432, never leaves the machine
        v
  PostgreSQL  .............  the department's data
```

One process. The database is on this machine, so the API is on this machine,
and once that is true there is little reason for the app to be somewhere else:
serving it from the same process means one origin, no CORS, no second
deployment to keep in step, and one build that works both on the office network
and through the tunnel.

Nothing is hosted elsewhere. No database port is exposed -- Postgres listens on
localhost, the Funnel publishes only port 8000, and the app requires a login.

## What breaks, and when

**The site is down whenever that machine is asleep, shut down, or off the
network.** The Funnel has nothing to proxy to, so visitors get an error rather
than the app. There is no way around this while the data lives on a machine
that sleeps; the fix is to run it on something that stays on.

The same is true if the API process stops but the machine keeps running, which
is why it belongs in Task Scheduler rather than in a terminal window somebody
might close.

## One-time setup on the machine that holds the database

### 1. A scratch database for the tests

The suite writes projects, users and time entries and deletes none of them, so
it must never point at the live database — `tests/conftest.py` now refuses to
start if it does. Give it its own database. In psql as a superuser:

```sql
CREATE DATABASE designops_test OWNER designops;
```

Then run the suite against it:

```
set TEST_DATABASE_URL=postgresql+psycopg://designops:PASSWORD@127.0.0.1:5432/designops_test
.venv\Scripts\python -m pytest
```

The fixtures migrate and seed that database themselves on first run.

### 2. Clear out test debris

A database used for development carries the demo department the seed invents
and the projects the suite leaves behind. Check what would go, then remove it:

```
.venv\Scripts\python scriptseset_to_live_data.py
.venv\Scripts\python scriptseset_to_live_data.py --apply
```

An administrator can do the same thing through the app -- `POST
/api/admin/purge-demo-data`, which reads only until given `?apply=true` -- for
a deployment where no shell is available.

Back up first: `pg_dump -U designops -h 127.0.0.1 -d designops -F c -f backup.dump`

### 3. Build the app

The API serves it, so it has to exist:

```
cd frontend
npm install
npm run build
```

### 4. Publish it

Tailscale is the least exposed way to do this: the machine dials out, so no
router change and no inbound firewall rule, and the name it gets is stable.

Funnel has to be permitted for the tailnet once, in the admin console under
**Access controls**, by adding:

```json
"nodeAttrs": [
  { "target": ["autogroup:member"], "attr": ["funnel"] }
]
```

Then, on the machine:

```
tailscale funnel --bg 8000
tailscale funnel status
```

That publishes `http://127.0.0.1:8000` at `https://<machine>.<tailnet>.ts.net`
with a real certificate. Nothing else on the machine becomes reachable.

For this department that address is:

    https://u1-l-2rkv8f4.tailc2b13d.ts.net

### 5. Keep it running

`scripts/serve.ps1` runs the API in the foreground. For daily use it should
start with the machine — a Task Scheduler entry set to "run whether user is
logged on or not", or a service wrapper such as NSSM. Both are outside what
this repo configures.

## Daily operation

```
cd backend
.\scripts\serve.ps1
```

It applies any pending migrations, then serves on `127.0.0.1:8000`. Add `-Lan`
to also answer on the office network, which is useful when the Funnel is down
and people are in the building.

Two probes:

- `/health` — the process is alive. Touches nothing.
- `/health/db` — the database answers. This is the one to check when people
  report they cannot sign in.

## Settings that matter

In `backend/.env`:

| Setting | Why |
|---|---|
| `ENVIRONMENT=production` | turns on the startup check that refuses development defaults |
| `DATABASE_URL` | must be set explicitly, even pointing at this machine |
| `SECRET_KEY`, `JWT_SECRET` | anything starting `dev-only` is refused |
| `SEED_DEFAULT_PASSWORD` | the published default is refused |
| `FRONTEND_DIST_PATH` | where the built app is; when it exists this process serves it |
| `FRONTEND_URL`, `EXTRA_CORS_ORIGINS`, `CORS_ORIGIN_REGEX` | only matter if the app is hosted separately; with one process there is no cross-origin call to allow |

A CORS mistake is worth recognising on sight: the API answers `curl` perfectly
and fails in the browser with nothing useful in the network tab. It means the
site's origin is not in the allowed list — including when it differs only by a
trailing slash.

## Hosting the app separately (not needed any more)

The app used to be deployed to Vercel, with the API somewhere else. That is no
longer the arrangement and nothing depends on it. If it is ever revived,
`VITE_API_BASE_URL` in `frontend/.env.production` must be set to the API's
absolute address -- it is deliberately empty now, which is what makes the
single-process setup work -- and Vite bakes it in at build time, so changing it
needs a rebuild rather than a restart.
