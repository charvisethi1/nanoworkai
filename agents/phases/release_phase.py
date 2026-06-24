"""
Phase 5 — Release

Assembles all validated pages into one cohesive SPA, deploys it, and returns the URL.

Steps:
  1. Wire up inter-page navigation (NAV_TO_x → ComponentName substitution)
  2. Assembly agent stitches pages + shared Nav/Footer + App router into one HTML file
  3. Store under a unique meaningful slug in the database
  4. Return the public URL

Wraps:
  - page_stitcher_agent.connect_page_links  (pure string substitution)
  - assembly_agent.assemble_final_site      (LLM stitching)
  - orchestrator_agent helpers              (slug, URL, DB write)
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from ...orchestration.cancel_flags import raise_if_cancelled
from ...db.schema import T
from ...nano_deploy.context_document import render_context_markdown
from ..assembly_agent import assemble_final_site
from ..page_stitcher_agent import connect_page_links
from ..sdlc_artifacts import ReleaseArtifact, TestArtifact

logger = logging.getLogger(__name__)

_ASSEMBLY_HEARTBEATS = [
    "almost ready — just finishing the final assembly",
]


async def _store_linq_memory(
    *,
    phone_number: str,
    ctx: dict,
    business_name: str,
    slug: str,
    site_url: str,
    pages: list[str],
    seo: dict,
) -> None:
    """
    Persist this build's output to LinqMemory so future generations for
    similar prompts can retrieve it via match_linq_memory and never produce
    the same company name, slug, or design again.

    Embeddings are left NULL here — the rag/embed_seed_data.py script
    will pick up unembedded rows on its next run.
    """
    from ...db import supabase

    original_prompt = ctx.get("build_idea") or ctx.get("description") or business_name
    output_summary = (
        f"{business_name} — {seo.get('meta_description', '')} "
        f"(slug: {slug}, pages: {', '.join(pages)})"
    ).strip()
    output_snapshot = json.dumps({
        "business_name": business_name,
        "slug": slug,
        "site_url": site_url,
        "pages": pages,
        "seo": seo,
        "industry": ctx.get("industry", ""),
        "tagline": ctx.get("tagline", ""),
        "description": ctx.get("description", ""),
    }, ensure_ascii=False)

    try:
        supabase.table(T.LINQ_MEMORY).insert({
            "original_prompt": original_prompt,
            "output_summary": output_summary,
            "output_snapshot": output_snapshot,
            "industry": ctx.get("industry", ""),
            "style_tags": ctx.get("style_tags", []),
            "quality_score": 0.8,   # seeded optimistically; updated by acceptance signals
            "was_accepted": True,    # user paid + build completed = accepted
        }).execute()
        logger.info("LinqMemory: stored build record for slug=%s", slug)
    except Exception:
        logger.exception("LinqMemory: failed to store build record for slug=%s", slug)


async def deploy(
    tested: TestArtifact,
    phone_number: str,
    progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> ReleaseArtifact:
    """
    Phase 5: Assemble, deploy, and return the live URL.

    Heartbeats are sent every 70 s during the assembly step so the user knows
    we're still working on the longest single operation in the pipeline.
    """
    # Import here to avoid circular deps with orchestrator helpers
    from ...nano_deploy.waitlist_db import update_waitlist_entry
    from ..orchestrator_agent import _make_unique_slug, make_slug, site_url, _page_build_type

    arch = tested.build.architecture
    ctx = arch.enriched_ctx
    blueprint = arch.design_blueprint
    business_name = arch.requirements.business_name

    # ── Filter out pages that failed validation ──────────────────────────────
    # The testing phase may return pages with passed=False (their JSX still
    # has residual Babel-standalone issues or the QA pipeline raised). Shipping
    # those to assembly tends to break the entire SPA at runtime — better to
    # drop them and ship the site with the remaining passing pages than to
    # crash the build or serve a blank page.
    valid_results = [r for r in tested.results if r.passed]
    dropped = [r.page for r in tested.results if not r.passed]
    if dropped:
        logger.warning(
            "Release: dropping %d page(s) that failed validation for %s: %s",
            len(dropped), business_name, ", ".join(dropped),
        )

    page_jsxes = {r.page: r.jsx for r in valid_results}
    if not page_jsxes:
        raise RuntimeError(
            f"Release: every page failed validation for {business_name} — "
            f"cannot assemble a site. Failed pages: {', '.join(dropped)}"
        )

    # ── Wire inter-page navigation ────────────────────────────────────────────
    wired_jsxes = connect_page_links(page_jsxes, arch.site_plan)

    # Phase header already sent by orchestrator — only speak up here if we had
    # to drop pages the user asked for, since that materially changes the result.
    if dropped and progress_cb:
        await progress_cb(f"had to skip {', '.join(dropped)} — shipping the rest")

    # ── Assemble with (sparse) heartbeats ─────────────────────────────────────
    # Assembly is the single longest step; a couple of short heartbeats reassure
    # the user without spamming the SMS thread with micro-updates.
    async def _heartbeat() -> None:
        for msg in _ASSEMBLY_HEARTBEATS:
            await asyncio.sleep(90)
            if progress_cb:
                await progress_cb(msg)

    heartbeat = asyncio.create_task(_heartbeat())
    try:
        final_html = await assemble_final_site(wired_jsxes, ctx, blueprint)
    finally:
        heartbeat.cancel()

    raise_if_cancelled(phone_number)

    # ── Deploy ────────────────────────────────────────────────────────────────
    # Prefer the slug reserved right after Phase 1 (real company name as subdomain).
    # Fall back to the name-based generator when the RPC was unavailable.
    if arch.requirements.reserved_slug:
        slug = arch.requirements.reserved_slug
        logger.info("Release: using pre-reserved slug=%s for %s", slug, business_name)
    else:
        slug = await _make_unique_slug(make_slug(business_name))
        logger.warning(
            "Release: no pre-reserved slug for %s — fell back to name-based slug=%s",
            business_name, slug,
        )

    # ── Open Graph preview ────────────────────────────────────────────────────
    # Every full build ships with a branded link-preview image so the page
    # doesn't look like a bare URL when shared on iMessage/Slack/Twitter/etc.
    # We render + cache the PNG here (under the final slug) and inject the
    # og:* / twitter:* meta block into the final HTML before it hits the DB.
    from ...og_image import (
        ensure_og_image,
        inject_og_meta_into_html,
        og_image_url as build_og_image_url,
        favicon_url as build_favicon_url,
    )
    og_bytes: bytes = b""
    try:
        og_bytes = await asyncio.to_thread(ensure_og_image, slug, ctx)
        image_url = build_og_image_url(slug)
        fav_url = build_favicon_url(slug)
        title = business_name or "Your site"
        description = (
            ctx.get("tagline")
            or ctx.get("description")
            or ctx.get("problem")
            or f"Built with Nanowork — {title}"
        )
        final_html = inject_og_meta_into_html(
            final_html,
            title=str(title),
            description=str(description),
            image_url=image_url,
            site_url=site_url(slug),
            favicon_url=fav_url,
        )
    except Exception:
        logger.exception("og_image: failed to attach preview for %s — shipping without", slug)

    # ── Inject company-specific SEO metadata ─────────────────────────────────
    # Use pre-generated metadata from Phase 1 when available; otherwise
    # generate it now.  This replaces <title> and name-based meta tags with
    # content that is unique to this exact company, not a generic fallback.
    from ..seo_agent import generate_company_seo_metadata, inject_seo_meta
    seo = arch.requirements.seo_metadata or {}
    if not seo:
        try:
            seo = await generate_company_seo_metadata(
                name=business_name,
                description=ctx.get("description", ""),
                industry=ctx.get("industry", ""),
                tagline=arch.requirements.tagline,
            )
        except Exception:
            logger.exception("Release: SEO metadata generation failed for %s", slug)
    if seo:
        final_html = inject_seo_meta(final_html, seo)

    final_url = site_url(slug)

    import time

    from ...core.brand_assets import generate_favicon as _gen_favicon
    from ...core.deploy import deploy_app
    from ...deployment.github_deploy import GitHubRepoCreateError, GitHubTokenPermissionError, deploy_to_github
    from ...nano_deploy.waitlist_db import get_waitlist_entry

    row = await asyncio.to_thread(get_waitlist_entry, phone_number)
    build_id = str((row or {}).get("build_id") or "")
    _t0 = time.perf_counter()

    bt = _page_build_type(ctx)
    logger.info(
        "DEPLOY[start] flow_type=post_payment slug=%s phone=%s build_id=%s build_type=%s",
        slug,
        phone_number,
        build_id,
        bt,
    )

    github_repo_url: str | None = None

    try:
        github_repo_url = await deploy_to_github(
            business_name=business_name,
            slug=slug,
            html=final_html,
            strict=True,
        )
    except GitHubRepoCreateError as exc:
        elapsed_ms = int((time.perf_counter() - _t0) * 1000)
        if isinstance(exc, GitHubTokenPermissionError):
            outcome = "github_token_permission"
            failure_reason = (
                "GitHub token authenticated but cannot create repositories — "
                "reissue PAT with repo scope or fine-grained Administration: write. "
                + str(exc)[:350]
            )
        else:
            outcome = "github_failed"
            failure_reason = str(exc)[:500]
        logger.exception(
            "DEPLOY post-payment GitHub failed slug=%s outcome=%s business=%s",
            slug,
            outcome,
            business_name,
        )
        await asyncio.to_thread(
            update_waitlist_entry,
            phone_number,
            page_slug=slug,
            page_html=final_html,
            preview_failure_reason=failure_reason,
            preview_status="failed",
            preview_status_updated_at=datetime.now(UTC).isoformat(),
        )
        logger.info(
            "DEPLOY[done] flow_type=post_payment outcome=%s slug=%s url= duration_ms=%s build_type=%s",
            outcome,
            slug,
            elapsed_ms,
            _page_build_type(ctx),
        )
        raise

    _primary = ctx.get("brand_color") or ctx.get("accent_color") or "#6366F1"
    favicon_bytes = await asyncio.to_thread(_gen_favicon, business_name, _primary)
    await deploy_app(slug, build_id, final_html, og_bytes, favicon_bytes)

    context_md_done = render_context_markdown(
        customer_id=phone_number,
        ctx={**ctx, "assembled_pages": list(wired_jsxes.keys())},
        build_stage="complete",
        site_url=final_url,
        github_repo_url=github_repo_url or "",
    )

    await asyncio.to_thread(
        update_waitlist_entry,
        phone_number,
        page_slug=slug,
        page_html=final_html,
        context_json=json.dumps({**ctx, "assembled_pages": list(wired_jsxes.keys())}),
        context_md=context_md_done,
        context_md_updated_at=datetime.now(UTC).isoformat(),
        app_domain=final_url,
        state="complete",
        github_repo_url=github_repo_url or "",
        preview_failure_reason=None,
        preview_status="deployed",
        preview_status_updated_at=datetime.now(UTC).isoformat(),
        build_type=_page_build_type(ctx),
    )

    logger.info(
        "Released %s at slug=%s (%d pages)",
        business_name,
        slug,
        len(wired_jsxes),
    )

    elapsed_ok = int((time.perf_counter() - _t0) * 1000)
    logger.info(
        "DEPLOY[done] flow_type=post_payment outcome=success url=%s duration_ms=%s slug=%s build_type=%s",
        final_url,
        elapsed_ok,
        slug,
        _page_build_type(ctx),
    )

    raise_if_cancelled(phone_number)

    # ── Write to LinqMemory (anti-repetition RAG) ─────────────────────────────
    # Store the full output so future generations for similar prompts retrieve
    # this via the match_linq_memory RPC and avoid producing the same name/design.
    # Fire-and-forget: a failure here must never block the caller getting their URL.
    asyncio.create_task(_store_linq_memory(
        phone_number=phone_number,
        ctx=ctx,
        business_name=business_name,
        slug=slug,
        site_url=final_url,
        pages=list(wired_jsxes.keys()),
        seo=seo,
    ))

    return ReleaseArtifact(
        url=site_url(slug),
        slug=slug,
        pages_deployed=list(wired_jsxes.keys()),
        github_repo_url=github_repo_url,
    )
