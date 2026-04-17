# pillly-api

FastAPI backend for [Pillly](https://github.com/jinyoo1021/pillly) — 18 REST endpoints across 5 domains, QStash-scheduled push notifications, deployed on Render via GitHub Actions CI/CD.

This is one half of the Pillly project. For the full picture, see the [main README](https://github.com/jinyoo1021/pillly) and the [Flutter app](https://github.com/jinyoo1021/pillly-app).

---

## Table of Contents

- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Database Schema](#database-schema)
- [API Reference](#api-reference)
  - [Auth — /v1/auth](#auth--v1auth)
  - [Medications — /v1/medications](#medications--v1medications)
  - [Schedules — /v1/schedules](#schedules--v1schedules)
  - [Dose — /v1/dose](#dose--v1dose)
  - [Notifications — /v1/notifications](#notifications--v1notifications)
- [Notification Pipeline](#notification-pipeline)
- [Local Development](#local-development)
- [Environment Variables](#environment-variables)
- [CI/CD](#cicd)
- [Testing](#testing)
- [What I Learned](#what-i-learned)
- [Limitations and What I'd Do Differently](#limitations-and-what-id-do-differently)

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Framework | FastAPI + Python 3.11 | Async support, automatic validation via Pydantic, auto-generated OpenAPI schema |
| Database | Supabase (PostgreSQL + RLS) | Row-Level Security, built-in auth, free tier with 500MB |
| Auth | Supabase Auth | Handles JWT issuance, token refresh, and social OAuth — no custom implementation needed |
| Cache | Upstash Redis | Serverless-compatible Redis with a free tier |
| Notification scheduling | Upstash QStash | Cron-based signed webhook delivery with auto-retry |
| Push notifications | Firebase Admin SDK | Single SDK that covers both FCM (Android) and APNs (iOS) |
| Error monitoring | Sentry | Production error tracking and alerting |
| CI/CD | GitHub Actions → Docker → Render | Push to main → tests pass → auto-deploy |

---

## Project Structure

```
pillly-api/
├── app/
│   ├── main.py              # FastAPI init: CORS, Sentry, router registration
│   ├── core/
│   │   ├── config.py        # Pydantic BaseSettings — reads all secrets from .env
│   │   ├── security.py      # JWT auth dependency + QStash signature verification
│   │   ├── redis.py         # Upstash Redis connection pool
│   │   └── supabase.py      # Supabase client singleton
│   ├── routers/             # Thin HTTP layer — validates input and delegates to services
│   │   ├── auth.py
│   │   ├── medications.py
│   │   ├── schedules.py
│   │   ├── dose.py
│   │   └── notifications.py
│   ├── services/            # All business logic lives here
│   │   ├── auth_service.py
│   │   ├── medication_service.py
│   │   ├── schedule_service.py
│   │   ├── dose_service.py
│   │   ├── notification_service.py
│   │   └── qstash_service.py
│   └── schemas/             # Pydantic request/response models
│       ├── auth.py
│       ├── medication.py
│       ├── dose.py
│       └── notification.py
├── tests/                   # pytest test suite
├── supabase/migrations/     # SQL migration files
├── secrets/                 # Firebase + APNs key files (never committed)
├── Dockerfile
├── docker-compose.yml       # API + Redis for local development
├── requirements.txt
└── .github/workflows/       # CI/CD pipeline
```

**Architecture pattern:** routers → services → core clients

Routers are thin: they only parse HTTP input and call a service method. All business logic — DB queries, push notification dispatch, QStash registration — lives in the service layer. This made it straightforward to write tests that bypass HTTP entirely.

---

## Database Schema

6 tables. Relationships:

```
users ──< medications ──< schedules ──< dose_logs
                                   └──< notification_logs
users ──< device_tokens
```

| Table | Key Columns | Notes |
|---|---|---|
| `users` | `id` (UUID, FK → auth.users), `email`, `provider`, `name`, `timezone`, `language` | Mirrors Supabase `auth.users` — synced on every login |
| `medications` | `id`, `user_id`, `name`, `dosage`, `color_tag`, `is_active`, `deleted_at` | Soft delete via `deleted_at` |
| `schedules` | `id`, `medication_id`, `scheduled_time`, `cycle_type`, `cycle_value` (JSONB), `is_active`, `qstash_schedule_id` | `cycle_value` stores weekdays or interval config as JSON |
| `dose_logs` | `id`, `schedule_id`, `user_id`, `log_date`, `status`, `taken_at` | `UNIQUE(schedule_id, log_date)` enforces one log per schedule per day |
| `notification_logs` | `id`, `schedule_id`, `user_id`, `sent_at`, `status`, `snooze_count` | Records every push dispatch attempt |
| `device_tokens` | `id`, `user_id`, `token`, `platform` | `token UNIQUE` — upserted on every app launch |

**Index strategy** — prioritized around the two highest-frequency queries:

```sql
CREATE INDEX idx_medications_user  ON medications(user_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_dose_logs_user    ON dose_logs(user_id, log_date DESC);
CREATE INDEX idx_schedules_qstash  ON schedules(qstash_schedule_id) WHERE qstash_schedule_id IS NOT NULL;
```

**`dose_logs.status` values:**

| Value | Meaning | Set by |
|---|---|---|
| `pending` | Scheduled time not yet reached | Default |
| `done` | User tapped "Taken" | User action |
| `skipped` | User tapped "Skip" | User action |
| `missed` | No response by end of day | Planned batch job (not yet implemented) |

---

## API Reference

Base URL: `/v1`
Authentication: `Authorization: Bearer <supabase_access_token>` on all protected routes.

Swagger UI is available at `/docs` in development. Disabled in production.

### Auth — `/v1/auth`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/register` | — | Email/password sign-up. Creates user in Supabase Auth and syncs to `public.users`. Returns `access_token` + `refresh_token`. |
| POST | `/login` | — | Email/password login. Returns tokens + user profile. |
| POST | `/social` | — | Google or Apple OAuth. Accepts `id_token` from native SDK, exchanges with Supabase. Returns `is_new_user` flag for onboarding flow. |
| POST | `/refresh` | — | Reissues `access_token` from `refresh_token`. |
| DELETE | `/logout` | Bearer | Invalidates the current session. Returns `200` with a message body (not `204` — see [What I Learned](#what-i-learned)). |

### Medications — `/v1/medications`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `` | Bearer | Returns all active medications for the user, with nested `schedules[]`. |
| POST | `` | Bearer | Creates a medication + its schedules in one transaction, then registers QStash cron jobs. |
| PATCH | `/{id}` | Bearer | Updates medication fields and/or schedules. Schedule changes soft-delete existing records and insert new ones. Re-syncs QStash. |
| PATCH | `/{id}/toggle` | Bearer | Toggles `is_active`. On activate: registers QStash crons. On deactivate: removes them. |
| DELETE | `/{id}` | Bearer | Soft-deletes the medication (`deleted_at` timestamp) and removes all QStash schedules. |

### Schedules — `/v1/schedules`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/today` | Bearer | Returns today's medication schedule with dose status. Filters by `cycle_type` — weekly schedules only appear on matching weekdays; interval schedules only appear on valid days. |

**Response example:**
```json
{
  "date": "2026-04-17",
  "total": 3,
  "done": 1,
  "rate": 33,
  "items": [
    {
      "schedule_id": "uuid",
      "medication_name": "Metformin 500mg",
      "scheduled_time": "08:00",
      "color_tag": "#1D9E75",
      "status": "done",
      "taken_at": "2026-04-17T04:12:00Z"
    }
  ]
}
```

### Dose — `/v1/dose`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/confirm` | Bearer | Marks a schedule as `done` for today. Upserts — safe to call if a log already exists. |
| POST | `/skip` | Bearer | Marks a schedule as `skipped` for today. Upserts. |
| DELETE | `/undo` | Bearer | Deletes today's dose log for a schedule, resetting it to `pending`. |
| GET | `/logs?from=YYYY-MM-DD&to=YYYY-MM-DD` | Bearer | Returns daily summaries for the calendar view. Each day includes `total`, `done`, `skipped`, `missed`, `rate`, and a color `grade` (green / yellow / red). |
| GET | `/logs/day?date=YYYY-MM-DD` | Bearer | Returns per-medication logs for a specific date. Used for the date-detail view when tapping a day in the calendar. |
| GET | `/stats?period=week\|month` | Bearer | Returns overall adherence rate + per-medication breakdown for the last 7 or 30 days. |

### Notifications — `/v1/notifications`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/token` | Bearer | Registers or updates the device's FCM/APNs token. Upserted on conflict to handle token rotation. |
| POST | `/notify` | QStash signature | **Internal webhook** — called by QStash at scheduled dose times. Verifies JWT signature, runs interval-day guard, then dispatches push via FCM. |
| GET | `/log` | Bearer | Returns the last 50 notification dispatch records for the user. |

---

## Notification Pipeline

This is the core feature of the backend. When a medication is saved, the API registers a cron job in QStash. At the scheduled time, QStash fires a signed webhook back to the server, which dispatches a push notification to the device.

```
Medication saved
  → MedicationService.create() / update() / toggle()
  → QStashService.sync_schedules()
      → Delete old QStash schedules (by qstash_schedule_id stored in DB)
      → POST /v2/schedules/{callback_url}
          Headers: Upstash-Cron: "8 8 * * *", Upstash-Retries: 3
      → Store returned scheduleId → schedules.qstash_schedule_id

At scheduled time (UTC)
  → QStash fires POST /v1/notifications/notify
  → verify_qstash_signature() — JWT verification via official qstash SDK
  → Interval guard: if cycle_type="interval", check (today - start_date).days % N == 0
  → Medication inactive guard: skip if is_active=False
  → No device token: log "skipped_no_token", return early
  → FCM data-only message → device
  → Log result to notification_logs

Device receives data-only FCM
  → Flutter intercepts payload (no system notification rendered)
  → flutter_local_notifications renders custom notification with Taken ✓ / Skip ✗ buttons
  → User taps button
  → POST /v1/dose/confirm or /v1/dose/skip
  → dose_logs updated, Riverpod providers invalidated, UI refreshes
```

**Why data-only FCM?**
When an FCM payload includes a `notification` field, Android auto-renders a system notification that cannot have custom action buttons. Sending a data-only message (no `notification` field) lets Flutter intercept the payload and render a fully custom local notification with action buttons — keeping the entire flow inside the app.

**Cron expression builder (`_build_cron`)**

Converts `scheduled_time` (stored as KST) to a UTC cron expression:

```python
hour_utc = (hour_kst - 9) % 24  # KST → UTC

# daily:    "8 8 * * *"
# weekly:   "8 8 * * 1,3,5"  (ISO weekday → cron day-of-week conversion)
# interval: "8 8 * * *"  (daily fire, server-side day filtering in send_push)
```

For `weekly`, if `hour_kst < 9`, the UTC date shifts to the previous day, so the cron day-of-week also shifts: `cron_day = (cron_day - 1) % 7`.

QStash does not natively support "every N days" scheduling. For `interval` cycle types, the cron fires daily and `send_push()` checks whether today is actually a valid day before dispatching.

---

## Local Development

### Prerequisites

- Python 3.11
- Docker Desktop (for `docker-compose` and Supabase CLI)
- Supabase CLI (`brew install supabase/tap/supabase`)
- Firebase service account JSON + APNs `.p8` key in `secrets/`

### Option A — Direct

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Copy and fill in all required environment variables
cp .env.example .env

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger UI: http://localhost:8000/docs (only available when `APP_ENV=development`)

### Option B — Docker Compose

```bash
docker-compose up
```

Starts the API server + a local Redis instance. `.env` is loaded automatically from the project root.

### Startup order for full local integration

```
1. docker compose up          # start API + Redis
2. supabase start             # start local Supabase (PostgreSQL + Auth)
3. supabase db reset          # apply migrations — creates all 6 tables
4. flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000/v1 ...
```

Note: Inside the Android emulator, `localhost` on the Mac is accessed via `10.0.2.2`, not `127.0.0.1`.

---

## Environment Variables

All variables are defined in `app/core/config.py` as a Pydantic `BaseSettings` class. Missing required variables will raise a validation error on startup.

| Variable | Required | Default | Description |
|---|---|---|---|
| `APP_ENV` | — | `development` | `development` enables Swagger UI and open CORS |
| `API_URL` | ✅ | — | Public URL of this server — used as QStash webhook callback. Must be reachable by QStash (not localhost). Use ngrok for local testing. |
| `SECRET_KEY` | ✅ | — | JWT signing key — 32+ random characters |
| `SUPABASE_URL` | ✅ | — | Supabase project URL |
| `SUPABASE_ANON_KEY` | ✅ | — | Supabase anon key (public) |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | — | Supabase service role key (admin — never expose to client) |
| `UPSTASH_REDIS_URL` | — | `redis://localhost:6379` | Upstash Redis URL |
| `UPSTASH_REDIS_TOKEN` | — | `local` | Upstash Redis auth token |
| `QSTASH_TOKEN` | ✅ | — | QStash API token for registering schedules |
| `QSTASH_CURRENT_SIGNING_KEY` | ✅ | — | Used to verify incoming QStash webhook signatures |
| `QSTASH_NEXT_SIGNING_KEY` | ✅ | — | Rotated key — kept to handle in-flight webhooks during key rotation |
| `FIREBASE_PROJECT_ID` | ✅ | `pillly-app` | Firebase project ID |
| `FIREBASE_CREDENTIALS_PATH` | ✅ | `./secrets/firebase-adminsdk.json` | Path to Firebase service account JSON |
| `APNS_KEY_ID` | ✅ | — | APNs key ID from Apple Developer portal |
| `APNS_TEAM_ID` | ✅ | — | Apple Developer team ID |
| `APNS_PRIVATE_KEY_PATH` | ✅ | `./secrets/apns-key.p8` | Path to APNs `.p8` private key |
| `APNS_BUNDLE_ID` | ✅ | `com.pillly.app` | iOS app bundle identifier |
| `SENTRY_DSN` | — | `""` | Sentry DSN — Sentry is disabled when empty |

**What not to commit:**
```
.env                          # real secrets
secrets/                      # Firebase JSON + APNs .p8 key
```

Both are in `.gitignore`. The `secrets/` directory also has its own `.gitignore` as a second layer of protection.

---

## CI/CD

```
Push to main branch
  → GitHub Actions
  → Setup Python 3.11
  → pip install -r requirements.txt
  → pytest tests/ -v --tb=short
  → On pass: POST to Render deploy hook
  → Render pulls latest image and redeploys
```

14 secrets are registered in GitHub Actions (all environment variables above). The deploy hook URL is `RENDER_DEPLOY_HOOK_URL`.

---

## Testing

```bash
pytest tests/ -v --tb=short          # run all tests
pytest tests/test_auth.py -v         # single file
```

| File | Coverage |
|---|---|
| `test_health.py` | `/health` endpoint |
| `test_auth.py` | Register, login, token refresh, logout |
| `test_medications.py` | Full CRUD + toggle, ownership verification |
| `test_schedules.py` | Today's schedule filtering (daily / weekly / interval) |
| `test_dose.py` | Confirm, skip, undo, logs, stats |
| `test_notifications.py` | Device token registration, webhook receiver |

---

## What I Learned

### 1. Infrastructure cost reality — $200/month to $0

The initial architecture was AWS ECS + RDS + ElastiCache + ALB, estimated at **$196–250/month** for a project with fewer than 10 daily users.

| Service | Monthly Cost |
|---|---|
| ECS Fargate (×2) | $55 |
| RDS PostgreSQL | $50 |
| ElastiCache Redis | $35 |
| ALB | $25 |
| CloudFront + WAF | $30 |
| **Total** | **$196–250** |

I redesigned around Render + Supabase + Upstash at **$0/month** while keeping the codebase identical. The migration path is planned and explicit — not "maybe someday AWS":

| Stage | DAU | Stack | Cost |
|---|---|---|---|
| Now | < 10 | Render + Supabase + Upstash | $0 |
| Growth | 100–3,000 | Fly.io + Supabase Pro | ~$20/mo |
| Scale | 3,000+ | AWS ECS + RDS + ElastiCache | ~$150/mo |

**Takeaway:** For a solo project at zero users, infrastructure complexity and cost should scale with actual demand, not imagined future scale.

---

### 2. Supabase `auth.users` vs `public.users`

My first migration had `medications.user_id` referencing `auth.users.id` directly:

```sql
user_id UUID REFERENCES auth.users(id)  -- this breaks
```

Every medication insert failed:
```
insert or update on table "medications" violates foreign key constraint
Key (user_id)=(uuid) is not present in table "users"
```

Supabase manages `auth.users` in a separate schema and does not expose it to `public` foreign keys reliably.

**Fix:** Created a `public.users` table that mirrors `auth.users`, synced manually on every login via `_sync_user()`:

```python
def _sync_user(self, user) -> None:
    existing = supabase.table("users").select("id").eq("id", user.id).execute()
    if not existing.data:
        supabase.table("users").insert({
            "id": user.id,
            "email": user.email,
            "name": user.user_metadata.get("name", ""),
            "provider": user.app_metadata.get("provider", "email"),
        }).execute()
```

**Side benefit:** A `public.users` table is far easier to extend later — adding caregiver links, preferences, or subscription status is a straightforward column addition.

---

### 3. supabase-py v2 API changes

`supabase.auth.refresh_session()` silently fails in supabase-py v2. There's no error — the call just returns nothing. After reading the source, I found the correct method:

```python
# v2 — doesn't work
response = supabase.auth.refresh_session()

# v2 — works
response = supabase.auth._refresh_access_token(refresh_token)
```

**Takeaway:** When an SDK method returns nothing silently, read the source code before spending time on environment/config issues.

---

### 4. FastAPI route ordering matters

`PATCH /{medication_id}/toggle` defined below `PATCH /{medication_id}` means FastAPI matches the generic route first:

```python
# Wrong order — /toggle never matched
@router.patch("/{medication_id}")
@router.patch("/{medication_id}/toggle")

# Correct — specific path above generic
@router.patch("/{medication_id}/toggle")
@router.patch("/{medication_id}")
```

FastAPI resolves routes top-down. More specific paths must come first.

---

### 5. Data-only FCM for interactive notifications

First implementation included a `notification` field in the FCM payload:

```python
# First attempt — action buttons don't work
message = messaging.Message(
    notification=messaging.Notification(title="...", body="..."),
    data={"schedule_id": schedule_id},
)
```

Android auto-renders a system notification when `notification` is present. That system notification cannot have custom action buttons.

**Fix:** Remove the `notification` field entirely. Flutter intercepts the raw data payload and renders a fully custom local notification using `flutter_local_notifications`:

```python
# Data-only — Flutter handles rendering
message = messaging.Message(
    data={
        'schedule_id': schedule_id,
        'medication_name': medication_name,
        'type': 'medication_reminder',
    },
    android=messaging.AndroidConfig(priority='high'),
    token=token,
)
```

---

### 6. QStash uses JWT signatures, not HMAC — and three bugs in the original implementation

The first webhook verification returned 401 on every QStash call. I spent time checking keys and headers before finding that the verification code itself had three bugs:

```python
# Bug 1: loop exits after first non-dummy key — second key never checked
for key in [current_key, next_key]:
    if key == "local-dummy":
        return True
    # loop exits here — second key never reached

# Bug 2: hmac.new does not exist
hmac.new(key.encode(), body, hashlib.sha256)  # AttributeError

# Bug 3: QStash signs with JWT, not HMAC — wrong algorithm entirely
```

**Fix:** Replaced with the official `qstash` Python SDK:

```python
from qstash import Receiver

receiver = Receiver(
    current_signing_key=settings.QSTASH_CURRENT_SIGNING_KEY,
    next_signing_key=settings.QSTASH_NEXT_SIGNING_KEY,
)
receiver.verify(body=body.decode("utf-8"), signature=signature)
```

**Takeaway:** When integrating a third-party webhook, check whether it uses HMAC or JWT before writing verification code. Both are common and the correct approach is not obvious from the header name alone.

---

### 7. KST → UTC timezone conversion in cron expressions

QStash runs cron jobs in UTC. Medication times are stored as KST. Without conversion:

```
User sets 17:00 KST → stored as "17:00" → cron: "0 17 * * *" (UTC)
→ notification fires at 17:00 UTC = 02:00 KST the next morning
```

**Fix:**

```python
hour_utc = (hour_kst - 9) % 24
```

For weekly schedules, if `hour_kst < 9`, the UTC time falls on the previous calendar day, so the cron day-of-week also needs to shift:

```python
if hour_kst < 9:
    cron_day = (cron_day - 1) % 7
```

**Verification:**

| Scheduled (KST) | Cron (UTC) | Result |
|---|---|---|
| 17:08 | `8 8 * * *` | ✅ Correct |
| 02:00 | `0 17 * * *` (prev day for weekly) | ✅ Correct |
| 09:00 | `0 0 * * *` | ✅ Correct |

---

### 8. Soft delete and hard delete — when to use which

Dose logs reference `schedule_id` with a foreign key. Deleting a schedule record breaks the history. When a medication schedule changes, the service:

1. Checks if any `dose_logs` reference the existing schedules
2. If yes → `is_active = False` (soft delete — history preserved)
3. If no → `DELETE` (hard delete — no orphaned records)

```python
for s in current_schedules:
    logs = supabase.table("dose_logs").select("id").eq("schedule_id", s["id"]).execute()
    if logs.data:
        supabase.table("schedules").update({"is_active": False}).eq("id", s["id"]).execute()
    else:
        supabase.table("schedules").delete().eq("id", s["id"]).execute()
```

This became important when cleaning up test data — 49 orphaned inactive schedules were safely hard-deleted.

---

### 9. Upsert instead of duplicate-checking on dose logs

The first implementation of `confirm` and `skip` raised a `400 ALREADY_LOGGED` if a log existed for that day:

```python
if existing.data:
    raise HTTPException(status_code=400, detail="ALREADY_LOGGED")
```

This broke the "Undo" flow — after undoing a dose, re-confirming it would hit the error because the original log record still existed in some edge cases. Replaced with upsert logic:

```python
if existing.data:
    supabase.table("dose_logs").update({"status": "done", "taken_at": now}).eq("id", existing.data[0]["id"]).execute()
else:
    supabase.table("dose_logs").insert({...}).execute()
```

---

### 10. `204 No Content` silently drops the response body

The logout endpoint originally returned `status_code=204`. This is semantically correct for "no content," but the Flutter client had no way to confirm success — `response.body` is empty by spec.

Changed to `status_code=200` with an explicit message:

```python
return {"message": "Successfully logged out"}
```

**Takeaway:** `204` is correct for fire-and-forget operations where the client doesn't need confirmation. For a logout that the app depends on to clear local state, a `200` with a body is more useful.

---

## Limitations and What I'd Do Differently

### N+1 queries in notification log retrieval

`NotificationService.get_logs()` fetches notification logs, then queries `schedules` and `medications` individually for each log entry to get the medication name:

```python
for log in logs.data:
    schedule = supabase.table("schedules").select("medication_id").eq("id", log["schedule_id"]).execute()
    medication = supabase.table("medications").select("name").eq("id", ...).execute()
```

For 50 log entries, this is 101 queries. I landed here because Supabase's Python client has limited support for 3-level nested joins, and `.in_()` queries were silently returning empty results in some configurations. The right fix is a raw SQL join via `supabase.rpc()` or direct `asyncpg`.

---

### Supabase Python SDK is synchronous inside async routes

The Supabase Python SDK makes synchronous HTTP requests. Every `supabase.table(...).execute()` call in an `async` route handler blocks the event loop. For a low-traffic app this is acceptable, but it means FastAPI's async advantage is largely negated.

The fix would be using `asyncpg` directly for database operations, or waiting for an official async Supabase Python client.

---

### Inconsistent error handling and logging

Some service methods use `print(f"ERROR in ...: {e}")` + re-raise. Others catch broad `Exception` and wrap in `HTTPException`. There's no structured logging — errors in production show up in Sentry but aren't searchable by request ID or user ID.

I'd introduce Python's `logging` module with a consistent format: `logger.error("...", extra={"user_id": ..., "endpoint": ...})`.

---

### `_build_cron()` has a latent bug in the weekly path

The weekly cycle conversion has a code path where `cron_day` is referenced before it's assigned:

```python
for d in weekdays:
    cron_days.append(d % 7)
    if hour_kst < 9:
        cron_day = (cron_day - 1) % 7  # ← cron_day not yet defined
    cron_days.append(cron_day)          # ← appends again, duplicating entries
```

This is a logic error from the first pass at timezone-aware weekday conversion. It hasn't caused visible issues because weekly schedules with KST times before 09:00 aren't common in testing, but it would produce incorrect cron expressions in production.

---

### iOS APNs is not directly implemented

`_send_apns()` currently routes through Firebase Admin SDK, which internally handles APNs delivery. This works but means iOS notifications go through an extra hop and lose direct control over APNs-specific features (like notification grouping or custom interruption levels). Direct APNs implementation using the `.p8` key was planned but not completed.

---

### No `.env.example` file

There's no template showing which environment variables are required. A new developer setting up locally has to read `config.py` and cross-reference with the `docker-compose.yml` to figure out what to populate. Adding a committed `.env.example` with placeholder values would eliminate this friction entirely.
