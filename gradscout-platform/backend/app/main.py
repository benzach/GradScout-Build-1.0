"""
GradScout API. Run locally with:
    uvicorn app.main:app --reload

Then visit http://localhost:8000/docs for the interactive API
documentation — FastAPI builds this automatically from the code, it's
not something maintained separately. This is what Phase 3's checkpoint
uses: create a test user, save some criteria, pull a real feed, all
through that page in your browser.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import criteria, jobs, users

app = FastAPI(
    title="GradScout API",
    description=(
        "Graduate job matching API. Auth is currently a STUB (see "
        "app/auth.py) — pass any real user's UUID in an X-User-Id header. "
        "Real auth arrives in Phase 4."
    ),
    version="0.3.0",
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

app.include_router(users.router)
app.include_router(criteria.router)
app.include_router(jobs.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
