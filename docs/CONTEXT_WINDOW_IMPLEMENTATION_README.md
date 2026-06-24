# Context Window Implementation Notes

This document records notable implementation work for `nanowork-mobile`.

## Scope completed (historical highlights)

1. Customer-scoped `context.md` persistence in Supabase flow.
2. GitHub App installation-token deploy path (repo-scoped token after repo creation).
3. Production hosting: **Render** (FastAPI backend) and **Vercel** for static preview deployments when enabled.

---

## 1) Customer-scoped `context.md` persistence

See `src/nanowork_mobile/nano_deploy/context_document.py` (`render_context_markdown`) and orchestrator / waitlist wiring. Migration: `migrations/2026_04_context_md_and_app_domain.sql`.

---

## 2) GitHub App token flow

See `src/nanowork_mobile/github_deploy.py` for PAT vs GitHub App installation tokens.

---

## 3) Preview and release hosting

- **API**: Render Python runtime; `.venv/bin/uvicorn nanowork_mobile.api:app` on `$PORT` (see `render.yaml`).
- **Previews**: Set `VERCEL_DEPLOY_ENABLED` and `VERCEL_*` vars to push `index.html` to Vercel; otherwise previews resolve via `PREVIEW_PUBLIC_URL_TEMPLATE` / `PREVIEW_CLOUDFRONT_DOMAIN` (`PREVIEW_CDN_DOMAIN`) or the backend `/preview/{slug}` route.
- Scheduled jobs hit `/internal/...` with `x-internal-secret` (configure in Render Cron Jobs or another scheduler).

Environment variables:

- Render: usual app secrets (`ANTHROPIC_API_KEY`, `SUPABASE_*`, `INTERNAL_SECRET`, …).
- Vercel previews: `VERCEL_DEPLOY_ENABLED`, `VERCEL_TOKEN`, optional `VERCEL_PROJECT_ID`, `VERCEL_TEAM_ID`.

---

## Verification

Run `uv run pytest` after substantive changes. The `/health` endpoint exposes basic readiness metadata.
