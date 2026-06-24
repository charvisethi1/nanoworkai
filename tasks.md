# Post-Payment Flow — Implementation Tasks
# Stack: Next.js (Vercel) + FastAPI (Render) + QStash + Upstash Redis
# Scope: Stripe webhook received → live URL returned
# Target: 3.5 hours

---

## Pre-work (15 min) — do this before the clock starts

- [ ] Open the other repo. Find the orchestration entry point — what function/route kicks off the multi-agent run
- [ ] Note exactly what it takes as input and what it returns (even if informal)
- [ ] Set env vars locally: `QSTASH_TOKEN`, `QSTASH_CURRENT_SIGNING_KEY`, `QSTASH_NEXT_SIGNING_KEY`, `NEXT_PUBLIC_APP_URL`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, `GITHUB_TOKEN`, `VERCEL_TOKEN`, `VERCEL_TEAM_ID`, `STRIPE_WEBHOOK_SECRET`, `FASTAPI_INTERNAL_SECRET`, `FASTAPI_BASE_URL`

---

## Block 0 — Define the contract between Next.js and FastAPI (20 min)
> This is the most important block. Everything else depends on it.

### T-01 · Define the orchestration API contract

Look at the existing agents in the other repo and agree on this interface — write it down before touching code:

**Request** — Next.js POSTs to FastAPI:
```json
POST /orchestrate
Authorization: Bearer {FASTAPI_INTERNAL_SECRET}
{
  "job_id": "uuid",
  "slug": "project-slug",
  "prior_agent_output": { ... }
}
```

**Response** — FastAPI returns:
```json
{
  "file_tree": {
    "index.html": "...",
    "styles.css": "...",
    "vercel.json": "{\"version\":2}"
  },
  "status": "done" | "failed",
  "error": null | "message"
}
```

- [ ] Confirm what `prior_agent_output` actually looks like from the pre-payment flow — check the other repo
- [ ] Confirm what the agents return today — file tree? raw HTML? something else?
- [ ] If the agents don't return a file tree yet, define the adapter layer you'll write in FastAPI to normalize the output
- [ ] Add `POST /orchestrate` stub to FastAPI (returns hardcoded file tree) so Next.js integration can be tested independently

> The FastAPI side doesn't need to be fully wired in 3.5 hours — the stub lets you build and test the entire Next.js → GitHub → Vercel pipeline with real HTTP calls while the agents are being ported.

---

## Block 1 — Stripe Webhook + QStash (25 min)

### T-02 · Stripe webhook handler
`/api/webhooks/stripe.ts`

- [ ] `export const config = { api: { bodyParser: false } }`
- [ ] Verify Stripe signature: `stripe.webhooks.constructEvent(rawBody, sig, STRIPE_WEBHOOK_SECRET)`
- [ ] Bad sig → `400`. Must return `200` to Stripe within 5s
- [ ] Extract `slug`, `job_id`, `user_id` from `event.data.object.metadata`
- [ ] Missing fields → log `{ event: 'missing_metadata', job_id }`, return `400`

### T-03 · Idempotency guard + QStash publish
- [ ] Check Redis: `GET post:{job_id}:status` — if exists, drop and return `200`
- [ ] Fetch `prior_agent_output` from Redis: `GET pre:{job_id}:agent:output`
- [ ] Publish to QStash:
  ```ts
  await qstash.publishJSON({
    url: `${process.env.NEXT_PUBLIC_APP_URL}/api/worker`,
    body: { job_id, slug, user_id, prior_agent_output }
  })
  ```
- [ ] Set Redis: `post:{job_id}:status = queued`
- [ ] Return `200`

### T-04 · Smoke test
- [ ] `stripe listen --forward-to localhost:3000/api/webhooks/stripe`
- [ ] `stripe trigger checkout.session.completed`
- [ ] Confirm Redis key `post:{job_id}:status = queued`, QStash message visible in Upstash console

---

## Block 2 — Worker + FastAPI Bridge (40 min)

### T-05 · QStash worker endpoint
`/api/worker.ts`

- [ ] Verify QStash signature with `Receiver` from `@upstash/qstash`
- [ ] Parse body: `{ job_id, slug, user_id, prior_agent_output }`
- [ ] Set Redis: `post:{job_id}:status = processing`
- [ ] Call `runPostPaymentOrchestration(payload)` — await it
- [ ] On success: return `200` (QStash won't retry)
- [ ] On error: set `post:{job_id}:status = failed`, store error, return `500` (QStash retries)

> ⚠️ Vercel function timeout: Hobby = 60s, Pro = 300s. If full orchestration + GitHub + Vercel deploy exceeds this, the function dies and QStash retries the whole job. Check your plan. If on Hobby, set `maxDuration: 60` in `vercel.json` and accept that complex jobs may fail — upgrade to Pro or move the worker to Render too.

### T-06 · FastAPI bridge
`/services/orchestration.ts`

- [ ] `POST ${FASTAPI_BASE_URL}/orchestrate` with `Authorization: Bearer {FASTAPI_INTERNAL_SECRET}`
- [ ] Body: `{ job_id, slug, prior_agent_output }`
- [ ] Timeout: 120s (set explicitly — default fetch has no timeout)
- [ ] On non-2xx: throw with status + body for debugging
- [ ] On success: return `{ file_tree, status, error }`
- [ ] Store file tree in Redis: `post:{job_id}:file_tree`

### T-07 · FastAPI stub (in the FastAPI repo)
`POST /orchestrate`

- [ ] Add route, verify `Authorization` header matches `FASTAPI_INTERNAL_SECRET`
- [ ] Return hardcoded file tree for now:
  ```python
  return {
    "file_tree": {
      "index.html": "<h1>Hello from {slug}</h1>",
      "vercel.json": '{"version":2}'
    },
    "status": "done",
    "error": None
  }
  ```
- [ ] Deploy stub to Render — get the live URL, set as `FASTAPI_BASE_URL`
- [ ] Test: `curl -X POST {FASTAPI_BASE_URL}/orchestrate -H "Authorization: Bearer ..." -d '{...}'`

> Port the real agents into this route after the full pipeline is working end-to-end with the stub.

---

## Block 3 — GitHub + Vercel (40 min)

### T-08 · GitHub service
`/services/github.ts`

- [ ] `npm install @octokit/rest`
- [ ] `createRepo(slug)`: `POST /user/repos` — `name: nanowork-{slug}`, `private: true`, `auto_init: false`
  - 422 (exists) → log and continue
- [ ] `commitFileTree(repoFullName, fileTree)`:
  - Build all blobs in parallel: `Promise.all(files.map(f => createBlob(f)))`
  - Create single Git tree from all blobs
  - Create commit on `main`, update ref
- [ ] Store: `post:{job_id}:github_repo`
- [ ] Throw on failure — do not proceed to Vercel

### T-09 · Vercel service
`/services/vercel.ts`

- [ ] `createVercelProject(slug, repoFullName)`: `POST /v9/projects`
  - Link GitHub repo, `framework: null`, `rootDirectory: /`
  - 409 (exists) → fetch project ID and continue
- [ ] Store: `post:{job_id}:vercel_project_id`
- [ ] GitHub push triggers auto-deploy
- [ ] `pollDeployment(projectId)`: `GET /v13/deployments?projectId=...&limit=1` every 5s, max 10 attempts
  - `READY` → store URL, proceed
  - `ERROR` → throw
  - Timeout → throw "Vercel deploy timed out"
- [ ] Store: `post:{job_id}:vercel_deploy_url`

### T-10 · Pipeline test with stub
- [ ] Run full flow with FastAPI stub returning hardcoded file tree
- [ ] Verify: GitHub repo created → Vercel deploy READY → `{slug}.nanowork.app` loads
- [ ] This confirms the entire pipeline before real agents are wired in

---

## Block 4 — Job Completion + Status API (15 min)

### T-11 · Mark job done
Inside `runPostPaymentOrchestration`, after Vercel READY:
- [ ] `post:{job_id}:status = done`
- [ ] `post:{job_id}:live_url = https://nanowork.app/preview/{slug}`

### T-12 · Job status route
`/api/job-status.ts`

- [ ] `GET /api/job-status?job_id={job_id}`
- [ ] Read `status`, `live_url`, `error` from Redis
- [ ] Return: `{ status, live_url?, error? }`
- [ ] Frontend polls every 3s → spinner → on `done` redirect to `live_url`

---

## Block 5 — Port Real Agents + E2E Test (45 min)

### T-13 · Port orchestration into FastAPI `/orchestrate`
- [ ] Move agents from other repo into this FastAPI codebase
- [ ] Wire existing multi-agent flow into `POST /orchestrate`:
  - Input: `{ job_id, slug, prior_agent_output }`
  - Agents run, produce output
  - Normalize output into file tree format defined in T-01
- [ ] Test locally: does the route return a valid file tree for a real input?
- [ ] Deploy to Render

### T-14 · End-to-end test with real agents
- [ ] Fire Stripe webhook → watch Redis: `queued → processing → done`
- [ ] GitHub repo has AI-generated code
- [ ] Vercel deployed, `{slug}.nanowork.app` loads with real output
- [ ] `/api/job-status` returns `done` + correct URL

### T-15 · Hardening
- [ ] Duplicate Stripe event → idempotency drop ✓
- [ ] FastAPI returns non-2xx → job fails cleanly, error stored
- [ ] GitHub 422 → reuse repo ✓
- [ ] Vercel timeout → fail with message ✓
- [ ] Every log line includes `job_id`

---

## Time Budget

| Block | Tasks | Time |
|---|---|---|
| Pre-work | — | 15 min |
| Block 0: Contract definition | T-01 | 20 min |
| Block 1: Webhook + QStash | T-02 to T-04 | 25 min |
| Block 2: Worker + FastAPI bridge | T-05 to T-07 | 40 min |
| Block 3: GitHub + Vercel | T-08 to T-10 | 40 min |
| Block 4: Job completion + status | T-11 to T-12 | 15 min |
| Block 5: Real agents + E2E | T-13 to T-15 | 45 min |
| **Total** | | **3h 20min** |

---

## Cut List (if running over)

1. **Real agents (T-13)** — ship with the stub returning hardcoded output, port agents in next session. The pipeline is proven, agents are just content.
2. **Vercel polling** — replace with `await sleep(60000)` then mark done. Brittle but works for demo.
3. **Hardening (T-15)** — skip for now, add after first real user goes through the flow.

---

## Architecture at a Glance

```
Stripe webhook
  → /api/webhooks/stripe (Next.js, Vercel)
    → QStash.publishJSON
      → /api/worker (Next.js, Vercel)
        → POST /orchestrate (FastAPI, Render)  ← agents live here
          → file_tree returned
        → GitHub: create repo + commit file tree
        → Vercel: create project + poll deploy
        → Redis: status = done, live_url set
  → /api/job-status polled by frontend
    → redirect to {slug}.nanowork.app
```

## Upstash Redis Keys

```
pre:{job_id}:agent:output          ← INPUT from pre-payment flow

post:{job_id}:status               → queued | processing | done | failed
post:{job_id}:error                → error string
post:{job_id}:file_tree            → file tree JSON from FastAPI
post:{job_id}:github_repo          → repo URL
post:{job_id}:vercel_project_id    → prj_...
post:{job_id}:vercel_deploy_url    → Vercel deploy URL
post:{job_id}:live_url             → https://{slug}.nanowork.app
```

## Env Vars

| Var | Where |
|---|---|
| `STRIPE_WEBHOOK_SECRET` | Stripe dashboard |
| `QSTASH_TOKEN` | Upstash console |
| `QSTASH_CURRENT_SIGNING_KEY` | Upstash console |
| `QSTASH_NEXT_SIGNING_KEY` | Upstash console |
| `NEXT_PUBLIC_APP_URL` | Your Vercel deployment URL |
| `UPSTASH_REDIS_REST_URL` | Upstash console |
| `UPSTASH_REDIS_REST_TOKEN` | Upstash console |
| `FASTAPI_BASE_URL` | Render deployment URL |
| `FASTAPI_INTERNAL_SECRET` | Generate a random string |
| `ANTHROPIC_API_KEY` | Anthropic console |
| `GITHUB_TOKEN` | GitHub → Settings → PAT (repo scope) |
| `VERCEL_TOKEN` | Vercel → Settings → Tokens |
| `VERCEL_TEAM_ID` | Vercel team settings |