"""
DNS agent — Render custom-domain provisioning.

Provisions {slug}.nanowork.app as a custom domain on the Render service
so the backend can serve the full site. For previews, no DNS provisioning
is needed — previews use ``{slug}.nanowork.app`` (same backend via wildcard DNS).

Required env vars (for full-site subdomain provisioning):
  RENDER_API_KEY          Render API key
  RENDER_SERVICE_ID       Render service ID for the backend

Stub mode (creds absent): logs + skips external calls so the job never fails
because DNS isn't configured yet.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

BASE_DOMAIN = "nanowork.app"
_RENDER_API_BASE = "https://api.render.com/v1"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def provision_subdomain(slug: str, job_id: str) -> str:
    """
    Registers {slug}.nanowork.app as a custom domain on Render.

    Returns the full subdomain (e.g. "myapp.nanowork.app").
    Non-fatal: logs on missing creds or API errors so the overall job succeeds.
    """
    safe_slug = _slugify(slug)
    subdomain = f"{safe_slug}.{BASE_DOMAIN}"

    logger.info("[dns] provisioning  job_id=%s  subdomain=%s", job_id, subdomain)
    await _add_render_custom_domain(subdomain, job_id)
    logger.info("[dns] provisioned  job_id=%s  domain=%s", job_id, subdomain)
    return subdomain


# ---------------------------------------------------------------------------
# Render custom domain
# ---------------------------------------------------------------------------

async def _add_render_custom_domain(domain: str, job_id: str) -> None:
    """Adds a custom domain to the Render web service via the Render API."""
    api_key = os.getenv("RENDER_API_KEY", "").strip()
    service_id = os.getenv("RENDER_SERVICE_ID", "").strip()

    if not api_key or not service_id:
        logger.warning(
            "[dns] RENDER_API_KEY / RENDER_SERVICE_ID not set — "
            "skipping Render custom domain  job_id=%s",
            job_id,
        )
        return

    url = f"{_RENDER_API_BASE}/services/{service_id}/custom-domains"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json={"name": domain},
            )

        if resp.status_code in (200, 201):
            logger.info("[dns] Render custom domain added  %s  job_id=%s", domain, job_id)
            return
        if resp.status_code == 409:
            logger.info("[dns] Render custom domain already exists  %s  job_id=%s", domain, job_id)
            return

        logger.warning(
            "[dns] Render custom domain add returned %d — continuing  domain=%s  job_id=%s  body=%s",
            resp.status_code, domain, job_id, resp.text[:200],
        )
    except Exception as exc:
        logger.exception("[dns] Render custom domain failed  job_id=%s: %s", job_id, exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    slug = name.lower()
    slug = re.sub(rf'\.{re.escape(BASE_DOMAIN)}$', '', slug)
    slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')[:40]
    return slug
