# Running this in production

The department's data lives in PostgreSQL on a machine Sieger owns, and nowhere
else. Everything below follows from that — including the one risk it leaves
open, under [Backups](#backups).

Migrated from a laptop to a dedicated server on 31 August 2026. That laptop is
now a development machine and nothing here depends on it.

## The shape

```
  designer's browser
        |
        |  HTTPS
        v
  rn-d-ticketing-system.vercel.app ....  the address the team uses. Vercel
        |                                serves the built app and rewrites
        |  rewrites /api/* and /health*  /api through to the tunnel, so the
        v                                browser only ever sees one origin.
  desktop-h993ees.tailc2b13d.ts.net ...  Tailscale Funnel on the server itself.
        |                                A real certificate, no open ports.
        |  localhost
        v
  FastAPI (uvicorn)  .................   the API, and the built app as well
        |                                192.168.2.253:8000
        |  localhost:5432
        v
  PostgreSQL 18  .....................   the department's data
```

**The office has a second way in that skips all of it.** The API binds
`0.0.0.0`, so anyone on the office network can reach `http://192.168.2.253:8000`
directly. If Vercel or the tunnel is having a bad day, the department is not
blocked — which is worth knowing before anyone panics.

**The API address is not baked into the build.** It is a rewrite in
`frontend/vercel.json`. If the tunnel name changes, that is one line and a
redeploy of a static site, not a rebuild.

## The machine

| | |
|---|---|
| Address | `192.168.2.253`, **static** — confirmed with IT, not a DHCP lease |
| Tailnet name | `desktop-h993ees` |
| Public address | `https://desktop-h993ees.tailc2b13d.ts.net` |
| Repo | `D:\Design-Ops-System` |
| Database | PostgreSQL 18, database `designops`, schema at `c3e8a5d17b40` |
| Python | **3.12** — 3.14 is also installed, see the warning below |
| Disk | One physical SSD, partitioned C: and D: |

### Python: use 3.12 explicitly

Both 3.12 and 3.14 are installed. `python` resolves to **3.14**, and
`requirements.txt` pins packages with no 3.14 wheels — `pip install` would try
to compile from source and fail confusingly. Always:

```
py -3.12 -m venv .venv
```

The existing `.venv` is already 3.12; this matters only when rebuilding it.

### PowerShell execution policy

A fresh Windows install refuses to run `.ps1` files. The scheduled tasks are
unaffected — they pass `-ExecutionPolicy Bypass` — but running anything by hand
needs this once per machine:

```
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## What runs, and when

Three scheduled tasks, all as SYSTEM, registered by
`scripts\install-autostart.ps1`. SYSTEM needs no stored password and survives
the user logging off.

| Task | Trigger | What it does |
|---|---|---|
| `DesignOps API` | At startup | Migrates, bootstraps, serves on `0.0.0.0:8000`, restarts the server if it exits |
| `DesignOps Database Backup` | 20:00 daily | `pg_dump` with rotation |
| `DesignOps Nightly Refresh` | 06:30 daily | Re-rates delay days and RAG health against today's date |

The nightly refresh is the one that fails invisibly. Nothing about a release
changes when it slips past its date overnight, so without it the portal keeps
showing yesterday's colours and looks perfectly healthy while doing so.

Also set by the installer: sleep and hibernate disabled on AC, and a firewall
rule allowing inbound TCP 8000 so the office can reach it. A SYSTEM task gets
no "allow this app?" prompt, so without that rule the server listens and
nobody can connect.

## Deploying a change

```
laptop  →  git push  →  GitHub  →  Vercel (frontend, automatic)
                             └──→  server: git pull + restart the task
```

**Frontend only** — Vercel rebuilds on push, nothing to do on the server.

**Backend** — on the server:

```
cd D:\Design-Ops-System; git pull
Stop-ScheduledTask -TaskName 'DesignOps API'; Start-Sleep 3; Start-ScheduledTask -TaskName 'DesignOps API'
```

The server also serves its own copy of the frontend as the office-direct
fallback, so run `npm run build` there too when the UI changes, or that path
serves an older bundle than Vercel does.

**Migrations run automatically** at task start, followed by the bootstrap that
applies new permissions, roles and settings. Both are idempotent.

## Checking it

Three probes, in order of how much they tell you:

| Probe | Answers |
|---|---|
| `https://rn-d-ticketing-system.vercel.app/health` | the whole chain works |
| `https://desktop-h993ees.tailc2b13d.ts.net/health` | server and tunnel are up; Vercel is not in the way |
| `http://192.168.2.253:8000/health/db` | the API is up and the database answers |

**Point an uptime monitor at the first one.** It is the only one that fails
when any part of the chain does — and the chain has already broken silently
once, in a way where the page still loaded and only the data was missing.
Nobody reported it.

Logs on the server:

```
D:\Design-Ops-System\backend\logs\service-<date>.log
D:\Design-Ops-System\backend\logs\backup.log
```

## Backups

There is one copy of this data. The nightly task is what stands between you and
losing every project, release, task and timesheet the department has recorded.

```
.\scripts\backup-db.ps1 -Destination D:\Backups -KeepDays 14
```

> **The open risk.** `D:\Backups` is on the **same physical SSD** as the
> database — C: and D: are partitions of one disk. That survives an accidental
> delete and not a failed drive, which is the failure that actually costs a
> department its year. It needs a network share or a permanently connected USB
> drive:
>
> ```
> .\scripts\install-autostart.ps1 -BackupTo \\server\share\designops -Lan
> ```
>
> The installer refuses a destination whose drive does not exist, so it cannot
> silently register a task that fails every night — that mistake has been made
> twice and is now impossible.

The script reads its connection details from `.env`, so it cannot drift onto a
different database from the one the app uses, and it fails loudly rather than
rotating a good backup out in favour of a truncated one.

### Restoring

A backup nobody has restored is a hypothesis. Test into a scratch database:

```
pg_restore -U designops -h 127.0.0.1 -d designops_restore_test --no-owner "D:\Backups\designops_<stamp>.dump"
```

**Restoring over the live database has an order that matters.** Get it wrong
and the restore silently does nothing:

1. **Stop the API task first.** If it starts before the restore, it recreates
   the schema and seeds permissions, roles and the admin user — and then every
   `CREATE TABLE` collides and every `COPY` fails on duplicate keys. Several
   hundred errors, an empty database, and an app that reports healthy.
2. `DROP DATABASE designops; CREATE DATABASE designops OWNER designops;`
3. `pg_restore` — expect **silence**. A wall of "already exists" means step 1
   was missed.
4. **Then** start the API task.
5. Compare row counts against the source before trusting it.

## Settings that matter

In `backend\.env` on the server:

| Setting | Why |
|---|---|
| `ENVIRONMENT=production` | turns on the startup check that refuses development defaults |
| `DATABASE_URL` | must be set explicitly, even pointing at this machine |
| `SECRET_KEY`, `JWT_SECRET` | anything starting `dev-only` is refused |
| `JWT_SECRET` specifically | **must not be regenerated** — changing it signs every user out at once |
| `SEED_DEFAULT_PASSWORD` | the published default is refused |
| `FRONTEND_URL`, `EXTRA_CORS_ORIGINS`, `CORS_ORIGIN_REGEX` | only consulted if a browser calls the API cross-origin; with the rewrite in place it does not |

## The network, and why this took a day

The wired `192.168.2.x` network **blocked Tailscale** until IT allowed it. The
symptom was thoroughly misleading and will be again if it recurs:

- TCP to `controlplane.tailscale.com:443` **connected**
- The TLS request then **timed out** — no error, no response
- Google, GitHub and Cloudflare all returned 200 from the same host at the same
  moment
- The identical request **succeeded** from the `192.168.0.x` wireless network
- Tailscale's own log said `fetch control key: context deadline exceeded`

Because the client could not reach its control plane, `tailscale up` hung with
no output, the GUI's sign-in button opened nothing, and an auth key looked
rejected. All of it read as a broken client. A clean reinstall changed nothing.

**If Tailscale ever stops working here, test the control plane before touching
the client:**

```
Test-NetConnection controlplane.tailscale.com -Port 443
Invoke-WebRequest "https://controlplane.tailscale.com/key?v=142" -TimeoutSec 20 -UseBasicParsing
```

TCP true and HTTPS timing out is the signature. It is a firewall policy, not
software.

### Verifying a Funnel is actually public

Fetching a `ts.net` address **from a machine on the tailnet proves nothing** —
it resolves internally and returns 200 while the tunnel is invisible to the
rest of the internet. Vercel is not on the tailnet, so it needs a public
record. That distinction caused a live outage.

The test that distinguishes them:

```
nslookup -type=A desktop-h993ees.tailc2b13d.ts.net 8.8.8.8
curl --resolve desktop-h993ees.tailc2b13d.ts.net:443:<that address> https://desktop-h993ees.tailc2b13d.ts.net/health
```

Public A records mean it is genuinely published. Tailscale can take several
minutes to publish them after Funnel is first enabled on a node. **Confirm this
before pointing Vercel at a new tunnel, not after.**

## The laptop

`SPINSIEGER`, `192.168.0.10`. A development machine. Nothing in this system
depends on it, and its `DesignOps API` task is stopped deliberately — it still
holds a pre-cutover database, and two live copies is the one failure with no
clean recovery.

> **It also runs a different system.** `D:\mrm-prod` serves on port **8001**,
> supervised by `D:\mrm-prod\run_backend.ps1`, and it is published on the
> laptop's own Tailscale Funnel at `u1-l-2rkv8f4.tailc2b13d.ts.net`.
>
> **Do not clear that funnel.** It reads as a leftover from this project and is
> not. Turning it off takes MRM off the internet; that has happened once.

## Rollback

The laptop still holds the database as it was at cutover. To fall back:

1. Start the laptop's `DesignOps API` task
2. Point the two `destination` lines in `frontend/vercel.json` at
   `u1-l-2rkv8f4.tailc2b13d.ts.net`, commit and push

Under two minutes. **This loses everything recorded on the server since
cutover**, so take a dump from the server first — the laptop's copy is frozen
at 31 August.

## Disaster recovery

Objective: back online within two hours, at most one day of data lost.

- Restore the most recent dump onto the laptop and start its API task
- Point `vercel.json` at the laptop's tunnel
- Replace the hardware, then rebuild the server from this document

That only holds while backups are current and restore-tested. Restore one into
a scratch database monthly and note the result — and get them off that single
disk.
