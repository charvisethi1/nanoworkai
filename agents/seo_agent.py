"""
SEO agent — optimizes websites for high ranking in both traditional search engines (Google, Bing, etc.)
and LLM-based internet indexes (e.g., ChatGPT Browsing & Bing Copilot / Google SGE / Perplexity).
Ensures generated business landing pages are indexable, discoverable, and primed for both algorithmic
and AI-driven discovery. Recommends SEO improvements and injects critical metadata, content structure,
and prompts for new LLM paradigms.
"""

from __future__ import annotations
import json
import logging
import re
from typing import Dict, List, Optional

from ..llm_client import chat
from ..services import send_linq_message

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Company-specific SEO metadata (called after slug reservation, Phase 1+)
# ---------------------------------------------------------------------------

_SEO_META_SYSTEM = (
    "You are a senior SEO copywriter. Return only valid JSON with no commentary. "
    "Every field must be unique to this specific company — no generic placeholders."
)


async def generate_company_seo_metadata(
    name: str,
    description: str,
    industry: str,
    tagline: str,
) -> dict:
    """
    Generate company-specific SEO meta tags via a focused Claude call.

    Returns a dict with keys: meta_title, meta_description, meta_keywords.
    Falls back to deterministic values derived from the inputs so a failed
    LLM call never blocks the build pipeline.
    """
    prompt = (
        f"Given this company:\n"
        f"Name: {name}\n"
        f"Description: {description}\n"
        f"Industry: {industry}\n"
        f"Tagline: {tagline}\n\n"
        'Return JSON only:\n'
        '{\n'
        '  "meta_title": "under 60 chars, includes company name",\n'
        '  "meta_description": "under 155 chars, unique value prop",\n'
        '  "meta_keywords": ["5", "specific", "keywords", "no", "generics"]\n'
        '}'
    )
    try:
        raw = await chat(
            [{"role": "user", "content": prompt}],
            system=_SEO_META_SYSTEM,
            max_tokens=200,
        )
        # Strip any accidental markdown fences
        raw = re.sub(r"^```[a-z]*\n?", "", raw.strip(), flags=re.MULTILINE).rstrip("` \n")
        meta = json.loads(raw)
        # Enforce length limits defensively
        meta["meta_title"] = str(meta.get("meta_title", name))[:60]
        meta["meta_description"] = str(meta.get("meta_description", tagline or description))[:155]
        if not isinstance(meta.get("meta_keywords"), list):
            meta["meta_keywords"] = []
        return meta
    except Exception:
        logger.exception("generate_company_seo_metadata: LLM/parse failed for %s — using fallback", name)
        return {
            "meta_title": f"{name} — {tagline}"[:60] if tagline else name[:60],
            "meta_description": (description or tagline or f"{name} — built with Linq")[:155],
            "meta_keywords": [w for w in [industry, name.lower().replace(" ", "-")] if w],
        }


def inject_seo_meta(html: str, seo: dict) -> str:
    """
    Inject <title> and <meta name="description"/"keywords"> into *html*.

    Replaces any existing tags so the SEO metadata is always unique to this
    company; never rewrites og:* tags (those are handled by inject_og_meta).
    Safe no-op if <head> is not found.
    """
    title = seo.get("meta_title", "")
    description = seo.get("meta_description", "")
    keywords = seo.get("meta_keywords", [])

    if "<head" not in html.lower():
        return html

    block = ""
    if title:
        html = re.sub(r"<title>[^<]*</title>", "", html, flags=re.IGNORECASE)
        block += f'  <title>{title}</title>\n'
    if description:
        html = re.sub(r'<meta\s+name=["\']description["\'][^>]*>', "", html, flags=re.IGNORECASE)
        html = re.sub(r'<meta\s+content=["\'][^"\']*["\']\s+name=["\']description["\'][^>]*>', "", html, flags=re.IGNORECASE)
        block += f'  <meta name="description" content="{description}">\n'
    if keywords:
        kw_str = ", ".join(keywords)
        html = re.sub(r'<meta\s+name=["\']keywords["\'][^>]*>', "", html, flags=re.IGNORECASE)
        block += f'  <meta name="keywords" content="{kw_str}">\n'

    if block:
        html = re.sub(r"(<head[^>]*>)", r"\1\n" + block, html, count=1, flags=re.IGNORECASE)

    return html

SEO_SYSTEM_PROMPT = (
    "You are an expert AI SEO agent tasked with optimizing a business website for maximum discoverability. "
    "Your goal: make the site rank high on both classic search engines (Google, Bing) AND through large language models "
    "like ChatGPT, Bing Copilot, Google SGE, and Perplexity that use internet indexes. "
    "Ensure best practices in structure, content, and modern SEO metadata (incl. structured data, OpenGraph, "
    "LLM-friendly summaries, FAQ, and clear language about the business). "
    "Output all recommendations as actionable checklists and summary copy for the business owner, ready for direct use."
)

def _seo_base_metadata(
    business_name: str,
    description: str,
    keywords: Optional[List[str]] = None,
    url: Optional[str] = None,
    social_image: Optional[str] = None,
) -> Dict[str, str]:
    """Returns a dictionary of basic SEO meta tags."""
    tags = {
        "title": business_name,
        "description": description,
        "og:title": business_name,
        "og:description": description,
        "twitter:card": "summary_large_image" if social_image else "summary",
    }
    if keywords:
        tags["keywords"] = ", ".join(keywords)
    if url:
        tags["og:url"] = url
    if social_image:
        tags["og:image"] = social_image
        tags["twitter:image"] = social_image
    return tags

async def gen_seo_recommendations(entry: dict) -> dict:
    """
    Generates a set of actionable SEO recommendations for the business landing page.
    Covers both classic SEO and new LLM-index best practices.
    """
    business_name = entry.get("business_name", "")
    description = entry.get("description", "")
    core_keywords = entry.get("seo_keywords", [])
    url = entry.get("url", "")
    img = entry.get("social_image", "")

    prompt = (
        f"You are an expert SEO agent.\n"
        f"Business Name: {business_name}\n"
        f"Description: {description}\n"
        f"Website: {url}\n"
        f"Target Keywords: {', '.join(core_keywords) if core_keywords else 'N/A'}\n\n"
        "Provide:\n"
        "1. A list of 5-10 optimized title/headline options for the landing page.\n"
        "2. A list of recommended meta title and meta description pairs.\n"
        "3. The ideal FAQ (2-5 questions/answers) to embed as schema.org markup.\n"
        "4. LLM/Palm/GPT-optimized site summary (2-3 crisp sentences for AI agents to index).\n"
        "5. Any additional tips for performance, accessibility, and crawlability.\n"
        "Respond as a Python dict with keys: 'titles', 'meta', 'faq', 'llm_summary', 'tips'."
    )

    try:
        messages = [
            {"role": "system", "content": SEO_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        response = await chat(messages)
        # Try parsing the response as a dict (LLM should return a Python dict as string).
        result = eval(response, {"__builtins__": {}})
        assert isinstance(result, dict), "LLM response not a dict"
        return result
    except Exception as e:
        logger.warning("SEO agent failed to parse LLM response: %r\nResponse:\n%s", e, response)
        return {}

async def send_seo_summary(entry: dict, phone: str) -> None:
    """
    Generates and sends a summary of SEO recommendations to the business owner via SMS or Linq.
    """
    recs = await gen_seo_recommendations(entry)
    if not recs:
        await send_linq_message(phone, "SEO agent could not generate recommendations. Try again or contact support.")
        return

    summary = "SEO Audit Complete:\n"

    if titles := recs.get("titles"):
        summary += "\nTitle ideas:\n" + "\n".join(f"- {t}" for t in titles[:3])

    if meta := recs.get("meta"):
        summary += "\n\nMeta options:\n"
        for m in meta[:2]:
            mt, md = m.get("title", ""), m.get("description", "")
            summary += f"- Title: {mt}\n  Desc: {md}\n"

    if llm_sum := recs.get("llm_summary"):
        summary += f"\nLLM/GPT summary:\n{llm_sum}\n"
    
    if tips := recs.get("tips"):
        summary += "\nQuick tips:\n" + ("\n".join(f"- {t}" for t in tips) if isinstance(tips, list) else str(tips))
    
    await send_linq_message(phone, summary.strip())

# Agent entrypoint for nanowork pipeline
async def maybe_run_seo_agent(entry: dict, phone: str) -> None:
    """
    Entry point to automatically trigger SEO checkup after a new landing page is built or updated.
    """
    logger.info("[seo_agent] Running SEO agent for %r", entry.get("business_name", entry.get("slug", "")))
    await send_seo_summary(entry, phone)