"""
Builder agent — ported from nanoengineer/builder.py.

Generates a complete React + Tailwind landing page via Claude.
No Supabase / Redis / Amplify dependencies — purely stateless.

Input:  SiteContext (product brief from prior_agent_output)
Output: dict[str, str]  { filepath: file_content }
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field

import anthropic

logger = logging.getLogger(__name__)

_CLAUDE_MODEL_DEFAULT = "claude-sonnet-4-6"


def _get_claude() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(api_key=api_key)


def _claude_model() -> str:
    return os.getenv("CLAUDE_MODEL", _CLAUDE_MODEL_DEFAULT)


# ---------------------------------------------------------------------------
# Mood presets (kept identical to nanoengineer so output is consistent)
# ---------------------------------------------------------------------------
MOOD_PRESETS: dict[str, str] = {
    "editorial": (
        "Magazine-style: large serif headlines, generous whitespace, asymmetric layouts. "
        "Think New Yorker. Typography: Playfair Display or Lora for headings, Source Sans for body. "
        "Rich, confident."
    ),
    "saas": (
        "Product-led: clean grids, soft gradients, rounded corners, trust badges. "
        "Think Linear, Vercel, Stripe. Light backgrounds, blue/indigo accents. "
        "Typography: Inter or Geist."
    ),
    "brutalist": (
        "Raw and bold: monospace, heavy contrast, no-frills. Black and white or high-contrast accent. "
        "Typography: IBM Plex Mono or Space Mono. Flat blocks, no gradients."
    ),
    "playful": (
        "Friendly: rounded shapes, warm colors, soft shadows. Think Notion, Figma. "
        "Pastels or warm accent. Typography: Nunito or Poppins."
    ),
    "luxury": (
        "Premium: refined spacing, gold/black accents, elegant serifs. "
        "Typography: Cormorant or Cinzel. Dark or cream backgrounds."
    ),
    "minimal": (
        "Reduced to essentials: lots of whitespace, single accent, thin lines. "
        "Think Apple. Typography: Outfit or Sora. One strong CTA."
    ),
}


def _mood_instruction(mood: list[str] | None) -> str:
    if not mood:
        return ""
    parts = [MOOD_PRESETS.get(m.lower(), m) for m in mood if m]
    if not parts:
        return ""
    return (
        "\n\nDESIGN MOOD (apply this visual style strictly):\n"
        + "\n".join(f"- {p}" for p in parts)
    )


# ---------------------------------------------------------------------------
# Context dataclass (lightweight — no Pydantic needed here)
# ---------------------------------------------------------------------------
@dataclass
class SiteContext:
    job_id: str
    product: str
    audience: str
    usp: str
    tone: str
    taglines: list[str] = field(default_factory=list)
    mood: list[str] | None = None
    tenant_id: str = ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def generate_site(ctx: SiteContext) -> dict[str, str]:
    """
    Generate the full React site bundle.

    Returns a file-tree dict ready to be committed to GitHub:
      { "src/App.jsx": "...", "index.html": "...", "package.json": "...", ... }
    """
    logger.info(
        "[builder] generating  job_id=%s  product=%r", ctx.job_id, ctx.product
    )
    hero = await _generate_hero_text(ctx)
    files = await _generate_react_site(ctx, hero)
    logger.info(
        "[builder] done  job_id=%s  files=%s", ctx.job_id, list(files.keys())
    )
    return files


# ---------------------------------------------------------------------------
# Step 1 — hero text
# ---------------------------------------------------------------------------
async def _generate_hero_text(ctx: SiteContext) -> dict:
    prompt = f"""You are a conversion copywriter building a product landing page.

Product description: {ctx.product}
Audience: {ctx.audience}
USP: {ctx.usp}
Tone: {ctx.tone}
Taglines to draw from: {json.dumps(ctx.taglines)}

Generate hero section copy:
- "product_name": a short, memorable brand name for this product (1-3 words, no generic words like "App" or "Pro")
- "headline": one punchy line, max 8 words, use or riff on the taglines
- "subheadline": one sentence expanding on the USP, max 20 words
- "cta": call-to-action button text — punchy, specific to the core action this product enables, feels exciting to click (e.g. for a pitch trainer: "Nail your next pitch", for an invoicing tool: "Get paid today", for a fitness app: "Start your transformation") — complete grammatical English, no dropped prepositions

Respond with ONLY a JSON object with keys: product_name, headline, subheadline, cta.
{_mood_instruction(ctx.mood)}"""

    client = _get_claude()
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: client.messages.create(
            model=_claude_model(),
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        ),
    )
    raw = _strip_fences(response.content[0].text)
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Step 2 — full React site (single-file, Tailwind)
# ---------------------------------------------------------------------------
async def _generate_react_site(ctx: SiteContext, hero: dict) -> dict[str, str]:
    prompt = f"""You are an expert React developer building a product landing page.

Product name: {hero.get('product_name', ctx.product)}
Product description: {ctx.product}
Audience: {ctx.audience}
USP: {ctx.usp}
Tone: {ctx.tone}
Hero headline: {hero.get('headline')}
Hero subheadline: {hero.get('subheadline')}
CTA text: {hero.get('cta')}

Generate a single-file React landing page. All sections (Hero, 3 Features, 2 Testimonials, Footer) must be in ONE file: "src/App.jsx".
Use Tailwind CSS classes only. Keep each section concise — no lengthy comments or repetition.

Also include these minimal config files:
- "index.html": standard Vite HTML entry (short)
- "package.json": minimal — only name, version, scripts (dev/build), and dependencies (react, react-dom, vite, @vitejs/plugin-react, tailwindcss, autoprefixer, postcss)
- "vite.config.js": minimal Vite + React plugin config (5 lines max)
- "tailwind.config.js": minimal config with content glob for src (5 lines max)
- "vercel.json": {{"version": 2}}

Rules:
- src/App.jsx must be one default export with all sections inlined as functions
- Use the exact headline, subheadline and CTA provided
- No placeholder text — use the actual product name everywhere
- Keep code concise — avoid long inline strings or comments
- Import fonts from Google Fonts to match the chosen mood (e.g. Playfair Display for editorial, Inter for saas)

Respond with ONLY a JSON object: keys are filepaths, values are file contents. No markdown fences, no explanation.
{_mood_instruction(ctx.mood)}"""

    client = _get_claude()
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: client.messages.create(
            model=_claude_model(),
            max_tokens=16000,
            messages=[{"role": "user", "content": prompt}],
        ),
    )
    raw = _strip_fences(response.content[0].text)
    try:
        files = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Claude returned invalid JSON for site files: {e}") from e

    if not isinstance(files, dict) or "src/App.jsx" not in files:
        raise RuntimeError(
            f"Site bundle missing expected files: {list(files.keys())}"
        )

    # Always include vercel.json
    files.setdefault("vercel.json", '{"version":2}')
    return files


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()
