# GradScout Backend

## Local setup

```bash
pip install -r requirements.txt

# Requires a local Postgres. If you don't have one:
#   sudo apt install postgresql
#   sudo -u postgres createuser gradscout -P   # set password to match .env
#   sudo -u postgres createdb -O gradscout gradscout_dev

cp .env.example .env   # adjust DATABASE_URL if needed

psql -U gradscout -d gradscout_dev -f migrations/0001_initial_schema.sql
psql -U gradscout -d gradscout_dev -f migrations/0002_seed_sources.sql

pytest tests/ -v
```

## What's here so far (Phase 0 + Phase 1 + Phase 2)

- `app/dedup/` — the dedup engine: normalize → block → score → decide.
  Pure Python, no database dependency. Fully covered by `tests/test_dedup.py`.
- `app/models.py` — SQLAlchemy models mirroring `migrations/0001_initial_schema.sql`.
- `app/storage.py` — wires the dedup engine to real persistence. This is
  what the scheduler (Phase 5) will call for every scraped job.
- `app/scrapers/` — all 7 scrapers ported from the prototype (adzuna,
  reed, jooble, charityjob, acca, thirdsector, w4mpjobs), returning
  plain dicts instead of the old JobListing dataclass. Field renamed:
  `organisation` -> `company`, matching the dedup engine and schema.
- `app/pipeline.py` — orchestrates scrape -> dedup -> store across every
  enabled source, with per-source failure isolation. Run directly via
  `python -m app.pipeline` for a manual scrape.
- `migrations/` — numbered SQL files. Never edit an already-applied one
  once there's real data depending on it — write a new numbered
  migration instead (see 0003 for a worked example: it adds a source
  that was missing from 0002, rather than editing 0002 in place).

## Adding a new job source later

Because sources are configured as data (see `sources` table), adding an
8th source that fits an existing `scraper_type` (`static`, `rss`,
`adzuna`, `reed`, `jooble`) is just:

```sql
INSERT INTO sources (name, scraper_type, config) VALUES
('new-site-name', 'static', '{"url": "...", "parser": "parse_new_site"}');
```

No code deploy, no migration. A genuinely new *type* of source (a new
API with a different response shape) needs one new scraper class in
`app/scrapers/`, registered in `app/scrapers/registry.py`'s
`SCRAPER_TYPES` dict — that's the only case that does.

## Running the pipeline manually

```bash
export ADZUNA_APP_ID=... ADZUNA_APP_KEY=... REED_API_KEY=... JOOBLE_API_KEY=...
python -m app.pipeline
```

Scrapes every enabled source once, storing results through the dedup
engine, and prints a summary. This is what Phase 5's scheduler will
call on a timer — for now it's a manual, one-off run.

## Running the API (Phase 3)

```bash
uvicorn app.main:app --reload
```

Then visit **http://localhost:8000/docs** — this is FastAPI's
auto-generated interactive documentation, not something maintained by
hand. Every endpoint is listed, and you can send real requests to your
local database directly from that page.

**Auth is currently a stub** (see `app/auth.py`): every request needs an
`X-User-Id` header containing a real user's UUID. There's no
login/signup flow yet — create a test user via `POST /users` first (in
the docs page, click it, "Try it out", enter an email), copy the `id`
from the response, then click the padlock icon at the top of the docs
page and paste that UUID in to authorize all your other requests. Real
auth (Supabase-issued tokens) replaces this in Phase 4 — the point of
building it this way is that no endpoint or business logic needs to
change when that happens, only `app/auth.py` itself.

### Trying the full flow yourself

1. `POST /users` — create a test user, copy the returned `id`
2. Authorize using that ID (padlock icon, or the `X-User-Id` header manually)
3. `POST /criteria` — save a search (try `{"keywords": ["graduate"], "locations": ["london"]}`)
4. `GET /feed` — see which jobs currently in your database match

If your database has no jobs yet, run the Phase 2 pipeline first:
`python -m app.pipeline` (needs real API keys for Adzuna/Reed/Jooble to
actually find anything — see `.env.example`).

## Deploying (Phase 4)

Three accounts needed — Supabase (database), Railway (backend hosting),
and later Vercel (frontend, Phase 6, not needed yet). See the main
conversation/ROADMAP.md for the full step-by-step checklist. Quick
reference once you have accounts:

1. Create a Supabase project, open its **SQL Editor**, paste and run
   `migrations/0001_initial_schema.sql`, then `0002_seed_sources.sql`,
   then `0003_add_w4mpjobs_source.sql`, in that order.
2. Copy the Supabase connection string (Project Settings → Database →
   Connection string → URI, pooler mode) — this becomes `DATABASE_URL`.
3. Push this repo to GitHub, connect Railway to it, set the service's
   **root directory to `backend`**, add `DATABASE_URL` and the three API
   keys as Railway environment variables.
4. Railway builds automatically (`railway.json` in this folder tells it
   how) and gives you a public URL — visit `<that-url>/docs` to confirm
   it's alive.

## The scheduler (Phase 5)

Runs inside the same process as the API — no separate Railway service
needed. Starts automatically on app startup (see `app/main.py`'s
lifespan handler), runs once immediately, then every
`SCRAPE_INTERVAL_MINUTES` (default 20) thereafter.

Each cycle: scrape every enabled source → dedup → store (Phase 2's
`run_pipeline`) → for every user with active criteria, compute and save
any new matches (Phase 3's `compute_and_materialize_matches`, now
called by a timer as well as by the live `/feed` endpoint).

Failures are visible, not silent: per-source failures land in
`sources.last_scrape_error` (queryable in the database), and everything
prints to stdout, which Railway captures as logs — check **Deployments
→ [latest] → Logs** to watch cycles happen in real time.

To disable the scheduler (e.g. for local API poking without triggering
real scrapes): set `DISABLE_SCHEDULER=true`.

## Real authentication (Phase 6)

The `X-User-Id` stub is gone. Every authenticated endpoint now requires
a genuine Supabase-issued JWT:

```
Authorization: Bearer <token>
```

Verification uses Supabase's JWKS endpoint (the current recommended
approach — Supabase explicitly advises against the older shared-secret
method), fetched and cached in memory. There's no `POST /users`
endpoint anymore either: the first time a valid token from a given
Supabase user hits any endpoint, their app-side profile row is created
automatically, using the same UUID Supabase assigned them.

**Requires `SUPABASE_URL`** (e.g. `https://xxxxx.supabase.co`, found
under Project Settings → API → Project URL) as an environment variable
— add this to Railway before/alongside deploying this change, or every
authenticated request will fail with a 500.

**Low-risk timing**: the scheduler doesn't go through this auth layer
at all (it calls the pipeline and matching logic directly), so scraping
and dedup keep running uninterrupted regardless. Only `/criteria` and
`/feed` are affected — and since there's no frontend yet, nothing real
depends on the old stub today. This is about as safe a moment as this
change will ever get to make.
