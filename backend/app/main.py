"""
GradScout API. Run locally with:
    uvicorn app.main:app --reload

Then visit http://localhost:8000/docs for the interactive API
documentation — FastAPI builds this automatically from the code, it's
not something maintained separately.

Auth is real Supabase JWT verification (app/auth.py) — there's no
POST /users endpoint. A user's app-side profile row gets created
automatically the first time a valid token from them hits any
authenticated endpoint, keyed on the same UUID Supabase assigned them.
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import criteria, jobs
from app.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # DISABLE_SCHEDULER exists so tests (and local one-off API poking)
    # don't accidentally kick off real scraping/API calls every time the
    # app starts — set it in test fixtures, leave it unset in deployment.
    if os.environ.get("DISABLE_SCHEDULER") != "true":
        start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="GradScout API",
    description=(
        "Graduate job matching API. Authenticated via Supabase-issued JWTs "
        "— send a valid Supabase session token as 'Authorization: Bearer <token>'. "
        "A background scheduler (app/scheduler.py) scrapes all sources and "
        "computes matches on an interval — see /health for basic status."
    ),
    version="0.6.0",
    lifespan=lifespan,
)

# Permissive for now (Phase 4/dev) — every origin allowed. Tighten this
# to your actual frontend domain(s) once Phase 6 gives you one; a
# wide-open CORS policy is fine for a backend with no cookies/session
# state (this API is stateless, auth is a header, not a cookie) but
# isn't something to carry forward indefinitely without reconsidering.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(criteria.router)
app.include_router(jobs.router)


@app.get("/")
def root():
    """
    Friendly landing so visiting the bare domain doesn't look broken —
    without this, '/' returns an unstyled 404 that's easy to mistake for
    a genuine deployment failure.
    """
    return {
        "service": "GradScout API",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}
