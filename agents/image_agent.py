"""
Image agent — brand visual generator powered by Nano Banana Pro
(Google's Gemini 3 Pro Image, model id `gemini-3-pro-image-preview`).

Why this exists
---------------
Every nanowork build used to render on top of pure Tailwind shapes. That made
sites look tidy but interchangeable — the same gradient hero, the same flat
cards, the same rounded buttons across products that should feel nothing alike.
This agent produces ONE high-fidelity hero image + ONE small logo mark per
build, keyed off the business's name, problem, solution, audience, and tone.
The design agent uploads those PNGs to Supabase Storage and passes HTTPS URLs
into the page shell — the browser loads pixels from storage instead of inlined
base64.

Design goals
------------
1. **Fail open**: if `GEMINI_API_KEY` is unset, or the Gemini call fails for
   any reason, we return `(None, None)` and the rest of the pipeline continues
   with its existing Tailwind-only rendering. No site should ever 500 because
   the image model is down.
2. **Fast & cheap**: at most two calls per build (hero + logo), both with
   short prompts. Each call has a hard `asyncio.wait_for` timeout so a slow
   Gemini response can't stall the whole build.
3. **Deterministic wiring**: Gemini output is converted to data URIs on
   :class:`BrandImagery` for the brief upload step; :func:`design_agent.create_site_blueprint`
   persists PNGs to Supabase Storage and exposes ``hero_image_url`` /
   ``logo_image_url`` on the merged ctx.

The strings on :class:`BrandImagery` are full `data:image/png;base64,...` URIs used
only until storage upload succeeds; they are not embedded in shipped HTML.
"""
from __future__ import annotations

import os
import base64
import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Public name of the Nano Banana Pro model. We isolate it here so it's easy to
# upgrade when Google ships the next revision.
NANO_BANANA_PRO_MODEL = os.getenv("NANO_BANANA_PRO_MODEL", "gemini-3-pro-image-preview")

# Per-image hard timeout. Nano Banana Pro typically returns in ~6-15s; 60s is
# well past that and still short enough that a stalled call doesn't block a
# build. Gemini-side failures usually surface much earlier as HTTP errors.
_IMAGE_TIMEOUT_S = float(os.getenv("NANO_BANANA_PRO_TIMEOUT_S", "60"))


# ---------------------------------------------------------------------------
# Public return type
# ---------------------------------------------------------------------------

@dataclass
class BrandImagery:
    """
    Output of a single `generate_brand_imagery` call.
    Both fields are optional — when the image model is unavailable, they are
    simply None and the caller uses its existing visual fallbacks.
    """
    hero_data_url: Optional[str] = None
    logo_data_url: Optional[str] = None
    skipped_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _hero_prompt(ctx: dict, design_style: str, brand_color: str) -> str:
    """
    Builds a Nano Banana Pro prompt for a hero/feature image that embodies the
    brand. We stay away from literal UI screenshots — those age fast and tend
    to fight with the Tailwind layout. Instead we aim for evocative,
    magazine-quality imagery that communicates tone without competing with the
    copy overlaid on top of it.
    """
    name = ctx.get("business_name") or ctx.get("tool_name") or "a new startup"
    problem = (ctx.get("problem") or "").strip()
    solution = (ctx.get("solution") or "").strip()
    audience = (ctx.get("audience") or "").strip()
    tone = (ctx.get("tone") or "professional").strip()

    style_direction = {
        "editorial": (
            "Editorial magazine photography. Soft natural light, film grain, "
            "muted earth palette with one precise pop of the brand color. "
            "High composition, lots of negative space, shallow depth of field."
        ),
        "minimal": (
            "Minimalist fine-art still life. Off-white studio background, one "
            "sculptural object or abstract form, a single accent in the brand "
            "color. Clean, calm, Scandinavian aesthetic."
        ),
        "bold": (
            "Bold, cinematic hero image. Dark moody backdrop, dramatic rim "
            "lighting, heavy contrast. Saturated accents in the brand color. "
            "Feels like a movie poster, not a stock photo."
        ),
        "soft": (
            "Warm, friendly lifestyle photograph. Pastel palette, sunlight "
            "through a window, soft shadows. Brand color woven in as a fabric, "
            "ceramic, or background tint. Inviting, human, approachable."
        ),
        "technical": (
            "Technical, high-tech macro photograph. Dark surface, cool rim "
            "light, subtle cyan/teal grid projections, a hint of the brand "
            "color as glowing accent lines. Feels like a precision instrument."
        ),
        "luxury": (
            "Luxury still-life photograph. Deep black velvet or dark marble "
            "backdrop, warm gold rim light, a single refined object centered. "
            "Brand color appears as a metallic sheen or thin inlay."
        ),
    }.get(design_style, "Premium editorial photograph, clean composition, balanced negative space.")

    return (
        "Create a premium hero image for a startup marketing website. "
        "This image will be overlaid with bold white or near-black headline "
        "text, so KEEP THE COMPOSITION simple: most of the frame should be "
        "quiet, with the focal subject to one side, leaving ample room for "
        "typography. Do NOT render any text, letters, numbers, logos, UI, "
        "app screenshots, or watermarks in the image.\n\n"
        f"Brand: {name}\n"
        f"What they do: {solution or 'helps customers solve a real problem'}\n"
        f"Problem they solve: {problem or 'everyday friction for their audience'}\n"
        f"Audience: {audience or 'modern professionals'}\n"
        f"Tone: {tone}\n"
        f"Brand accent color: {brand_color}\n\n"
        f"Visual direction: {style_direction}\n\n"
        "Deliver ONE photographic, magazine-grade image. No collage, no "
        "multi-panel compositions, no text, no embedded interfaces."
    )


def _logo_prompt(ctx: dict, design_style: str, brand_color: str) -> str:
    """
    Prompt for a small, square logomark. We ask for something abstract and
    geometric that will read well at 32-40px (where most nav bars render it).
    No letters — the nav template always pairs the mark with the wordmark
    rendered in the site's heading font.
    """
    name = ctx.get("business_name") or ctx.get("tool_name") or "a new startup"

    mark_shape = {
        "editorial": "a single elegant serif-inspired abstract mark",
        "minimal":   "a minimal geometric monogram shape, single hairline stroke",
        "bold":      "a chunky geometric mark with thick strokes and one offset shape",
        "soft":      "a soft rounded blob mark with a warm highlight",
        "technical": "a precise grid-aligned mark with a subtle dot/line motif",
        "luxury":    "a refined serif-informed mark with a thin metallic accent",
    }.get(design_style, "a simple geometric mark")

    return (
        "Create a tiny, pixel-crisp logomark for a startup's app icon. "
        "Square format. Subject centered. The mark MUST work at 40x40 pixels — "
        "absolutely no fine detail, no gradients smaller than a few pixels, "
        "no photography. Solid flat vector-style shapes only. "
        "Do NOT include any text, letters, numbers, taglines, or watermarks. "
        "Transparent or single-color background.\n\n"
        f"Business: {name}\n"
        f"Brand accent color (use as primary color of the mark): {brand_color}\n"
        f"Direction: {mark_shape}. No text, no words, no letterforms."
    )


# ---------------------------------------------------------------------------
# Nano Banana Pro call
# ---------------------------------------------------------------------------

def _have_api_key() -> bool:
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


def _sync_generate_png(prompt: str, aspect_ratio: str) -> Optional[bytes]:
    """
    Sync helper that does the actual google-genai call. Returns PNG bytes on
    success, None on any failure. Runs inside `asyncio.to_thread` so the event
    loop isn't blocked by the SDK's synchronous networking.
    """
    try:
        # Imported inside the function so that a) the module imports cleanly
        # in environments without google-genai installed (tests, local dev),
        # and b) the dependency is only pulled in when we actually use it.
        from google import genai
        from google.genai import types
    except Exception as exc:
        logger.warning("image_agent: google-genai not installed: %s", exc)
        return None

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=NANO_BANANA_PRO_MODEL,
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_modalities=["Image"],
                image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
            ),
        )
    except Exception as exc:
        logger.warning("image_agent: Nano Banana Pro call failed (%s): %s", NANO_BANANA_PRO_MODEL, exc)
        return None

    # Extract the first image part. The SDK returns a variety of shapes across
    # versions, so we probe defensively — any shape that yields raw bytes is
    # acceptable.
    try:
        candidates = getattr(response, "candidates", None) or []
        for cand in candidates:
            content = getattr(cand, "content", None)
            parts = getattr(content, "parts", None) or []
            for part in parts:
                inline = getattr(part, "inline_data", None)
                if inline is None:
                    continue
                data = getattr(inline, "data", None)
                if not data:
                    continue
                if isinstance(data, (bytes, bytearray)):
                    return bytes(data)
                if isinstance(data, str):
                    # Some SDK versions return base64 strings rather than raw bytes.
                    try:
                        return base64.b64decode(data)
                    except Exception:
                        continue
    except Exception as exc:
        logger.warning("image_agent: failed to extract image bytes: %s", exc)
        return None

    logger.info("image_agent: Nano Banana Pro returned no inline image data")
    return None


async def _generate_png_async(
    prompt: str,
    aspect_ratio: str,
    *,
    timeout_s: Optional[float] = None,
) -> Optional[bytes]:
    """Async wrapper with a hard per-call timeout."""
    limit = timeout_s if timeout_s is not None else _IMAGE_TIMEOUT_S
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_sync_generate_png, prompt, aspect_ratio),
            timeout=limit,
        )
    except asyncio.TimeoutError:
        logger.warning("image_agent: Nano Banana Pro timed out after %ss", limit)
        return None


def _png_to_data_url(png: bytes) -> str:
    b64 = base64.b64encode(png).decode("ascii")
    return f"data:image/png;base64,{b64}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def generate_brand_imagery(
    ctx: dict,
    design_style: str,
    brand_color: str,
    *,
    include_hero: bool = True,
    include_logo: bool = True,
    per_image_timeout_s: Optional[float] = None,
) -> BrandImagery:
    """
    Generate a hero image and a logomark for this build.

    Runs the two Nano Banana Pro calls concurrently — they're independent and
    both take several seconds, so sequential execution would noticeably slow
    the preview. Either or both can be skipped with the `include_*` kwargs
    (tests disable both; the assembled build path may want the hero only).
    ``per_image_timeout_s`` caps each call (defaults to ``NANO_BANANA_PRO_TIMEOUT_S``
    / 60s). Previews pass a lower value so a slow image model does not block the
    critical path for multiple minutes.

    Never raises. Missing API key, SDK failure, or per-call timeout each
    translate to `hero_data_url=None` / `logo_data_url=None` + a
    `skipped_reason` so the caller can log the outcome.
    """
    if not _have_api_key():
        return BrandImagery(skipped_reason="no_gemini_api_key")

    tasks: list = []
    kinds: list[str] = []
    if include_hero:
        tasks.append(
            _generate_png_async(
                _hero_prompt(ctx, design_style, brand_color),
                "16:9",
                timeout_s=per_image_timeout_s,
            )
        )
        kinds.append("hero")
    if include_logo:
        tasks.append(
            _generate_png_async(
                _logo_prompt(ctx, design_style, brand_color),
                "1:1",
                timeout_s=per_image_timeout_s,
            )
        )
        kinds.append("logo")

    if not tasks:
        return BrandImagery(skipped_reason="nothing_requested")

    results = await asyncio.gather(*tasks, return_exceptions=True)

    hero_bytes: Optional[bytes] = None
    logo_bytes: Optional[bytes] = None
    for kind, result in zip(kinds, results):
        if isinstance(result, BaseException):
            logger.warning("image_agent: %s generation raised: %s", kind, result)
            continue
        if kind == "hero":
            hero_bytes = result
        elif kind == "logo":
            logo_bytes = result

    imagery = BrandImagery()
    if hero_bytes:
        imagery.hero_data_url = _png_to_data_url(hero_bytes)
    if logo_bytes:
        imagery.logo_data_url = _png_to_data_url(logo_bytes)

    if not imagery.hero_data_url and not imagery.logo_data_url:
        imagery.skipped_reason = "all_generations_failed"

    logger.info(
        "image_agent: generated hero=%s logo=%s (skipped_reason=%s)",
        bool(imagery.hero_data_url),
        bool(imagery.logo_data_url),
        imagery.skipped_reason,
    )
    return imagery
