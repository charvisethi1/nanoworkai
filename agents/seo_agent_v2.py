"""
SEO Agent v2 — Actually optimizes websites for search engines and LLM indexes.

Performs 4 key optimizations:
  1. Meta tags (title, description, keywords, OG/Twitter cards)
  2. Structured data (JSON-LD schema.org markup)
  3. Sitemap generation (sitemap.xml for multi-page sites)
  4. Content optimization (keyword targeting, readability)

Integrated with multi-agent orchestration framework.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional
from datetime import datetime

from ..infrastructure.llm_client import chat
from ..core.agents.orchestration import AgentArtifact, AgentOrchestrator, register_agent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. META TAG OPTIMIZATION
# ---------------------------------------------------------------------------

_META_SYSTEM = (
    "You are an expert SEO copywriter. Generate meta tags that maximize click-through "
    "rates from Google/Bing search results AND visibility in LLM-based tools like "
    "ChatGPT, Perplexity, and Google SGE. Return only valid JSON with no commentary."
)


async def optimize_meta_tags(ctx: dict) -> dict:
    """
    Generate optimized meta tags for a page.

    Returns:
        {
            "title": "...",
            "description": "...",
            "keywords": ["..."],
            "og_title": "...",
            "og_description": "...",
            "twitter_card": "summary_large_image"
        }
    """
    name = ctx.get("business_name") or ctx.get("tool_name") or "App"
    description = ctx.get("description") or ctx.get("tagline") or ""
    industry = ctx.get("industry") or ""
    tagline = ctx.get("tagline") or ""

    prompt = (
        f"Business: {name}\n"
        f"Description: {description}\n"
        f"Industry: {industry}\n"
        f"Tagline: {tagline}\n\n"
        "Generate SEO-optimized meta tags as JSON:\n"
        "{\n"
        '  "title": "under 60 chars, compelling, includes brand",\n'
        '  "description": "under 155 chars, actionable, includes CTA",\n'
        '  "keywords": ["5-7", "highly", "specific", "keywords"],\n'
        '  "og_title": "social-optimized title",\n'
        '  "og_description": "social-optimized description",\n'
        '  "twitter_card": "summary_large_image"\n'
        "}"
    )

    try:
        raw = await chat(
            [{"role": "user", "content": prompt}],
            system=_META_SYSTEM,
            max_tokens=300,
        )
        raw = re.sub(r"^```[a-z]*\n?", "", raw.strip(), flags=re.MULTILINE).rstrip("` \n")
        meta = json.loads(raw)

        # Enforce length limits
        meta["title"] = str(meta.get("title", name))[:60]
        meta["description"] = str(meta.get("description", description))[:155]
        if not isinstance(meta.get("keywords"), list):
            meta["keywords"] = []

        return meta

    except Exception:
        logger.exception("optimize_meta_tags failed for %s — using fallback", name)
        return {
            "title": f"{name} — {tagline}"[:60] if tagline else name[:60],
            "description": (description or tagline or f"{name}")[:155],
            "keywords": [w for w in [industry, name.lower().replace(" ", "-")] if w],
            "og_title": name,
            "og_description": description[:155],
            "twitter_card": "summary_large_image",
        }


def inject_meta_tags(html: str, meta: dict) -> str:
    """Inject optimized meta tags into HTML <head>."""
    if "<head" not in html.lower():
        return html

    block = ""

    # Title
    if title := meta.get("title"):
        html = re.sub(r"<title>[^<]*</title>", "", html, flags=re.IGNORECASE)
        block += f'  <title>{title}</title>\n'

    # Description
    if desc := meta.get("description"):
        html = re.sub(r'<meta\s+name=["\']description["\'][^>]*>', "", html, flags=re.IGNORECASE)
        block += f'  <meta name="description" content="{desc}">\n'

    # Keywords
    if keywords := meta.get("keywords"):
        html = re.sub(r'<meta\s+name=["\']keywords["\'][^>]*>', "", html, flags=re.IGNORECASE)
        block += f'  <meta name="keywords" content="{", ".join(keywords)}">\n'

    # Open Graph
    if og_title := meta.get("og_title"):
        html = re.sub(r'<meta\s+property=["\']og:title["\'][^>]*>', "", html, flags=re.IGNORECASE)
        block += f'  <meta property="og:title" content="{og_title}">\n'

    if og_desc := meta.get("og_description"):
        html = re.sub(r'<meta\s+property=["\']og:description["\'][^>]*>', "", html, flags=re.IGNORECASE)
        block += f'  <meta property="og:description" content="{og_desc}">\n'

    # Twitter
    if twitter_card := meta.get("twitter_card"):
        html = re.sub(r'<meta\s+name=["\']twitter:card["\'][^>]*>', "", html, flags=re.IGNORECASE)
        block += f'  <meta name="twitter:card" content="{twitter_card}">\n'

    if block:
        html = re.sub(r"(<head[^>]*>)", r"\1\n" + block, html, count=1, flags=re.IGNORECASE)

    return html


# ---------------------------------------------------------------------------
# 2. STRUCTURED DATA (JSON-LD)
# ---------------------------------------------------------------------------

async def generate_structured_data(ctx: dict) -> dict:
    """
    Generate schema.org JSON-LD structured data.

    Returns:
        {
            "organization": {...},
            "website": {...},
            "faq": [...],
            "product": {...}  # optional
        }
    """
    name = ctx.get("business_name") or ctx.get("tool_name") or "App"
    description = ctx.get("description") or ""
    url = ctx.get("url") or ctx.get("app_domain") or ""
    logo = ctx.get("logo_image_url") or ""

    structured_data = {}

    # Organization schema
    structured_data["organization"] = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": name,
        "description": description,
        "url": url,
    }
    if logo:
        structured_data["organization"]["logo"] = logo

    # WebSite schema
    structured_data["website"] = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": name,
        "url": url,
    }

    # Generate FAQ if we have enough context
    if description:
        faq_prompt = (
            f"Generate 3-5 frequently asked questions and answers for this business:\n"
            f"Name: {name}\n"
            f"Description: {description}\n\n"
            "Return JSON only:\n"
            "[\n"
            '  {"question": "...", "answer": "..."},\n'
            '  {"question": "...", "answer": "..."}\n'
            "]"
        )

        try:
            faq_raw = await chat(
                [{"role": "user", "content": faq_prompt}],
                system="You generate FAQ content for SEO. Return valid JSON only.",
                max_tokens=600,
            )
            faq_raw = re.sub(r"^```[a-z]*\n?", "", faq_raw.strip(), flags=re.MULTILINE).rstrip("` \n")
            faq_list = json.loads(faq_raw)

            if isinstance(faq_list, list) and len(faq_list) > 0:
                structured_data["faq"] = {
                    "@context": "https://schema.org",
                    "@type": "FAQPage",
                    "mainEntity": [
                        {
                            "@type": "Question",
                            "name": item["question"],
                            "acceptedAnswer": {
                                "@type": "Answer",
                                "text": item["answer"],
                            },
                        }
                        for item in faq_list
                    ],
                }
        except Exception:
            logger.exception("Failed to generate FAQ structured data for %s", name)

    return structured_data


def inject_structured_data(html: str, structured_data: dict) -> str:
    """Inject JSON-LD structured data into HTML <head>."""
    if "<head" not in html.lower():
        return html

    scripts = []
    for key, schema in structured_data.items():
        if schema:
            json_str = json.dumps(schema, indent=2)
            scripts.append(
                f'  <script type="application/ld+json">\n{json_str}\n  </script>\n'
            )

    if scripts:
        block = "".join(scripts)
        html = re.sub(r"(</head>)", block + r"\1", html, count=1, flags=re.IGNORECASE)

    return html


# ---------------------------------------------------------------------------
# 3. SITEMAP GENERATION
# ---------------------------------------------------------------------------

def generate_sitemap(pages: list[dict], base_url: str) -> str:
    """
    Generate sitemap.xml for a multi-page site.

    Args:
        pages: List of {"path": "/about", "priority": 0.8, "changefreq": "monthly"}
        base_url: e.g., "https://mysite.nanowork.app"

    Returns:
        sitemap.xml as string
    """
    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n'
    sitemap += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

    for page in pages:
        path = page.get("path", "/")
        priority = page.get("priority", 0.5)
        changefreq = page.get("changefreq", "weekly")
        lastmod = page.get("lastmod", datetime.utcnow().strftime("%Y-%m-%d"))

        url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"

        sitemap += "  <url>\n"
        sitemap += f"    <loc>{url}</loc>\n"
        sitemap += f"    <lastmod>{lastmod}</lastmod>\n"
        sitemap += f"    <changefreq>{changefreq}</changefreq>\n"
        sitemap += f"    <priority>{priority:.1f}</priority>\n"
        sitemap += "  </url>\n"

    sitemap += "</urlset>\n"
    return sitemap


# ---------------------------------------------------------------------------
# 4. CONTENT OPTIMIZATION
# ---------------------------------------------------------------------------

_CONTENT_SYSTEM = (
    "You are an expert SEO content optimizer. Rewrite HTML content to improve "
    "keyword targeting, readability, and search rankings while preserving the "
    "original intent and structure. Return the optimized HTML only — no markdown, "
    "no explanation."
)


async def optimize_content(html: str, target_keywords: list[str]) -> str:
    """
    Optimize page content for SEO without breaking structure.

    Args:
        html: Original HTML
        target_keywords: Keywords to target (e.g., ["coffee shop", "portland cafe"])

    Returns:
        Optimized HTML
    """
    # Extract text content from body
    body_match = re.search(r"<body[^>]*>(.*)</body>", html, re.DOTALL | re.IGNORECASE)
    if not body_match:
        return html

    body_content = body_match.group(1)

    # Skip if body is mostly script/style (SPA shell)
    if body_content.count("<script") > 5 or body_content.count("<style") > 5:
        logger.info("Skipping content optimization for SPA shell")
        return html

    prompt = (
        f"Optimize this HTML content for SEO. Target keywords: {', '.join(target_keywords)}\n\n"
        "Rules:\n"
        "- Keep all HTML structure (div, section, etc.) exactly the same\n"
        "- Improve headings (h1, h2) to include keywords naturally\n"
        "- Enhance paragraph text for readability and keyword density\n"
        "- Add alt text to images if missing\n"
        "- Do NOT change class names, IDs, or inline styles\n"
        "- Return ONLY the optimized HTML — no markdown fences\n\n"
        f"{body_content[:3000]}"  # Limit to avoid token overflow
    )

    try:
        optimized_body = await chat(
            [{"role": "user", "content": prompt}],
            system=_CONTENT_SYSTEM,
            max_tokens=3000,
        )

        # Replace body content
        html = re.sub(
            r"<body[^>]*>.*</body>",
            f"<body>{optimized_body}</body>",
            html,
            count=1,
            flags=re.DOTALL | re.IGNORECASE,
        )

        return html

    except Exception:
        logger.exception("Content optimization failed — returning original HTML")
        return html


# ---------------------------------------------------------------------------
# MAIN SEO AGENT
# ---------------------------------------------------------------------------

@register_agent("seo_agent", credits_cost=20)
async def seo_agent(
    ctx: dict,
    orchestrator: Optional[AgentOrchestrator] = None,
) -> AgentArtifact:
    """
    SEO optimization agent — performs all 4 SEO tasks.

    Input context:
        {
            "html": "<html>...</html>",
            "business_name": "...",
            "description": "...",
            "url": "https://...",
            "pages": [{"path": "/about", ...}],  # optional for multi-page
        }

    Returns:
        AgentArtifact with:
            {
                "optimized_html": "...",
                "meta_tags": {...},
                "structured_data": {...},
                "sitemap_xml": "...",  # if multi-page
                "optimizations_applied": ["meta", "structured_data", "sitemap", "content"]
            }
    """
    html = ctx.get("html", "")
    if not html:
        return AgentArtifact(
            agent_name="seo_agent",
            status="failed",
            data={},
            metadata={"error": "No HTML provided"},
        )

    optimizations_applied = []

    # 1. Meta tags
    try:
        meta_tags = await optimize_meta_tags(ctx)
        html = inject_meta_tags(html, meta_tags)
        optimizations_applied.append("meta_tags")
        logger.info("SEO: Applied meta tag optimizations")
    except Exception:
        logger.exception("SEO: Meta tag optimization failed")
        meta_tags = {}

    # 2. Structured data
    try:
        structured_data = await generate_structured_data(ctx)
        html = inject_structured_data(html, structured_data)
        optimizations_applied.append("structured_data")
        logger.info("SEO: Applied structured data (JSON-LD)")
    except Exception:
        logger.exception("SEO: Structured data generation failed")
        structured_data = {}

    # 3. Sitemap (if multi-page site)
    sitemap_xml = None
    if pages := ctx.get("pages"):
        try:
            base_url = ctx.get("url") or ctx.get("app_domain") or ""
            if base_url:
                sitemap_xml = generate_sitemap(pages, base_url)
                optimizations_applied.append("sitemap")
                logger.info("SEO: Generated sitemap.xml with %d pages", len(pages))
        except Exception:
            logger.exception("SEO: Sitemap generation failed")

    # 4. Content optimization
    target_keywords = meta_tags.get("keywords", [])
    if target_keywords:
        try:
            html = await optimize_content(html, target_keywords)
            optimizations_applied.append("content_optimization")
            logger.info("SEO: Optimized content for keywords: %s", target_keywords)
        except Exception:
            logger.exception("SEO: Content optimization failed")

    return AgentArtifact(
        agent_name="seo_agent",
        status="success" if len(optimizations_applied) >= 2 else "partial",
        data={
            "optimized_html": html,
            "meta_tags": meta_tags,
            "structured_data": structured_data,
            "sitemap_xml": sitemap_xml,
            "optimizations_applied": optimizations_applied,
        },
        metadata={
            "total_optimizations": len(optimizations_applied),
            "keywords_targeted": target_keywords,
        },
    )


# Backward-compatible wrapper for existing code
async def gen_seo_recommendations(entry: dict) -> dict:
    """Legacy interface — redirects to new seo_agent."""
    from ..core.agents.orchestration import delegate_to_agent

    artifact = await delegate_to_agent("seo_agent", entry)
    return artifact.data
