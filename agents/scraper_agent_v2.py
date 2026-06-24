"""
Scraper Agent v2 — Web scraping with automatic SEO analysis delegation.

Demonstrates agent-to-agent delegation: after scraping a site, automatically
delegates to SEO agent to analyze competitors' SEO strategies.
"""
from __future__ import annotations

import logging
from typing import Optional

from ..core.agents.orchestration import AgentArtifact, AgentOrchestrator, register_agent

logger = logging.getLogger(__name__)


@register_agent("scraper_agent", credits_cost=15)
async def scraper_agent(
    ctx: dict,
    orchestrator: Optional[AgentOrchestrator] = None,
) -> AgentArtifact:
    """
    Scrape a URL and optionally delegate to SEO agent for analysis.

    Input context:
        {
            "url": "https://...",
            "analyze_seo": True,  # if True, delegates to SEO agent
        }

    Returns:
        AgentArtifact with scraped content and optional SEO analysis
    """
    from ..agents.scraper_agent import ScraperAgent as LegacyScraperAgent

    url = ctx.get("url")
    if not url:
        return AgentArtifact(
            agent_name="scraper_agent",
            status="failed",
            data={},
            metadata={"error": "No URL provided"},
        )

    # Use existing scraper implementation
    scraper = LegacyScraperAgent()
    try:
        scraped_data = await scraper.scrape(url)

        data = {
            "url": url,
            "scraped_content": scraped_data,
        }

        # If analyze_seo is True and we have an orchestrator, delegate to SEO agent
        if ctx.get("analyze_seo") and orchestrator:
            logger.info("Scraper delegating to SEO agent for competitor analysis")

            seo_artifact = await orchestrator.delegate(
                "seo_agent",
                {
                    "html": scraped_data.get("html", ""),
                    "business_name": scraped_data.get("title", ""),
                    "url": url,
                },
                requesting_agent="scraper_agent",
            )

            data["seo_analysis"] = seo_artifact.data

            return AgentArtifact(
                agent_name="scraper_agent",
                status="success",
                data=data,
                metadata={
                    "delegated_to": ["seo_agent"],
                },
                sub_artifacts=[seo_artifact],
            )

        return AgentArtifact(
            agent_name="scraper_agent",
            status="success",
            data=data,
        )

    except Exception as exc:
        logger.exception("Scraper failed for URL: %s", url)
        return AgentArtifact(
            agent_name="scraper_agent",
            status="failed",
            data={"url": url},
            metadata={"error": str(exc)},
        )
