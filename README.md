# Raabta / SafeReach — Family Safety Tracking System

A full-stack family safety system with a Next.js dashboard and FastAPI backend.
It automatically detects when a user reaches a configured destination (Home,
School, College, Office, University, or a custom safe place) and sends an
automatic WhatsApp notification to a chosen family member, e.g.:

> ✅ Ali has safely arrived at College at 8:20 AM.

The repository contains the `Raabtaa` backend and `raabta-frontend` dashboard.
The backend can still be tested independently through **Swagger UI** or
**Postman**.

---

## 1. Project Overview

The core pipeline:

```
Mobile app sends GPS location
        ↓
POST /api/v1/locations
        ↓
Deterministic geofence evaluation (Haversine distance, Python only)
        ↓
Geofence ENTER / EXIT event created (duplicates suppressed)
        ↓
Journey started (on EXIT) / completed (on ENTER)
        ↓
Safe Arrival Agent invoked (OpenAI Agents SDK) on ENTER
        ↓
Agent checks journey / dedup / eligible family member via tools
        ↓
WhatsApp Cloud API (or Mock mode) sends the message
        ↓
Result stored in PostgreSQL (notifications + whatsapp_messages)
```

**Important architecture rule:** the LLM/agent never computes GPS distance,
geofence membership, or timestamps. All of that is deterministic Python code
in `app/utils/geo.py` and `app/services/geofence_service.py`. The agent only
reasons about *what to do* once the geofence detection has already happened.

---

## 2. Architecture

```
app/
├── main.py                  FastAPI app, router wiring, exception handlers
├── core/                    config, JWT/password security, logging
├── database/                async engine/session, declarative base
├── models/                  SQLAlchemy ORM models (source of truth)
├── database/models/         re-export shim -> app.models (for the requested layout)
├── schemas/                 Pydantic request/response schemas
├── api/
│   ├── deps.py               shared FastAPI dependencies (get_current_user)
│   └── routes/                auth, users, family, places, locations,
│                               journeys, notifications, webhooks, test
├── services/                 geofence, journey, arrival, notification, whatsapp
├── agents/                   Safe Arrival Agent, tools, guardrails (OpenAI Agents SDK)
├── utils/                    geo.py (Haversine), time.py
└── tests/                    pytest test suite (mocks all external APIs)
```

Business rules enforced by the code (see spec §31), notably:
- One arrival event → at most one arrival notification (dedup by journey).
- Disabled / inactive family members are never notified.
- A safe place / destination must belong to the authenticated user.
- The agent never overrides deterministic geofence math.
- WhatsApp credentials live only in environment variables.
- Mock WhatsApp mode is available for local development.

---

## 3. Installation

### Requirements
- Python 3.11 or 3.12
- A Postgres database — this project defaults to [Neon](https://neon.tech) (free, serverless, no local install needed); local Postgres via Docker Compose is also supported
- A Google Gemini API key (for the Safe Arrival Agent — free tier available at https://aistudio.google.com/apikey)
- (Optional for real sends) A Meta WhatsApp Cloud API app

### Steps

```bash
git clone <this-repo>
cd Raabta
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set at minimum:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/Raabta
JWT_SECRET_KEY=some-long-random-string
GEMINI_API_KEY=AIza...
GEMINI_MODEL=gemini-2.5-flash
WHATSAPP_MOCK_MODE=true
TELEGRAM_MOCK_MODE=true
```

---

## 4. Environment Variables

| Variable | Description |
|---|---|
| `APP_NAME` | Display name of the app |
| `ENVIRONMENT` | `development` or `production`. Disables `/api/v1/test/*` in production. |
| `DATABASE_URL` | Async SQLAlchemy URL, e.g. `postgresql+asyncpg://user:pass@host:5432/db` |
| `JWT_SECRET_KEY` | Secret used to sign JWTs. **Change this in production.** |
| `JWT_ALGORITHM` | Defaults to `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT expiry, in minutes |
| `GEMINI_API_KEY` | Required for the Safe Arrival Agent. A Google Gemini API key (get one free at https://aistudio.google.com/apikey). |
| `GEMINI_MODEL` | Gemini model name used by the agent, e.g. `gemini-2.5-flash` |
| `GEMINI_BASE_URL` | Gemini's OpenAI-compatible endpoint. Defaults to `https://generativelanguage.googleapis.com/v1beta/openai/` — only change this if Google updates the URL. |
| `WHATSAPP_ACCESS_TOKEN` | Meta WhatsApp Cloud API access token |
| `WHATSAPP_PHONE_NUMBER_ID` | Meta phone number ID |
| `WHATSAPP_BUSINESS_ACCOUNT_ID` | Meta WABA ID |
| `WHATSAPP_API_VERSION` | e.g. `v20.0` |
| `WHATSAPP_VERIFY_TOKEN` | Token used to verify the Meta webhook handshake |
| `WHATSAPP_MOCK_MODE` | `true`/`false`. When `true`, no real WhatsApp calls are made. |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token used as the WhatsApp fallback |
| `TELEGRAM_MOCK_MODE` | `true`/`false`. When `true`, no real Telegram calls are made. |

Never commit your real `.env` file — only `.env.example` is checked in.

---

## 5. Database: Neon Postgres Setup & Migrations

This project is configured to use **[Neon](https://neon.tech)** — serverless,
managed Postgres — as the database. You don't need to install or run
Postgres yourself.

### Get a Neon connection string

1. Sign up at https://neon.tech (free tier is enough for this MVP) and
   create a project.
2. On your project's dashboard, open **Connection Details** and copy the
   connection string. It looks like:
   ```
   postgresql://neondb_owner:AbCdEf123@ep-cool-lab-123456.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
3. Convert it for SQLAlchemy's async driver by changing `postgresql://` to
   `postgresql+asyncpg://`, and paste it into `.env`:
   ```env
   DATABASE_URL=postgresql+asyncpg://neondb_owner:AbCdEf123@ep-cool-lab-123456.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```

That's it — no other config is needed. `app/database/session.py` automatically:
- Detects Neon hosts (or any `sslmode=require`/`verify-full` Postgres URL)
  and enables TLS on the asyncpg connection (asyncpg doesn't understand the
  `sslmode`/`channel_binding` query params libpq uses, so they're stripped
  and translated into an `ssl=` connect argument instead).
- Sets `pool_pre_ping=True` so the pool transparently reconnects if Neon's
  serverless compute suspends an idle connection.

If you'd rather use a **pooled** Neon connection (recommended for
serverless/many short-lived connections, e.g. multiple API instances), use
the `-pooler` host Neon shows in the dashboard instead of the direct host —
no other code changes are needed.

### Prefer local Postgres instead?

You can still run Postgres locally if you don't want to use Neon:
```bash
docker compose --profile local-db up -d db
```
then set in `.env`:
```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/Raabta
```

### Run migrations

```bash
# Already initialized in this repo under alembic/. To create a NEW migration
# after changing models:
alembic revision --autogenerate -m "describe your change"

# Apply all migrations (works against Neon or local Postgres the same way):
alembic upgrade head
```

The initial migration (`alembic/versions/..._initial_schema.py`) creates all
8 tables: `users`, `family_members`, `safe_places`, `location_events`,
`journeys`, `geofence_events`, `notifications`, `whatsapp_messages`.

---

## 6. Running the Server

```bash
uvicorn app.main:app --reload
```

Then open:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health check: http://localhost:8000/health

---

## 7. Running with Docker

By default, Docker Compose only runs the **API** container and connects to
your **Neon** database via `DATABASE_URL` in `.env`:

```bash
cp .env.example .env      # fill in your Neon DATABASE_URL and GEMINI_API_KEY
docker compose up --build
```

This runs `alembic upgrade head` automatically against Neon, then exposes
the API on `http://localhost:8000`.

If you opted for local Postgres instead of Neon (see §5), start both
services together:
```bash
docker compose --profile local-db up --build
```

---

## 8. Postman / Swagger Testing Flow

This mirrors the exact flow requested in the spec.

### Step 1 — Register
```
POST /api/v1/auth/register
{
  "full_name": "Ali Khan",
  "email": "ali@example.com",
  "phone_number": "+923001234567",
  "password": "SuperSecret123"
}
```

### Step 2 — Login
```
POST /api/v1/auth/login
{ "email": "ali@example.com", "password": "SuperSecret123" }
```
Copy the returned `access_token` and use it as a Bearer token for every
request below.

### Step 3 — Create a family member
```
POST /api/v1/family
{
  "name": "Father",
  "phone_number": "+923009998888",
  "relationship_type": "parent",
   "whatsapp_enabled": true,
   "telegram_enabled": true,
   "telegram_chat_id": "123456789"
}
```

WhatsApp is attempted first. If it fails, Raabta sends the same message to
the family member's Telegram chat when `telegram_enabled` is true and
`telegram_chat_id` is configured. Telegram chat IDs can be obtained by having
the recipient start a chat with your bot and reading the bot update payload.

### Step 4 — Create Home
```
POST /api/v1/places
{ "name": "Home", "place_type": "home", "latitude": 24.8607, "longitude": 67.0011, "radius_meters": 150 }
```

### Step 5 — Create College
```
POST /api/v1/places
{ "name": "College", "place_type": "college", "latitude": 24.9000, "longitude": 67.1000, "radius_meters": 200 }
```

### Step 6 — Send a location at Home
```
POST /api/v1/locations
{ "latitude": 24.8607, "longitude": 67.0011, "accuracy_meters": 10, "speed": 0,
  "recorded_at": "2026-09-11T08:00:00Z" }
```

### Step 7 — Send a location leaving Home / outside College
```
POST /api/v1/locations
{ "latitude": 24.9500, "longitude": 67.1500, "accuracy_meters": 10, "speed": 8,
  "recorded_at": "2026-09-11T08:10:00Z" }
```
This triggers a Home **EXIT**, which starts a Journey to College (MVP
heuristic: single other active safe place).

### Step 8 — Send a location inside College
```
POST /api/v1/locations
{ "latitude": 24.9001, "longitude": 67.1002, "accuracy_meters": 10, "speed": 1,
  "recorded_at": "2026-09-11T08:20:00Z" }
```

Expected result:
```
Geofence ENTER detected
      ↓
Arrival event created
      ↓
Safe Arrival Agent invoked
      ↓
Agent validates event, journey, dedup, family member
      ↓
WhatsApp notification created
      ↓
Mock/Meta WhatsApp send
      ↓
Database updated (notifications + whatsapp_messages)
```

Check the result with:
```
GET /api/v1/notifications
```

### Alternative: single-call simulation

Instead of steps 6–8, you can call the dev-only simulation endpoint directly
(disabled when `ENVIRONMENT=production`):

```
POST /api/v1/test/simulate-arrival
{
  "safe_place_id": "<college-place-id>",
  "latitude": 24.9001,
  "longitude": 67.1002
}
```

---

## 9. Gemini Setup (LLM backing the Safe Arrival Agent)

This project uses the **OpenAI Agents SDK** for the agent framework itself
(`Agent`, `Runner`, `function_tool`, guardrails) — that part didn't change.
What changed is *which LLM* answers the agent's requests: instead of an
OpenAI model, we point the SDK at **Google Gemini**, using Gemini's
OpenAI-compatible endpoint. No LangChain, LiteLLM, or extra framework is
needed — just the standard `openai` Python client pointed at a different
`base_url`, per Google's own docs: https://ai.google.dev/gemini-api/docs/openai

1. Get a free API key from https://aistudio.google.com/apikey.
2. Set in `.env`:
   ```env
   GEMINI_API_KEY=AIza...
   GEMINI_MODEL=gemini-2.5-flash
   GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
   ```
3. `app/agents/model_provider.py` builds an `AsyncOpenAI` client with that
   key and base URL, wraps it in `OpenAIChatCompletionsModel`, and passes
   that as the `model=` for the `Agent`. Everything else (tools, guardrails,
   structured output, function calling) works unchanged, because Gemini's
   compatibility layer implements the same Chat Completions + function
   calling shape the Agents SDK expects.
4. Built-in Agents SDK tracing is disabled (`set_tracing_disabled(True)`)
   since the default tracing exporter expects an OpenAI key — this only
   affects OpenAI's hosted trace viewer, not the agent's behavior. Your own
   `app/core/logging.py` logs already record each step of the agent run.
5. **Model choice matters for tool calling.** `gemini-2.5-flash` and
   `gemini-2.0-flash` are known to work reliably with function calling
   through the compatibility layer. Some newer preview models
   (e.g. `gemini-3-flash-preview` with thinking mode) have had reported
   issues returning malformed function-call responses through this
   endpoint — if you switch models and the agent starts erroring out on
   tool calls, try reverting to `gemini-2.5-flash` first.
6. If you ever want to switch back to OpenAI (or add it as a second option),
   you only need to change `app/agents/model_provider.py` — the rest of the
   agent code (`tools.py`, `guardrails.py`, `safe_arrival_agent.py`) is
   provider-agnostic.

---

## 10. Meta WhatsApp Cloud API Setup

1. Create a Meta App with the WhatsApp product enabled.
2. Get a temporary or permanent access token, the phone number ID, and the
   WhatsApp Business Account ID.
3. Set `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`,
   `WHATSAPP_BUSINESS_ACCOUNT_ID`, `WHATSAPP_API_VERSION` in `.env`.
4. Set a `WHATSAPP_VERIFY_TOKEN` of your choosing and configure the same
   value in the Meta App's webhook settings.
5. Point the Meta webhook at `https://<your-domain>/api/v1/webhooks/whatsapp`.
6. Set `WHATSAPP_MOCK_MODE=false` once you're ready to send real messages.
7. For production messaging outside a 24-hour session window, use an
   approved template via `send_template_message` (see
   `app/services/whatsapp_service.py`), e.g. template `safe_arrival_notification`
   with parameters `{{1}}=name`, `{{2}}=destination`, `{{3}}=time`.

---

## 11. Mock WhatsApp Testing

With `WHATSAPP_MOCK_MODE=true` (the default), no real Meta API calls are
made. Instead, the service prints:

```
MOCK WHATSAPP SENT
To: +923009998888

✅ Ali has safely arrived at College at 8:20 AM.
```

...and stores a successful mock message in `whatsapp_messages`. This lets
you test the entire pipeline before configuring a real Meta account.

---

## 12. Testing Commands

```bash
pytest                 # run the full suite
pytest -v               # verbose
pytest app/tests/test_geofence.py   # a single file
```

All external APIs (the Gemini-backed Agents SDK Runner, WhatsApp Cloud API HTTP calls)
are mocked in the automated tests — no real network calls or API keys are
required to run `pytest` (a dummy `GEMINI_API_KEY` is set automatically in
`app/tests/conftest.py`).

Test coverage includes:
- **Geofence**: inside/outside radius, boundary conditions, invalid
  coordinates, duplicate ENTER suppression.
- **Journey**: home exit → journey creation, arrival → journey completion.
- **Agent**: valid arrival, invalid arrival (guardrail trip), duplicate
  arrival detection, missing family member, WhatsApp-disabled family member.
- **WhatsApp**: mock send success, API failure handling, missing
  credentials, webhook status parsing.
- **Auth / Locations**: register/login/me, protected routes, full location
  ingestion pipeline (with the agent mocked out).

---

## 13. Example API Requests

**Register**
```http
POST /api/v1/auth/register
Content-Type: application/json

{"full_name":"Ali Khan","email":"ali@example.com","phone_number":"+923001234567","password":"SuperSecret123"}
```

**Create a safe place**
```http
POST /api/v1/places
Authorization: Bearer <token>
Content-Type: application/json

{"name":"College","place_type":"college","latitude":24.9000,"longitude":67.1000,"radius_meters":200}
```

**Send a location update**
```http
POST /api/v1/locations
Authorization: Bearer <token>
Content-Type: application/json

{"latitude":24.9001,"longitude":67.1002,"accuracy_meters":15,"speed":8.5,"recorded_at":"2026-09-11T08:20:00Z"}
```

---

## 14. Example Arrival Workflow (End-to-End)

1. Simulated GPS location is POSTed to `/api/v1/locations`.
2. `geofence_service` computes Haversine distance and detects an ENTER
   transition (deterministic, no LLM).
3. A `geofence_events` row is created; duplicate ENTER events while already
   inside are suppressed.
4. `arrival_service` marks any matching active journey as `arrived` and
   signals that the Safe Arrival Agent should run.
5. The **Safe Arrival Agent** (OpenAI Agents SDK, backed by Gemini) is invoked with a minimal
   context (user id, geofence event id, safe place id). It calls its tools to
   fetch the geofence event, destination, journey, dedup status, and an
   eligible family member — all real DB reads, never invented.
6. If everything checks out, the agent calls `record_notification` exactly
   once, which sends the WhatsApp message (via Mock or Meta Cloud API) and
   persists both the `notifications` and `whatsapp_messages` rows.
7. The mobile app (future work) or Postman can then read
   `GET /api/v1/notifications` to see the result.

Only after this full workflow works reliably in Mock mode should
`WHATSAPP_MOCK_MODE` be set to `false` to use the real Meta WhatsApp Cloud API.

---

## 15. Future Architecture Compatibility

The codebase is intentionally structured so the following can be added later
without breaking existing business logic:
- React Native background location reporting (already just POSTs to `/api/v1/locations`)
- Automatic multi-candidate destination prediction (journey_service is the extension point)
- Expected-arrival / delay / no-show detection (fields already exist on `journeys`)
- Emergency escalation, multiple simultaneous family members per notification
- Push notifications, a parent-facing dashboard
- Background scheduling (Celery/APScheduler/Redis) for delay detection
