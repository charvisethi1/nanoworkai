# GitHub → Vercel pipeline — follow-up ideas

Backlog items from aligning the preview pipeline with the post-payment GitHub → Vercel flow (`github_vercel_customer_hooks`). Pick these up when prioritizing infra or product work.

## Extra ideas (original list)

- **`PREVIEW_USE_GITHUB_VERCEL` (or similar)** — Separate flag from production GitHub deploy so staging can exercise preview GitHub/Vercel without enabling the same behavior across every code path that checks `GITHUB_DEPLOY_ENABLED`.

- **Deletion / retention** — Cron or manual job to archive or delete stale **preview** GitHub repos after N days (each preview build can create a new repo under the current `deploy_to_github` behavior).

- **Integration runbook** — Single checklist: `GITHUB_*` (PAT or App), `VERCEL_TOKEN`, `VERCEL_PROJECT_CREATE_ENABLED`, Vercel ↔ GitHub connection, `NANOWORK_PUBLIC_SITE_HOST` / apex DNS, optional `RENDER_*` if `trigger_customer_deploy` stays in the chain.

- **Repo naming / idempotency** — Today a `422` from GitHub (“repo exists”) skips push. Optional **reuse existing repo + force-push `main`** (or a preview branch) would make repeated previews for the same logical site safer and avoid orphan repos.

## Related suggestions (same theme)

- **Repo churn** — Consider **one repo per `customer_id`** (branches or force-push) vs **new repo per build** if GitHub API limits or org hygiene become an issue.

- **Latency / UX** — Git push + Vercel build is slower than the file-upload deployments API; consider user messaging, deploy webhooks, or polling if you need “green” before notifying.

- **`VERCEL_DEPLOY_ENABLED`** — When GitHub → Vercel is the primary path, turn **off** legacy file-upload previews in prod to avoid accidental double hosting when GitHub fails once and fallback runs.

- **Canonical URL vs origin** — Defaults: `PREVIEW_PREFER_VERCEL_DEPLOY_URL` true → SMS uses the deployment URL Vercel returns. Set false + wired DNS/API for `preview_url(slug)`. Filesystem uploads omit `VERCEL_PROJECT_ID` unless `VERCEL_PREVIEW_ATTACH_PROJECT_ID=true`.

- **`_deploy_preview_as_final`** — Still GitHub-only today; add **`create_customer_project_from_github`** (same hooks as release/preview) if reliability fallbacks should always get a Vercel project.

- **Private previews** — `deploy_to_github` defaults to public repos; evaluate **`private=True`** for previews if link leakage matters.

- **Observability** — Optional DB column for **`vercel_project_id`** on preview rows for support and dashboards.
