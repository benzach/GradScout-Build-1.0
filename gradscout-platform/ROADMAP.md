# GradScout Build Roadmap

**Status: Phase 5 complete (background scheduler — the system now watches constantly). This document picks up from Phase 6.**

## How we'll work together

Every phase follows the same pattern, because it's the pattern that already worked well on the scraper prototype:

1. **I build** a piece, and explain the *why* behind the design decisions, not just hand you code.
2. **You review or deploy** it — sometimes that's just reading and asking questions, sometimes it's creating a cloud account or running a command.
3. **We test it together against something real** — not just "does it run" but "does it do the right thing," the same way we stress-tested the dedup engine against cases designed to catch false positives.
4. **We only move to the next phase once the current one actually works**, not once the code merely exists.

You'll notice phases don't wait until "everything is built" before you get involved — you're brought in early and often, on purpose, because that's how you actually end up understanding the system instead of just owning a black box someone else built for you.

---

## Overview

| Phase | What it is | Status |
|---|---|---|
| 0 | Dedup engine | ✅ Done |
| 1 | Data model + local database | ✅ Done |
| 2 | Port the 6 scrapers | ✅ Done (7 — w4mpjobs added back in) |
| 3 | Backend API core (FastAPI) | ✅ Done |
| 4 | Real infrastructure (Supabase, Railway, Vercel accounts) | ✅ Done |
| 5 | Scheduler + backend deployment | ✅ Done |
| 6 | Frontend PWA | Next |
| 3 | Backend API core (FastAPI) | |
| 4 | Real infrastructure (Supabase, Railway, Vercel accounts) | |
| 5 | Scheduler + backend deployment | |
| 6 | Frontend PWA | |
| 7 | Push notifications | |
| 8 | End-to-end testing | |
| 9 | Go-live | |
| 10 | Monetization, AI ranking, Tier 2 partnerships | Later |

---

## Phase 1 — Data model + local database

**Why this is next**: the dedup engine currently operates on plain Python dictionaries in memory. Before we can build an API or a scheduler around it, we need real, persistent storage with a schema that reflects the decisions the dedup engine makes — specifically, the fact that one canonical job can have multiple source postings linked to it.

**What you'll understand by the end of this phase**: why we separate `jobs` (canonical, deduplicated) from `job_sources` (every original posting) — this is the schema-level expression of everything we just built in Phase 0.

| | |
|---|---|
| **I do** | Design the Postgres schema (`users`, `search_criteria`, `jobs`, `job_sources`, `user_job_matches`), write it as SQL migration files, stand up a local Postgres instance in my sandbox to test against, wire the dedup engine to actually read/write from it instead of in-memory lists, write tests proving inserts/merges/flags all persist correctly. |
| **You do** | Nothing required yet — but I'll walk you through the schema and explain each table's purpose before moving on, and you should push back if anything doesn't make sense. This is the foundation everything else sits on, worth understanding solidly. |
| **Checkpoint** | I show you the schema diagram and a worked example: a job scraped from Adzuna and the same job scraped from Reed, and how they end up as one row in `jobs` with two rows in `job_sources`. |

---

## Phase 2 — Port the 6 scrapers

**Why this matters**: your existing scrapers (Adzuna, Reed, Jooble, CharityJob, ACCA, Third Sector) already work — this phase is about restructuring them to fit the new backend, not rewriting their logic. Low risk, mostly mechanical.

| | |
|---|---|
| **I do** | Move all 6 scrapers into the new backend structure, adapt them to write into the Phase 1 database (via the dedup engine) instead of SQLite, keep the existing test coverage, add a couple of new tests confirming a scraped job actually flows through normalize → block → score → store correctly end-to-end. |
| **You do** | Nothing required — your Adzuna/Reed/Jooble API keys from the old project carry over unchanged, no new registration needed. |
| **Checkpoint** | I run all 6 scrapers against real live data in my sandbox (where network access allows) and show you actual jobs flowing through the full pipeline into the database, with real dedup decisions on real data — not synthetic test cases this time. |

---

## Phase 3 — Backend API core (FastAPI)

**Why this matters**: this is what your future frontend will actually talk to. It's the first genuinely new piece of business logic — turning "a database full of jobs" into "an API a user's phone can query."

**What you'll understand by the end**: how a user's saved criteria (location, salary, keywords) actually gets turned into "show me only jobs I care about" — this is where your product's core value proposition lives in code.

| | |
|---|---|
| **I do** | Build endpoints for: creating/editing search criteria, fetching a user's matched job feed (filtered, paginated), marking a job as seen/applied/dismissed. Write tests for each endpoint. Document the API (FastAPI auto-generates interactive docs, which you'll be able to click through yourself). |
| **You do** | Review the API docs I generate and tell me if anything about how criteria work doesn't match what you pictured (e.g., can a user save multiple criteria sets? Should "any of these keywords" or "all of these keywords" be the default?). This is a product decision, not a technical one — I need your call. |
| **Checkpoint** | You use the interactive API docs (a web page FastAPI builds automatically) to manually create a test user's criteria and pull back a real filtered job feed, entirely through your browser, no frontend needed yet. |

---

## Phase 4 — Real infrastructure

**Why now, not earlier**: everything so far has run in my sandbox, which is disposable and not reachable from your phone. This phase makes it real and persistent. I'm deliberately placing this *after* the API is built and proven, not before — so that when you set up hosting, you're deploying something already known to work, rather than debugging infrastructure and business logic at the same time.

| | |
|---|---|
| **I do** | Give you exact, step-by-step instructions for each signup — what to click, what to name things, what settings matter. Prepare deployment config files (so your Railway/Render deploy is closer to one-click than a manual setup). |
| **You do** | Create the actual accounts (I can't sign up on your behalf): **Supabase** (database + auth, free tier), **Railway or Render** (backend hosting, free/hobby tier), **Vercel or Netlify** (frontend hosting, free tier — used in Phase 6). Add the API keys/secrets I tell you to add. |
| **Checkpoint** | Your backend, running on real infrastructure, responds to a request from your own browser — not my sandbox. This is the first moment the product exists outside a development environment. |

---

## Phase 5 — Scheduler + backend deployment

**Why this matters**: this is what turns "an API that answers when asked" into "a system that watches constantly," which was your original core requirement.

**What you'll understand by the end**: the actual mechanics of "constantly search the internet" — it's not magic, it's a loop that wakes up every 15-30 minutes, asks each of your 6 sources for what's new, runs it through dedup, and checks it against every user's saved criteria.

| | |
|---|---|
| **I do** | Build the scheduler (runs inside your deployed backend), wire it to call all 6 scrapers on an interval, push results through the Phase 1-2 pipeline, and generate match records for Phase 3's API to serve. Add monitoring/logging so failures are visible, not silent. |
| **You do** | Watch it run for real, on a real schedule, against real data — and tell me if the timing feels right (is 15 minutes too aggressive? Too slow?). |
| **Checkpoint** | You watch a genuinely new graduate job appear on one of your 6 sources, and see it show up in your API's job feed within one scheduler cycle, unprompted — the first real end-to-end proof the product works as intended. |

---

## Phase 6 — Frontend PWA

**Why a PWA, reminder**: installable on a phone home screen, push notifications work, no App Store review cycle while we're still validating — all discussed earlier. This is the biggest single piece of new code, so it's worth taking in stages rather than one giant drop.

| | |
|---|---|
| **I do** | Build in this order: (a) onboarding — criteria input form, (b) job feed — the main scrollable list with filters, (c) job detail view with the original source link, (d) account/settings page. Each piece will be shown to you as a working screen before I move to the next. |
| **You do** | This is the most "product taste" heavy phase — I need your input on layout, what information matters most on a job card, how filters should feel to use. I'd suggest you literally use it on your own phone as each screen is built, the way we debugged the Streamlit dashboard together. |
| **Checkpoint** | You install the PWA on your own phone from a real URL and it looks and feels like an app, not a website. |

---

## Phase 7 — Push notifications

**Why this is separate from Phase 6**: notification permissions and delivery are genuinely fiddly across iOS/Android/browsers, and deserve focused testing rather than being bundled into general frontend work.

| | |
|---|---|
| **I do** | Wire up the Web Push subscription flow, connect it to the Phase 5 scheduler so a new match triggers a real push notification. |
| **You do** | Test this on your actual phone — grant notification permission, then wait for (or trigger) a real match and confirm the notification actually arrives and opens the right job. This one genuinely can't be verified without your device. |
| **Checkpoint** | A real graduate job matching your saved criteria appears, and your phone buzzes with a notification for it, unprompted, while the app isn't open. |

---

## Phase 8 — End-to-end testing

**Why this phase exists as its own thing**: individual pieces working doesn't guarantee the whole system holds together under real, messy conditions (a scraper failing, a duplicate slipping through, a slow API response).

| | |
|---|---|
| **I do** | Write integration tests covering realistic failure scenarios (one source down, malformed data, high job volume) — the same defensive instinct as the dedup false-positive tests, applied to the whole system. |
| **You do** | Use the product like a real user would for a few days — create real criteria for yourself, let it run, tell me what feels broken, slow, or wrong. |
| **Checkpoint** | A week of genuinely uneventful daily use — no crashes, no missed notifications you can verify were real misses, no duplicate spam. |

---

## Phase 9 — Go-live

| | |
|---|---|
| **I do** | Final production configuration, help you write a basic privacy policy/terms of service page (I'm not a lawyer — flagging that a real legal review is worth it before genuinely public launch, especially given UK GDPR obligations once you have real users' data). |
| **You do** | Decide on a name/domain if you want one, decide who the first real users are (friends? A university careers society? A subreddit?), handle the actual "telling people this exists" part — that's a business decision, not mine to make. |
| **Checkpoint** | Someone who isn't you creates an account and gets a real, correct job notification. |

---

## Phase 10 — Later (not blocking launch)

Once the core product is live and validated: Stripe integration for the freemium tiers we discussed, Claude-API-powered job ranking/application assistance, and starting the Tier 2 outreach conversations (TargetJobs, Milkround, Bright Network etc.) — now with a working product as leverage, exactly as you planned from the start.

---

## A note on pacing

This is a lot of phases, and that's honest, not padding — a real multi-user product is a genuinely bigger undertaking than the daily-email prototype was. Nothing here requires you to have written code before; every "you do" item is either a decision, a real-world test, or clicking through a signup with my exact instructions. Where it gets technical, I'll explain as we go, the same way I did with the dedup engine.
