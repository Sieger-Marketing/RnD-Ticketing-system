# Running this in production

The department's data lives in PostgreSQL on a machine Sieger owns, and it
lives nowhere else. That is a deliberate decision, and everything below follows
from it — including the two things it costs you, which are covered under
[Availability](#availability-is-one-machines-uptime) and [Backups](#backups).

## The shape

```
  designer's browser
        |
        |  HTTPS
        v
  rn-d-ticketing-system.vercel.app ....  the address the team knows.
        |                                Vercel serves the built app and
        |  rewrites /api/* and /health*  rewrites the API through, so the
        v                                browser only ever sees one origin.
  Tailscale Funnel  ..................   https://<machine>.<tailnet>.ts.net
        |                                a real certificate, no open ports
        |  localhost
        v
  FastAPI (uvicorn)  .................   the API, and the built app as well
        |
        |  localhost:5432, never leaves the machine
        v
  PostgreSQL  ........................   the department's data
```

Two things are worth understanding about this.

**The API address is not baked into the build.** It is a rewrite in
`frontend/vercel.json`. If the tunnel name ever changes, that is one line and a
redeploy of a static site — not a rebuild with a new `VITE_API_BASE_URL`. It
also means the browser makes same-origin requests, so there is no CORS
preflight and no allow-list to keep in step.

**The app is reachable two ways.** Through Vercel, and directly at the
`ts.net` address, because the API process also serves `frontend/dist`
(`app/main.py`). The direct address is the one to use when checking whether the
machine itself is healthy, since it bypasses Vercel entirely.

## Availability is one machine's uptime

Everything except the static frontend runs on the host machine. So:

> **The portal is down whenever that machine is asleep, shut down, or off the
> network.**

It does not fail cleanly. Vercel keeps serving the page from its CDN, so the
site still loads, users still see a login screen, and then every request times
out. It reads like a broken application rather than a machine that is off.

Three consequences worth acting on:

* **A laptop is the wrong host.** Sleep, lid-close, being carried home and
  shut — each one is an outage. Use a machine that stays on: a mini PC, a spare
  desktop, or a server. Nothing about the setup changes; it is the same folder
  and the same steps on a machine that does not sleep.
* **The API must start by itself.** PostgreSQL and Tailscale are both
  `Automatic` Windows services and come back after a reboot on their own. The
  API does not, unless installed to. `scripts\install-autostart.ps1` does that.
* **Nothing else may serve this application.** If a second deployment exists
  anywhere, it has its own database, and anyone reaching it enters work that
  will never appear here. Shut down any old hosting rather than leaving it
  running.

## One-time setup on the host machine

### 1. A scratch database for the tests

The suite writes projects, users and time entries and deletes none of them, so
it must never point at the live database — `tests/conftest.py` refuses to start
if it does. Give it its own database. In psql as a superuser:

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
.venv\Scripts\python scripts\reset_to_live_data.py
.venv\Scripts\python scripts\reset_to_live_data.py --apply
```

An administrator can do the same through the app — `POST
/api/admin/purge-demo-data`, which reads only until given `?apply=true` — for a
deployment where no shell is available.

Take a backup first (see [Backups](#backups)).

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

It is also the `destination` in `frontend/vercel.json`. If it changes, change
it there too.

### 5. Make it start by itself, and back itself up

From `backend\`, in an **elevated** PowerShell:

```
.\scripts\install-autostart.ps1 -BackupTo E:\Backups
```

That registers two scheduled tasks and adjusts power settings:

| What | Effect |
|---|---|
| `DesignOps API` | Runs `scripts\run-service.ps1` at boot, as SYSTEM. Migrates, then serves, then restarts the server if it exits. |
| `DesignOps Database Backup` | Nightly `pg_dump`, rotated. |
| Power | Sleep and hibernate off on AC; lid-close does nothing on AC. |

Both tasks run as SYSTEM, which needs no stored password and survives the user
logging off. Undo the whole thing with `-Uninstall`.

Start it without rebooting, and check:

```
Start-ScheduledTask -TaskName 'DesignOps API'
curl http://127.0.0.1:8000/health/db
```

## Backups

There is one copy of the department's data. A failed disk loses every project,
release, task and timesheet recorded since go-live, with nothing to restore
from. The nightly task installed above is what stands between you and that.

```
.\scripts\backup-db.ps1 -Destination E:\Backups -KeepDays 14
```

**`-Destination` must be a different physical disk, or a network share.** A
backup sitting beside the database survives an accidental delete but not a dead
drive, and the dead drive is the failure that actually costs you the year.

The script reads the connection details from `.env`, so it cannot drift onto a
different database from the one the app uses. It fails loudly rather than
quietly rotating good backups out in favour of a bad one: a non-zero `pg_dump`
exit, or a dump too small to be real, is treated as failure.

Check it after installing, and then occasionally:

```
Get-Content backend\logs\backup.log -Tail 20
```

### Restoring

A backup nobody has restored is a hypothesis. Test it into a scratch database
rather than the live one:

```
createdb -U postgres -O designops designops_restore_test
pg_restore -U designops -h 127.0.0.1 -d designops_restore_test --no-owner "E:\Backups\designops_<stamp>.dump"
```

To see what a dump contains without restoring it:

```
pg_restore --list "E:\Backups\designops_<stamp>.dump"
```

Restoring over the live database is a deliberate, destructive act — stop the
`DesignOps API` task first, so the application is not writing while you do it.

## Daily operation

Nothing, if the tasks are installed. To run it in the foreground instead — for
debugging, or on a machine where you have not installed the task:

```
cd backend
.\scripts\serve.ps1
```

`serve.ps1` is the interactive version: it applies migrations, builds the
frontend if the build is missing, and serves on `127.0.0.1:8000`. Add `-Lan` to
also answer on the office network, which is useful when the Funnel is down and
people are in the building.

Logs from the scheduled task:

```
backend\logs\service-<date>.log
backend\logs\backup.log
```

Three probes, in order of how much they tell you:

| Probe | Answers |
|---|---|
| `https://rn-d-ticketing-system.vercel.app/health` | the whole path works, end to end |
| `https://u1-l-2rkv8f4.tailc2b13d.ts.net/health` | the machine and tunnel are up; Vercel is not in the way |
| `http://127.0.0.1:8000/health/db` | run on the host: the API is up and the database answers |

The first is the one to point an uptime monitor at, because it is the only one
that fails when any part of the chain does.

## Settings that matter

In `backend\.env`:

| Setting | Why |
|---|---|
| `ENVIRONMENT=production` | turns on the startup check that refuses development defaults |
| `DATABASE_URL` | must be set explicitly, even pointing at this machine |
| `SECRET_KEY`, `JWT_SECRET` | anything starting `dev-only` is refused |
| `SEED_DEFAULT_PASSWORD` | the published default is refused |
| `FRONTEND_DIST_PATH` | where the built app is; when it exists this process serves it |
| `FRONTEND_URL`, `EXTRA_CORS_ORIGINS`, `CORS_ORIGIN_REGEX` | the Vercel origins. Only consulted if a browser ever calls the API cross-origin; with the rewrite in place it does not. |

A CORS mistake is worth recognising on sight: the API answers `curl` perfectly
and fails in the browser with nothing useful in the network tab. It means the
site's origin is not in the allowed list — including when it differs only by a
trailing slash.
