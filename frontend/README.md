# GradScout Frontend

React + Vite + Tailwind v4, built as an installable PWA (via
vite-plugin-pwa). Authenticates through Supabase directly, then talks
to the FastAPI backend using the resulting session token.

## Setup

```bash
npm install
cp .env.example .env   # fill in your real Supabase + Railway URLs
npm run dev
```

You need three values in `.env`:
- `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` — Project Settings → API
  in your Supabase dashboard. The anon key is safe to expose in frontend
  code; it's public by design.
- `VITE_API_BASE_URL` — your Railway backend's public URL

## What's built so far (Phase 6, screen 2 of 4)

- **Auth** (`src/context/AuthContext.jsx`, `src/lib/supabase.js`) — real
  Supabase email/password sign-up and sign-in, session persisted and
  kept in sync automatically.
- **Login screen** (`src/pages/Login.jsx`) — sign-in/sign-up toggle,
  handles Supabase's email-confirmation-required flow.
- **API client** (`src/lib/api.js`) — wraps `fetch`, automatically
  attaches the current session's token as `Authorization: Bearer
  <token>` on every backend call — this is what the backend's
  `app/auth.py` verifies.
- **Route protection** (`src/components/ProtectedRoute.jsx`) —
  redirects to `/login` if there's no active session.
- **Search criteria screen** (`src/pages/Criteria.jsx`) — full CRUD
  against the real `/criteria` endpoint: create, list, delete. Keywords
  use a chip-based free-text input (`src/components/TagInput.jsx`).
  Locations and Industry both use a searchable dropdown
  (`src/components/MultiSelectDropdown.jsx`) — closed by default so 52
  locations and 22 industries don't crowd the screen the way
  always-visible toggle chips would, with a search box inside the open
  panel for finding one option quickly. Both option lists are fetched
  from `GET /locations` / `GET /industries` — the backend's actual
  canonical lists — rather than hardcoded here, so this can never
  silently drift out of sync with what the backend categorizes jobs
  into. Minimum salary is a native `<select>` dropdown, £2,000
  increments starting at £18,000.
- **Home** (`src/pages/Home.jsx`) — hub screen showing your saved
  criteria count, links to manage them. Becomes the real job feed next.

## Note on onboarding flow

This screen works fully today, reachable from Home — but doesn't yet
force a brand-new user through it before they can do anything else.
That sequencing (sign up → must set up a search → land on your feed)
makes more sense to wire up once the feed screen itself exists next,
rather than guessing at the right flow before there's anywhere for it
to lead.

## PWA

`vite-plugin-pwa` generates the manifest and service worker
automatically on build — nothing to maintain by hand. One deliberate
choice: API calls are configured as `NetworkOnly` in the caching
strategy (see `vite.config.js`), since a job alert app silently showing
stale cached data would defeat the entire point of the product.

Icons at `public/icon-192.png` / `icon-512.png` are placeholders (a
simple mark) — swap these for real branding whenever you have it; nothing
else needs to change.

## Building for production / deploying

```bash
npm run build
```

Outputs to `dist/`. Deploy this to Vercel or Netlify (Phase 6 doesn't
cover hosting setup yet — that's grouped with the rest of Phase 6's
screens once they're all built).
