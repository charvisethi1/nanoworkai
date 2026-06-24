"""
Nanomarketer — content generation.
Ported from nanoengineer/nanomarketer/generate.py (stateless, no Supabase/Redis).

Public API:
  generate_taglines(brief, n=5)   -> list[str]
  generate_ad_copy(brief, taglines, n=3)  -> list[str]
  generate_pitch_deck(brief)      -> list[dict]
  build_brief(understanding)      -> str   (builds a brief from session.understanding)
"""
from __future__ import annotations

import json
import logging
import os

import anthropic

logger = logging.getLogger(__name__)


def _claude() -> anthropic.Anthropic:
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(api_key=key)


def _model() -> str:
    return os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")


# ---------------------------------------------------------------------------
# Brief builder — converts session.understanding → markdown brief string
# ---------------------------------------------------------------------------

def build_brief(understanding: dict) -> str:
    """
    Build a short requirements brief from session.understanding for use as
    nanomarketer input (equivalent to the requirements.md the Brain generates).
    """
    product   = understanding.get("product") or understanding.get("product_name") or "Untitled Product"
    audience  = understanding.get("audience") or "general users"
    usp       = understanding.get("usp") or ""
    tone      = understanding.get("tone") or "professional"
    features  = understanding.get("features") or []
    pricing   = understanding.get("pricing") or ""
    competitors = understanding.get("competitors") or []

    features_md = "\n".join(f"- {f}" for f in features) if features else "- TBD"
    competitors_md = ", ".join(competitors) if competitors else "none listed"
    pricing_md = pricing or "TBD"

    brief = f"""# {product} — Product Brief

## Overview
{usp or product}

## Target Audience
{audience}

## Tone & Voice
{tone}

## Core Features
{features_md}

## Pricing
{pricing_md}

## Competitors
{competitors_md}
""".strip()

    context_md = understanding.get("context_md") or ""
    context_md = context_md.strip() if isinstance(context_md, str) else ""
    if context_md:
        brief = f"""{brief}

## Full customer context (preview / context.md)

{context_md}
""".strip()

    return brief


# ---------------------------------------------------------------------------
# Taglines
# ---------------------------------------------------------------------------

def generate_taglines(brief: str, n: int = 5) -> list[str]:
    """Return n punchy taglines derived from the product brief."""
    prompt = (
        f"You are a world-class copywriter. Read the product brief below and write "
        f"exactly {n} punchy, memorable taglines (≤ 10 words each). "
        f"Return ONLY a JSON array of strings, no extra text.\n\n"
        f"Brief:\n{brief}"
    )
    msg = _claude().messages.create(
        model=_model(),
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    try:
        taglines = json.loads(raw)
        if isinstance(taglines, list):
            return [str(t) for t in taglines[:n]]
    except json.JSONDecodeError:
        logger.warning("[marketer] taglines JSON parse failed — splitting by newline")
        return [line.strip("- •\"'") for line in raw.splitlines() if line.strip()][:n]
    return []


# ---------------------------------------------------------------------------
# Ad copy
# ---------------------------------------------------------------------------

def generate_ad_copy(brief: str, taglines: list[str], n: int = 3) -> list[str]:
    """Return n ad copy variants (≤ 50 words each) for Google/Meta ads."""
    taglines_str = "\n".join(f"- {t}" for t in taglines)
    prompt = (
        f"You are a performance marketing expert. Using the product brief and taglines below, "
        f"write exactly {n} ad copy variants. Each must be ≤ 50 words, punchy, and end with a "
        f"clear call-to-action. Return ONLY a JSON array of strings, no extra text.\n\n"
        f"Brief:\n{brief}\n\n"
        f"Taglines:\n{taglines_str}"
    )
    msg = _claude().messages.create(
        model=_model(),
        max_tokens=768,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    try:
        variants = json.loads(raw)
        if isinstance(variants, list):
            return [str(v) for v in variants[:n]]
    except json.JSONDecodeError:
        logger.warning("[marketer] ad copy JSON parse failed — splitting by newline")
        return [line.strip() for line in raw.splitlines() if line.strip()][:n]
    return []


# ---------------------------------------------------------------------------
# Pitch deck
# ---------------------------------------------------------------------------

def generate_pitch_deck(brief: str) -> list[dict]:
    """Return a 6-slide pitch deck: [{title, bullets, note?}]."""
    prompt = (
        "You are a startup pitch expert. Using the product brief below, generate a concise "
        "investor pitch deck as a JSON array of slides.\n\n"
        "Include exactly these 6 slides in order: Problem, Solution, Market, Product, Traction, The Ask.\n\n"
        "Each slide must follow this structure:\n"
        '{"title": "slide title", "bullets": ["bullet 1", "bullet 2", ...], "note": "optional speaker note"}\n\n'
        "Rules:\n"
        "- 3–5 bullets per slide, each under 15 words\n"
        "- Be specific and compelling — no generic filler\n"
        "- Respond with ONLY the JSON array, no markdown fences\n\n"
        f"Brief:\n{brief}"
    )
    msg = _claude().messages.create(
        model=_model(),
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip().rstrip("```").strip()
    try:
        slides = json.loads(raw)
        if isinstance(slides, list):
            return slides
    except json.JSONDecodeError:
        logger.warning("[marketer] pitch deck JSON parse failed")
    return []
