"""
Design agent — applies shared visual defaults to ctx before pages are built.

The previous LLM-generated "site blueprint" path (competitor research + JSON
design spec) has been removed. We now derive nav/footer variants, palette, and
layout defaults deterministically from the business context, then optionally
attach hero/logo imagery via :func:`generate_brand_imagery` and Supabase Storage.

Output is still a dict with the keys page builders and assembly expect
(``design_style``, ``brand_color``, ``nav_variant``, etc.).
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid

from ..nano_deploy.brand_imagery_storage import (
    png_bytes_from_data_url,
    upload_brand_png,
)
from .image_agent import BrandImagery, generate_brand_imagery
from .ui_components import choose_footer_variant, choose_nav_variant

logger = logging.getLogger(__name__)

_VALID_STYLES = frozenset({"editorial", "minimal", "bold", "soft", "technical", "luxury"})
_VALID_HEROES = frozenset({"centered", "split-left", "split-right", "statement", "cinematic"})


def _preview_per_image_timeout_s() -> float | None:
    """Cap Gemini image latency on the pre-payment preview path (seconds per image).

    Reads ``PREVIEW_BRAND_IMAGE_TIMEOUT_S`` — default ``28`` when unset.
    Set to ``0`` / ``off`` / ``false`` to use the full global ``NANO_BANANA_PRO_TIMEOUT_S``.
    """
    raw = os.getenv("PREVIEW_BRAND_IMAGE_TIMEOUT_S", "28").strip().lower()
    if raw in ("", "0", "off", "false", "no"):
        return None
    try:
        return float(raw)
    except ValueError:
        return 28.0


def _storage_object_prefix(ctx: dict) -> str:
    for key in ("slug", "build_id", "customer_id"):
        v = ctx.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    return uuid.uuid4().hex


async def _persist_imagery_urls(ctx: dict, imagery: BrandImagery) -> dict[str, str]:
    """
    Upload Gemini PNGs to Supabase Storage; return ``hero_image_url`` /
    ``logo_image_url`` entries for the blueprint (never base64 data URIs).

    Hero and logo uploads run concurrently to avoid doubling network latency.
    """
    prefix = _storage_object_prefix(ctx)

    async def _one(key: str, filename: str, data_url: str | None) -> tuple[str, str | None]:
        if not data_url:
            return key, None
        raw = png_bytes_from_data_url(data_url)
        if not raw:
            return key, None
        url = await asyncio.to_thread(upload_brand_png, prefix, filename, raw)
        return key, url

    pairs = await asyncio.gather(
        _one("hero_image_url", "hero.png", imagery.hero_data_url),
        _one("logo_image_url", "logo.png", imagery.logo_data_url),
    )
    return {k: v for k, v in pairs if v}


def _fallback_blueprint(ctx: dict) -> dict:
    """Deterministic design tokens from context (no LLM)."""
    import random

    name = ctx.get("business_name") or ctx.get("tool_name") or "nanowork"

    # Dynamic style selection based on product personality
    build_type = ctx.get("build_type", "")
    flow_kind = ctx.get("flow_kind", "")
    audience = ctx.get("audience", "").lower()
    description = (ctx.get("description") or ctx.get("build_idea", "")).lower()

    # Pick style based on product personality
    if any(w in description for w in ["luxury", "premium", "exclusive", "high-end", "wedding", "jewelry"]):
        default_style = "luxury"
    elif any(w in description for w in ["developer", "api", "code", "technical", "devops", "engineer", "cli"]):
        default_style = "technical"
    elif any(w in description for w in ["kids", "family", "fun", "playful", "pet", "baby", "creative"]):
        default_style = "soft"
    elif any(w in description for w in ["magazine", "blog", "news", "editorial", "media", "publication"]):
        default_style = "editorial"
    elif any(w in description for w in ["startup", "saas", "platform", "enterprise", "b2b"]):
        default_style = "minimal"
    else:
        default_style = random.choice(["bold", "minimal", "editorial", "soft", "technical"])

    style = ctx.get("design_style") or default_style
    if style not in _VALID_STYLES:
        style = default_style

    hero = ctx.get("hero_layout") or "cinematic"
    if hero not in _VALID_HEROES:
        hero = "cinematic"
    color = ctx.get("brand_color", "") or "#6366F1"
    color = str(color).strip()
    if not color.startswith("#"):
        color = f"#{color}" if color else "#6366F1"
    return {
        "design_style": style,
        "brand_color": color,
        "hero_layout": hero,
        "tone": ctx.get("tone", "professional"),
        "nav_items": ctx.get("nav_items")
        if isinstance(ctx.get("nav_items"), list) and ctx.get("nav_items")
        else ["Home", "Features", "Pricing", "About", "Contact"],
        "section_emphasis": ctx.get("section_emphasis") or "conversion",
        "competitor_insights": "",
        "design_rationale": ctx.get("design_rationale")
        or "Theme derived from your brief — conversion-focused layout.",
        "nav_variant": choose_nav_variant(name, style),
        "footer_variant": choose_footer_variant(name, style),
    }


async def create_site_blueprint(ctx: dict, *, preview_build: bool = False) -> dict:
    """
    Builds the design dict merged into ctx for previews and full-site builds.

    Starts from :func:`_fallback_blueprint`, then best-effort brand imagery
    (Gemini when configured). Never raises from image generation failures.

    When ``preview_build=True``, each Gemini image call uses a tighter timeout
    (see :func:`_preview_per_image_timeout_s`) so previews do not sit on the
    critical path for minutes when the image API is slow.
    """
    business_name = ctx.get("business_name", ctx.get("tool_name", "Product"))
    blueprint = _fallback_blueprint(ctx)

    try:
        img_timeout = _preview_per_image_timeout_s() if preview_build else None
        imagery = await generate_brand_imagery(
            {**ctx, "business_name": business_name},
            design_style=blueprint.get("design_style", "minimal"),
            brand_color=blueprint.get("brand_color", "#6366F1"),
            per_image_timeout_s=img_timeout,
        )
        urls = await _persist_imagery_urls(ctx, imagery)
        blueprint.update(urls)
        if imagery.skipped_reason:
            blueprint["brand_imagery_skipped_reason"] = imagery.skipped_reason
        logger.info(
            "Brand imagery for %s: hero_url=%s logo_url=%s reason=%s",
            business_name,
            bool(urls.get("hero_image_url")),
            bool(urls.get("logo_image_url")),
            imagery.skipped_reason,
        )
    except Exception:
        logger.exception(
            "Brand imagery generation failed for %s — continuing without images",
            business_name,
        )

    return blueprint
