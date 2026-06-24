# nanowork-mobile-agent

> An AI-powered platform that takes a founder from a text message to a live, paid web product — entirely through SMS conversation.

---

## What is this?

Nanowork is a **multi-agent build system** delivered over SMS (via Linq). A founder texts in, describes what they want to build, and the system walks them through a full product-creation workflow: preview → payment → finances → full web app build → deployment. All output is a single-page React app stored in Supabase and served at a custom subdomain.

---

## Current Build Overview

| Layer | Technology |
|---|---|
| API server | FastAPI (`nanowork_mobile.api`) |
| Runtime | Python 3.11+, managed by `uv` |
| Deployment | **Render** (Python native runtime, FastAPI via uvicorn); secrets from environment |
| Scheduled jobs | Render Cron Jobs or any scheduler POSTing to `/internal/*` |
| Database / auth | Supabase (Postgres) |
| SMS channel | Linq API |
| Email | Resend |
| Payments | Stripe (checkout + webhooks + Connect) |
| LLM backbone | Anthropic Claude (primary) + Google Gemini (image generation) |
| Preview static host | **Vercel** (optional via `VERCEL_DEPLOY_*`); CDN URL templates supported |

---

## Agent Map

The system is built around a pipeline of single-responsibility AI agents. Each agent lives in `src/nanowork_mobile/agents/`.

### Conversation-layer agents

These agents own the SMS conversation with the founder.

| Agent | File | Role |
|---|---|---|
| **CFO Agent** | `agents/cfo_agent.py` | Runs a 3-turn financial advisory conversation after payment is confirmed. Captures pricing model (subscription / one-time / freemium / usage-based), pricing specifics, and payment integration preferences. Transitions the session to the page-building phase when done. |
| **CMO Agent** | `agents/cmo_agent.py` | ⚠️ **Currently disabled** (bootstrapping cost decision). When re-enabled: handles marketing strategy, optional Google Ads + X ad running (at $0.05/run over ad cost), and pitch-deck generation. Even when disabled, ad/campaign drafts are still created for manual use. See re-enable checklist in the file header. |

### Build-pipeline agents

These agents are invoked in sequence by the orchestrator to produce the final web app.

| Agent | File | Role |
|---|---|---|
| **Orchestrator Agent** | `agents/orchestrator_agent.py` | Central coordinator. Runs the full 6-phase SDLC pipeline (Requirements → Architecture → Development → Testing → Release → Maintenance) for premium builds, and a faster preview pipeline (design blueprint → landing page) for pre-payment previews. Publishes previews to **Vercel** when enabled, otherwise the configured preview URL or backend route; full sites to `<slug>.nanowork.app`. |
| **Design Agent** | `agents/design_agent.py` | Creates a unified **site blueprint** before any pages are built. Analyses the business type and audience to choose the right visual language (design style, brand colour, hero layout, typography, nav/footer variants). All page builders share this blueprint so the whole site looks like it was designed by one person. |
| **Image Agent** | `agents/image_agent.py` | Generates one hero image and one logo mark per build using Google Gemini image generation. Outputs base64 data URIs so the final HTML is fully standalone with no external image hosting. Fails open — if Gemini is unavailable the pipeline continues with Tailwind-only rendering. |
| **Page Builder Agent** | `agents/page_builder_agent.py` | Generates individual page JSX from a context dict. Owns the design system (6 styles: `editorial`, `minimal`, `bold`, `soft`, `technical`, `luxury`), brand colour logic, and the React shell wrapper. One responsibility: turn a context dict + blueprint into clean, deployable HTML for a single page. |
| **Page Stitcher Agent** | `agents/page_stitcher_agent.py` | Multi-page site assembly in 3 steps: (1) plan site map with inter-page navigation, (2) build each page individually with nav placeholders, (3) replace placeholders with real React component names. Knows all 10 standard page types: `home`, `login`, `signup`, `pricing`, `about`, `contact`, `financials`, `ad`, `analytics`, `wallet`. |
| **Syntax Agent** | `agents/syntax_agent.py` | Pass 1 of quality assurance. Scans JSX for Babel-standalone incompatibilities (optional chaining, nullish coalescing, TypeScript syntax, import/export statements, etc.) and auto-fixes them in two passes: Python precheck → Claude fix → re-check. |
| **Final Testing Agent** | `agents/final_testing_agent.py` | Pass 3 of quality assurance (Pass 2 is the syntax agent's second pass). Acts as a QA engineer that mentally loads the component in a browser. Hunts for JS errors, Babel transpilation failures, unclosed JSX tags, unmatched braces, and anything else that would cause a blank or broken page. |
| **Assembly Agent** | `agents/assembly_agent.py` | Final step in the build pipeline. Takes JSX from each page agent and stitches them into a single cohesive React SPA with shared Nav + Footer (from `ui_components.py`), client-side routing via `React.useState`, and guaranteed reachability of Auth + Pricing CTAs. Passes the assembled output through Syntax Agent and Final Testing Agent before storing. |
| **CRM Agent** | `agents/crm_agent.py` | Designs and provisions a customer database schema tailored to each business type. Reads business description and Q&A context, asks Claude to decide what customer fields to track, and stores the schema in Supabase (`business_schemas`). Reused on every form submission from the live site. |

### SDLC phase modules

The orchestrator delegates to named phase modules in `agents/phases/`. Each phase is a single async function.

| Phase | File | What it does |
|---|---|---|
| Phase 1 — Requirements | `phases/requirements_phase.py` | Pure data normalisation — no LLM call. Formalises raw user context into a typed `RequirementsSpec` (pages, pricing, ads flags) that all downstream phases consume. |
| Phase 2 — Architecture | `phases/architecture_phase.py` | Calls Design Agent (site blueprint) + Page Stitcher Agent (navigation plan) to produce an `ArchitectureSpec`. Reuses an existing blueprint from the preview phase if available. |
| Phase 3 — Development | `phases/development_phase.py` | Builds all requested pages in parallel using the Page Builder + Page Stitcher agents. |
| Phase 4 — Testing | `phases/testing_phase.py` | Runs Syntax Agent + Final Testing Agent on each built page. |
| Phase 5 — Release | `phases/release_phase.py` | Calls Assembly Agent to stitch the SPA, stores it in Supabase, and returns the live URL. |
| Phase 6 — Maintenance | `phases/maintenance_phase.py` | Applies bug-fix patches and post-launch refinements via targeted LLM calls. |

---

## User-facing Workflow

```
SMS: "hey I want to build X"
        │
        ▼
  Welcome + name capture
        │
        ▼
  Build idea Q&A  (context.json assembled turn by turn)
        │
        ▼
  Preview generated  →  served on Vercel or your preview CDN / API route
  (24 h expiry, Stripe checkout link sent)
        │
        ▼
  Stripe payment confirmed  →  CFO conversation (pricing model)
        │
        ▼
  [CMO conversation — DISABLED]
        │
        ▼
  Full 6-phase build  →  <slug>.nanowork.app
        │
        ▼
  Post-launch: bug fixes, refinements, new businesses restart the flow
```

---

## Automated Cron Jobs

Schedule HTTP POST requests to the internal endpoints below (for example with **Render Cron Jobs**). Each job must send the `x-internal-secret` header matching `INTERNAL_SECRET`.

| Job name | Schedule (UTC) | Endpoint | Purpose |
|---|---|---|---|
| `nanowork-payout-reminder` | 10:00 on the 24th of every month | `/internal/cron/payout-reminder` | Reminds founders with Stripe Connect balances to trigger a payout |
| `nanowork-abandoned-payment-nudge` | 16:00 every Monday | `/internal/cron/abandoned-payment-nudge` | Nudges users who saw a preview but never paid |
| `nanowork-connect-onboarding-reminder` | 17:00 every Monday | `/internal/cron/connect-onboarding-reminder` | Reminds users who started but didn't complete Stripe Connect onboarding |
| `nanowork-preview-expiry` | Every hour | `/internal/expire-previews` | Enforces the 24 h preview expiry promise |
| `nanowork-payment-nudge` | Every 3 hours | `/internal/payment-nudge` | One-time gentle nudge for previews aged 12–24 h without payment |

---

## Key Modules (non-agent)

| Module | File | Purpose |
|---|---|---|
| API server | `api.py` | FastAPI entry point. Handles Linq webhooks, Stripe webhooks, internal cron endpoints, page serving, OG image routes, and health/info endpoints. |
| Task queue | `tasks.py` + `async_queue.py` | Async message processing pipeline. Deduplicates and serialises per-user message handling. |
| Conversation control | `conversation_control.py` | Manages state machine transitions and per-user locks to prevent race conditions. |
| LLM client | `llm_client.py` | Thin wrapper around the Anthropic SDK. Used by all agents. |
| Brain client | `brain_client.py` | Secondary LLM interface (used for specific reasoning tasks). |
| Database | `db.py` | Supabase client initialisation and low-level query helpers. |
| Services | `services.py` | Outbound integrations: Linq SMS send, reactions, Resend email. |
| Stripe Connect | `stripe_connect.py` | Handles Stripe Connect account creation, onboarding links, and payout logic. |
| Customer infra | `customer_infra.py` | Provisions per-customer infrastructure resources. |
| OG image | `og_image.py` | Generates and injects Open Graph preview images for built sites. |
| Vercel deploy | `vercel_deploy.py` | Pushes standalone preview `index.html` to Vercel when `VERCEL_DEPLOY_ENABLED=true`. |
| Changelog | `changelog.py` | Serves versioned changelog content to the frontend. |
| Waitlist flow | `nano_deploy/waitlist_flow.py` | Main conversation state machine — drives the SMS flow from welcome through build. |
| Waitlist DB | `nano_deploy/waitlist_db.py` | All Supabase read/write operations for the waitlist/build table. |
| Page generator | `nano_deploy/page_generator.py` | Low-level page HTML storage and retrieval. |
| Context builder | `nano_deploy/context_builder.py` | Assembles the `context.json` blob passed between conversation turns and agents. |

---

## Setup

```bash
# Install dependencies
uv sync

# Copy and fill in secrets
cp .env.example .env
# Edit .env with your keys (see the table below for the full list)
```

### Required environment variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key (primary LLM) |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase service role key |
| `SUPABASE_ANON_KEY` | Supabase anon/public key (injected into generated app clients) |
| `LINQ_API_KEY` | Linq SMS platform API key |
| `LINQ_BASE_URL` | Linq API base URL (default: `https://api.linqapp.com/api/partner/v3`) |
| `RESEND_API_KEY` | Resend transactional email key |
| `RESEND_FROM` | Sender address for Resend emails |
| `GEMINI_API_KEY` | Google Gemini key (image generation — optional, fails open) |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret |
| `INTERNAL_SECRET` | Shared secret for internal cron endpoint auth |
| `APP_BASE_URL` | Public base URL (e.g. `https://nanowork.app`) |
| `NANOWORK_DOMAIN` | Apex domain for subdomain routing (e.g. `nanowork.app`) |
| `MAIN_REPO_URL` | URL of this repo (used for self-reference in some flows) |

#### Optional preview / CDN

| Variable | Description |
|---|---|
| `VERCEL_DEPLOY_ENABLED` | Set to `true` to publish previews via `vercel_deploy` |
| `VERCEL_TOKEN` | Vercel API bearer token |
| `VERCEL_PROJECT_ID` | Unused for filesystem previews unless `VERCEL_PREVIEW_ATTACH_PROJECT_ID=true` |
| `VERCEL_PREVIEW_ATTACH_PROJECT_ID` | `true` — attach each filesystem preview to `VERCEL_PROJECT_ID` (default off) |
| `VERCEL_TEAM_ID` | Team / org scope (optional) |
| `PREVIEW_PREFER_VERCEL_DEPLOY_URL` | `false` — use branded subdomain URL vs raw deploy URL (`true`/omit default) |
| `PREVIEW_PUBLIC_URL_TEMPLATE` | Override preview URL shape, `{slug}` (optional) |
| `PREVIEW_CDN_DOMAIN` | Alias for legacy `PREVIEW_CLOUDFRONT_DOMAIN` — CDN host for previews (optional) |

### Deployment (Render + optional Vercel previews)

**Backend API (Render)**

1. Create a Web Service with the Python native runtime (`render.yaml` uses `uv sync` for the build command).
2. **Start command (must bind all interfaces — not `127.0.0.1`)** Render probes **`0.0.0.0:$PORT`**; if you bind to localhost only or to a fixed port like `8000`, deploys hang with “no open ports on 0.0.0.0”. Use **`$PORT`** (Render assigns it):

   ```bash
   .venv/bin/uvicorn nanowork_mobile.api:app --host 0.0.0.0 --port $PORT
   ```

   Do **not** paste the local-dev command from “Run locally” below (`--reload`, `--host 127.0.0.1`, `--port 8000`) — that is only for your machine.

3. Add every secret from `.env`/the table below in the Render dashboard (Environment).

**Preview static hosting (Vercel mirror)**

Optional: enable `VERCEL_DEPLOY_ENABLED=true`, set `VERCEL_TOKEN`, and optionally `VERCEL_TEAM_ID`. By default filesystem previews **do not** use `VERCEL_PROJECT_ID` (set `VERCEL_PREVIEW_ATTACH_PROJECT_ID=true` only if you need uploads attached to one project).

By default (**`PREVIEW_PREFER_VERCEL_DEPLOY_URL`**, omit or `true`), user-facing preview links prefer the actual Vercel deployment URL so the opened page matches the uploaded `index.html`. Set **`PREVIEW_PREFER_VERCEL_DEPLOY_URL=false`** to send branded `https://{slug}.{apex}` URLs instead — then wildcard DNS must hit FastAPI subdomain middleware **or** a Next route that loads **`GET {APP_BASE_URL}/api/public/preview/{slug}`** (same payload as **`GET /preview/{slug}`**).

Alternatively, configure `PREVIEW_PUBLIC_URL_TEMPLATE` / `PREVIEW_CDN_DOMAIN` (see below) without using the Vercel deploy API.

**Cron jobs**

Configure scheduled POSTs in Render Cron or another scheduler to the URLs in “Automated Cron Jobs”, each including `x-internal-secret: $INTERNAL_SECRET`.

### Run locally *(development machine only)*

These flags are for **fast reload on localhost**. They are **incorrect on Render**: use **`--host 0.0.0.0 --port $PORT`** there and omit **`--reload`**.

The ASGI app is **`nanowork_mobile.api:app`**. After **`uv sync`**, **`uv run`** resolves the **`uvicorn` CLI** in the project env:

```bash
uv run uvicorn nanowork_mobile.api:app --reload --host 127.0.0.1 --port 8000
```

Same using the venv binary:

```bash
.venv/bin/uvicorn nanowork_mobile.api:app --reload --host 127.0.0.1 --port 8000
```

| Endpoint | Purpose |
|---|---|
| `http://127.0.0.1:8000/health` | Health check |
| `http://127.0.0.1:8000/info` | Build info / version |
| `http://127.0.0.1:8000/docs` | Interactive API docs (Swagger UI) |
| `http://127.0.0.1:8000/api/public/preview/<slug>` | JSON `{ slug, html }` for apex ``/preview`` pages on Vercel |
| `http://127.0.0.1:8000/preview/<slug>` | Preview HTML (direct from API) |
| `http://127.0.0.1:8000/<slug>` | Full site (local dev) |

### Run tests

```bash
uv run pytest
```

---

## Preview URLs (Vercel or CDN templates)

Configure one of:

- **Vercel** (`VERCEL_DEPLOY_ENABLED` + `VERCEL_TOKEN`, etc.) — the app creates a deployment per preview slug.
- **URL templates** — `PREVIEW_PUBLIC_URL_TEMPLATE` with `{slug}` and/or `PREVIEW_CDN_DOMAIN` (alias: `PREVIEW_CLOUDFRONT_DOMAIN`) with `PREVIEW_CLOUDFRONT_MODE` = `path` or `subdomain`.
- **Default** — `https://{NANOWORK_DOMAIN}/preview/{slug}` when `NANOWORK_DOMAIN` is set, else `APP_BASE_URL/preview/{slug}`, when templates and CDN domain are unset.

---

## Source layout

```
src/nanowork_mobile/
├── api.py                      # FastAPI app entry point
├── tasks.py                    # Message processing pipeline
├── async_queue.py              # Per-user async serialisation
├── conversation_control.py     # State machine + concurrency locks
├── llm_client.py               # Anthropic SDK wrapper
├── brain_client.py             # Secondary LLM interface
├── db.py                       # Supabase client
├── services.py                 # Linq SMS + Resend email
├── stripe_connect.py           # Stripe Connect integration
├── customer_infra.py           # Per-customer infra provisioning
├── og_image.py                 # Open Graph image generation
├── vercel_deploy.py            # Vercel preview static deploy API
├── changelog.py                # Changelog serving
├── context.md                  # Product rules & workflow spec
│
├── agents/
│   ├── orchestrator_agent.py   # Central pipeline coordinator
│   ├── design_agent.py         # Site blueprint & visual system
│   ├── image_agent.py          # Gemini hero/logo image generation
│   ├── page_builder_agent.py   # Single-page JSX generation
│   ├── page_stitcher_agent.py  # Multi-page assembly & nav wiring
│   ├── syntax_agent.py         # JSX/Babel syntax QA (Pass 1)
│   ├── final_testing_agent.py  # Browser-compatibility QA (Pass 3)
│   ├── assembly_agent.py       # SPA stitching & final wrap
│   ├── cfo_agent.py            # Financial conversation agent
│   ├── cmo_agent.py            # Marketing agent (currently disabled)
│   ├── crm_agent.py            # Customer schema designer
│   ├── ui_components.py        # Pre-built Nav/Footer JSX variants
│   ├── static_fallbacks.py     # Fallback HTML for error states
│   ├── sdlc_artifacts.py       # Typed specs passed between phases
│   └── phases/
│       ├── requirements_phase.py   # Phase 1: data normalisation
│       ├── architecture_phase.py   # Phase 2: blueprint + nav plan
│       ├── development_phase.py    # Phase 3: parallel page builds
│       ├── testing_phase.py        # Phase 4: syntax + QA passes
│       ├── release_phase.py        # Phase 5: assembly + deploy
│       └── maintenance_phase.py    # Phase 6: post-launch patches
│
└── nano_deploy/
    ├── waitlist_flow.py        # Main SMS conversation state machine
    ├── waitlist_db.py          # Supabase read/write operations
    ├── page_generator.py       # Page HTML storage & retrieval
    └── context_builder.py      # context.json assembly
```
# Nanowork-mobile-mvp
