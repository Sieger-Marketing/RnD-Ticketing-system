# Running this in production

The department's data lives in PostgreSQL on a machine Sieger owns, and nowhere
else. Everything below follows from that — including the one risk it leaves
open, under [Backups](#backups).

Migrated from a laptop to a dedicated server on 31 August 2026. That laptop is
now a development machine and nothing here depends on it.

Moved from Tailscale Funnel to Cloudflare Tunnel on 3 September 2026, onto the
company's own domain. Tailscale is no longer part of this system.

## The shape

```
  designer's browser
        |
        |  HTTPS
        v
  designops.siegerspintech.com ........  the address the team uses. Cloudflare
        |                                terminates TLS at its nearest edge —
        |                                Mumbai, from the office — and carries
        |                                the request down the tunnel.
        v
  cloudflared (Windows service) .......  on the server. Outbound-only: it dials
        |                                Cloudflare, so nothing is open inbound
        |  localhost:8000                and no port is forwarded.
        v
  FastAPI (uvicorn)  .................   the API, and the built app as well
        |                                192.168.2.253:8000
        |  localhost:5432
        v
  PostgreSQL 18  .....................   the department's data
```

**The old Vercel address still works.** `rn-d-ticketing-system.vercel.app`
serves the same bundle and rewrites `/api` and `/health` through to
`designops.siegerspintech.com`, so nobody's bookmark breaks. It is one hop
longer and measurably slower — roughly 0.5s against 0.2s — so prefer the direct
address and treat Vercel as a fallback that happens to still be wired up.

**The office has a way in that skips all of it.** The API binds `0.0.0.0`, so
anyone on the office network can reach `http://192.168.2.253:8000` directly. If
Cloudflare is having a bad day, the department is not blocked — worth knowing
before anyone panics.

## The machine

| | |
|---|---|
| Address | `192.168.2.253`, **static** — confirmed with IT, not a DHCP lease |
| Public address | `https://designops.siegerspintech.com` |
| Tunnel | Cloudflare Tunnel `designops`, in the `dawn-haze-5b83` Zero Trust account |
| Domain | `siegerspintech.com`, registered at GoDaddy, DNS at Cloudflare |
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

**`cloudflared` is a Windows service, not a scheduled task.** It was installed
by the connector command from the Cloudflare dashboard, starts at boot, and
needs nobody logged in:

```
Get-Service cloudflared
```

That is the entire point of the move. The tunnel it replaced depended on
`tailscale-ipn.exe`, a **GUI process** — when it stopped on 2 September the
office kept working over the LAN while every remote user was locked out, and
the portal looked healthy from inside the building the whole time.

## Deploying a change

```
laptop  →  git push  →  GitHub  →  Vercel (frontend, automatic)
                             └──→  server: git pull + restart the task
```

**Every change now needs the server.** The server serves the app the team
actually loads, so Vercel rebuilding on its own is no longer enough — that was
true under the old shape and is not any more.

```
cd D:\Design-Ops-System; git pull; cd frontend; npm run build
Stop-ScheduledTask -TaskName 'DesignOps API'; Start-Sleep 3; Start-ScheduledTask -TaskName 'DesignOps API'
```

Skip the build if nothing under `frontend/` changed, and the restart if nothing
under `backend/` did. When unsure, run both; they are cheap and safe.

**A backend pull does nothing until the restart.** uvicorn reads the code once,
at startup. This has already bitten: the fix for a bug that blocked submitting
any over-estimate task for review sat pulled-but-not-running on the server.

**Migrations run automatically** at task start, followed by the bootstrap that
applies new permissions, roles and settings. Both are idempotent.

After a frontend change, confirm both addresses serve the same bundle:

```
curl -s https://designops.siegerspintech.com/ | findstr index-
curl -s https://rn-d-ticketing-system.vercel.app/ | findstr index-
```

Different hashes mean the server was not rebuilt.

## Checking it

Three probes, in order of how much they tell you:

| Probe | Answers |
|---|---|
| `https://designops.siegerspintech.com/health` | the whole chain works |
| `https://rn-d-ticketing-system.vercel.app/health` | the legacy address still routes correctly |
| `http://192.168.2.253:8000/health/db` | the API is up and the database answers |

**Point an uptime monitor at the first one.** It is the only one that fails
when any part of the chain does — and the chain has already broken silently
once, in a way where the page still loaded and only the data was missing.
Nobody reported it.

`/api/auth/me` is a useful fourth probe: it should return **401**, not 200 and
not 502. A 401 proves the API is reachable *and* still enforcing auth.

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

## The network, and what it is capable of blocking

Tailscale is no longer in this system's path, so the fault below cannot recur
here. It is kept because the *behaviour of this network* is the lasting lesson:
**it can filter one destination while everything else works perfectly.**

The wired `192.168.2.x` network **blocked Tailscale** until IT allowed it, and
the symptom was thoroughly misleading:

- TCP to `controlplane.tailscale.com:443` **connected**
- The TLS request then **timed out** — no error, no response
- Google, GitHub and Cloudflare all returned 200 from the same host at the same
  moment
- The identical request **succeeded** from the `192.168.0.x` wireless network
- Tailscale's own log said `fetch control key: context deadline exceeded`

Because the client could not reach its control plane, `tailscale up` hung with
no output, the GUI's sign-in button opened nothing, and an auth key looked
rejected. All of it read as a broken client. A clean reinstall changed nothing.

**If `cloudflared` ever goes unhealthy while the machine is plainly online,
suspect the same thing before touching the service:**

```
Get-Service cloudflared
Test-NetConnection region1.v2.argotunnel.com -Port 7844
```

`cloudflared` dials **outbound** to Cloudflare on 7844 — QUIC over UDP, falling
back to TCP. Nothing inbound is needed, which is why no firewall rule exists
for it. A service that is running while the dashboard shows the tunnel down is
a filtering signature, not a software fault. Ask IT before reinstalling
anything.

### Verifying the public path, properly

The mistake that caused a live outage: an origin was tested **from a machine
that resolved it privately**. The `ts.net` address returned 200 in 69ms from
the tailnet while being invisible to the rest of the internet — and Vercel, not
being on the tailnet, got nothing.

Cloudflare removes that particular trap, because the hostname resolves to
public anycast addresses from everywhere. Confirm that is genuinely what
answered:

```
nslookup designops.siegerspintech.com 1.1.1.1
curl -sI https://designops.siegerspintech.com/health | findstr /i cf-ray
```

Cloudflare anycast IPs (`104.21.*`, `172.67.*`) plus a `cf-ray` header mean the
request really crossed the public internet. **Check before pointing anything at
a new origin, not after.**

## The laptop

`SPINSIEGER`, `192.168.0.10`. A development machine. Nothing in this system
depends on it, and its `DesignOps API` task is stopped deliberately — it still
holds a pre-cutover database, and two live copies is the one failure with no
clean recovery.

> **It also runs a different system.** `D:\mrm-prod` serves on port **8001**,
> supervised by `D:\mrm-prod\run_backend.ps1`, and it is published on the
> laptop's own Tailscale Funnel at `u1-l-2rkv8f4.tailc2b13d.ts.net`.
>
> **Do not clear that funnel, and do not uninstall Tailscale.** Design Ops no
> longer uses Tailscale anywhere, which makes "we don't need this any more" an
> easy and wrong conclusion. MRM still depends on it. Turning that funnel off
> takes MRM off the internet; that has happened once already.

## Rollback

Two fallbacks, in increasing order of pain.

**If the tunnel is broken but the server is fine**, the office can work at
`http://192.168.2.253:8000` immediately. Remote users stay blocked, so this
buys time rather than solving anything — but the department is never fully
stopped by a Cloudflare problem.

**If the server itself is gone**, the laptop still holds the database as it was
at cutover on 31 August:

1. Start the laptop's `DesignOps API` task
2. Repoint the tunnel — add a public hostname on the laptop, or point the three
   `destination` lines in `frontend/vercel.json` at an address that reaches it,
   then commit and push

Under two minutes. **This loses everything recorded on the server since
cutover**, so take a dump from the server first if it is reachable at all.

## Disaster recovery

Objective: back online within two hours, at most one day of data lost.

- Restore the most recent dump onto the laptop and start its API task
- Repoint the tunnel, or `vercel.json`, at whatever is serving
- Replace the hardware, then rebuild the server from this document — the
  Cloudflare tunnel is recreated by rerunning the connector install command
  from the Zero Trust dashboard, and the DNS record follows automatically

That only holds while backups are current and restore-tested. Restore one into
a scratch database monthly and note the result — and get them off that single
disk.
