# Running this in production

The department's data lives in PostgreSQL on a machine Sieger owns. Everything
else follows from that.

## The shape

```
  designer's browser
        |
        |  HTTPS
        v
  Vercel  ................  the built React app, static files only
        |
        |  HTTPS, one call per user action, carries a bearer token
        v
  Tailscale Funnel  .......  public HTTPS name, no open ports on the machine
        |
        |  localhost
        v
  FastAPI (uvicorn)  ......  on the machine that holds the database
        |
        |  localhost:5432, never leaves the machine
        v
  PostgreSQL  .............  the department's data
```

The API sits next to the database rather than in the cloud, and that is the
whole point of the layout. One page in this app runs several SQL queries; with
the API in a datacentre and the database on an office machine, each of those
queries would cross the internet separately and the app would feel broken. Here
only the API call crosses, once.

It also means no database port is exposed. Postgres listens on localhost, the
Funnel publishes only the API, and the API requires a login.

## What breaks, and when

**The site is down whenever that machine is asleep, shut down, or off the
network.** Vercel keeps serving the page, so people see the app load and then
fail to sign in. There is no way around this while the data lives on a machine
that sleeps; the fix is to run it on something that stays on.

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

A database that was used for development carries projects the test suite
invented. Check what would go, then remove it:

```
.venv\Scripts\python scripts\clean_test_data.py
.venv\Scripts\python scripts\clean_test_data.py --apply
```

Back up first: `pg_dump -U designops -h 127.0.0.1 -d designops -F c -f backup.dump`

### 3. Publish the API

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

### 4. Keep it running

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
| `FRONTEND_URL` | the site's origin, or the browser blocks every call with a CORS error |
| `EXTRA_CORS_ORIGINS` | further allowed origins, comma separated |
| `CORS_ORIGIN_REGEX` | preview deployments, which get a generated subdomain per build |

A CORS mistake is worth recognising on sight: the API answers `curl` perfectly
and fails in the browser with nothing useful in the network tab. It means the
site's origin is not in the allowed list — including when it differs only by a
trailing slash.

## On Vercel

Set the project's **Root Directory** to `frontend`.

`VITE_API_BASE_URL` must point at the API's public name. It is baked into the
bundle at build time, so changing it needs a redeploy, not a restart. The repo
carries it in `frontend/.env.production`; **a value set in the Vercel dashboard
overrides that file**, so if the dashboard still holds an older API address,
that is what ships.
