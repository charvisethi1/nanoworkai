"""
Phase 1 — Requirements

Formalizes raw user context (collected during CFO/CMO conversations and Q&A)
into a typed RequirementsSpec that drives every downstream phase.

No LLM call needed: this is pure data normalization and derivation.
"""
from __future__ import annotations

import logging
from ..sdlc_artifacts import RequirementsSpec
from ..page_stitcher_agent import describe_page_spec
from ...assembly.page_build_taxonomy import DEFAULT_PAGE_BUILD_TYPE

logger = logging.getLogger(__name__)


async def gather_requirements(ctx: dict, pages: list[str]) -> RequirementsSpec:
    """
    Phase 1: Derive a RequirementsSpec from the accumulated user context.

    Functional requirements are derived from:
      - Requested pages (each page = a functional requirement)
      - Pricing model / details (from CFO conversation)
      - Ad/analytics flags (from CMO conversation)
    """
    functional_requirements: list[str] = []

    for page in pages:
        spec_text = describe_page_spec(ctx, page)
        functional_requirements.append(f"[{page.upper()}] {spec_text}")

    pricing_model = ctx.get("pricing_model", "")
    if pricing_model:
        details = ctx.get("pricing_details", "")
        functional_requirements.append(
            f"[PRICING] {pricing_model} model" + (f" — {details}" if details else "")
        )

    # === DISABLED: ads-driven analytics/wallet requirement (CMO flow paused) ==
    # if ctx.get("ads_opted_in"):
    #     functional_requirements.append("[ANALYTICS] Ad campaign performance dashboard")
    #     functional_requirements.append("[WALLET] Ad spend balance and transaction history")
    # === END DISABLED ==========================================================

    # === DISABLED: pitch-deck requirement (pitch-deck generation paused) =======
    # if ctx.get("pitch_deck_slug"):
    #     functional_requirements.append("[PITCH DECK] Investor pitch deck (already generated)")
    # === END DISABLED ==========================================================

    spec = RequirementsSpec(
        business_name=ctx.get("business_name", ctx.get("tool_name", "Product")),
        tagline=ctx.get("tagline", ""),
        problem=ctx.get("problem", ""),
        solution=ctx.get("solution", ""),
        audience=ctx.get("audience", ""),
        differentiator=ctx.get("differentiator", ""),
        tone=ctx.get("tone", "professional"),
        build_type=ctx.get("build_type", DEFAULT_PAGE_BUILD_TYPE),
        pages=pages,
        pricing_model=pricing_model,
        pricing_details=ctx.get("pricing_details", ""),
        functional_requirements=functional_requirements,
        ctx=ctx,
    )

    logger.info(
        "Requirements gathered for %s: %d pages, %d functional requirements",
        spec.business_name, len(pages), len(functional_requirements),
    )
    return spec
