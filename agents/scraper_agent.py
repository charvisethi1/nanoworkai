"""
Intelligent Web Scraper Agent

Decides when to scrape external content based on user queries and automatically
fetches, processes, and stores relevant information in vector memory.

Architecture:
  User Query → Agent Analysis → Decision → Scrape → Store → Enhanced Response

Use Cases:
  - "Research competitor pricing" → Scrapes competitor websites
  - "What do people say about X?" → Scrapes reviews/forums
  - "Latest trends in Y industry" → Scrapes news/blogs
  - "How does Z work?" → Scrapes documentation/tutorials

The agent runs as:
  1. Real-time: Inline during conversation (fast URLs only)
  2. Background: Via Render worker (slow/complex scraping)
"""
from __future__ import annotations

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ScrapingStrategy(Enum):
    """Strategy for scraping based on query analysis."""
    NONE = "none"  # No scraping needed
    INLINE = "inline"  # Scrape immediately (fast)
    BACKGROUND = "background"  # Queue for background worker (slow)


@dataclass
class ScrapingDecision:
    """Decision about whether and how to scrape."""
    strategy: ScrapingStrategy
    urls: List[str]
    reason: str
    confidence: float  # 0-1
    search_query: Optional[str] = None  # For web search first


class ScraperAgentAnalyzer:
    """
    Analyzes user queries to decide if web scraping is needed.

    Uses LLM to:
      1. Detect queries that need external information
      2. Extract or generate relevant URLs
      3. Choose scraping strategy (inline vs background)
    """

    def __init__(self):
        self.scraping_keywords = {
            "competitor", "compare", "research", "what do people say",
            "reviews", "pricing", "trends", "latest", "how does",
            "documentation", "guide", "tutorial", "example",
            "market", "industry", "best practices", "alternatives",
        }

    async def analyze_query(
        self,
        user_query: str,
        conversation_context: Optional[str] = None,
    ) -> ScrapingDecision:
        """
        Analyze if query needs web scraping.

        Args:
            user_query: User's question/request
            conversation_context: Prior conversation context

        Returns:
            ScrapingDecision with strategy and URLs
        """
        # Quick keyword check
        query_lower = user_query.lower()
        needs_scraping = any(kw in query_lower for kw in self.scraping_keywords)

        if not needs_scraping:
            return ScrapingDecision(
                strategy=ScrapingStrategy.NONE,
                urls=[],
                reason="No external information needed",
                confidence=0.9
            )

        # Extract URLs if mentioned explicitly
        urls = self._extract_urls(user_query)

        if urls:
            # User provided URLs - scrape them
            strategy = self._choose_strategy(urls)
            return ScrapingDecision(
                strategy=strategy,
                urls=urls,
                reason=f"User provided {len(urls)} URL(s) to scrape",
                confidence=1.0
            )

        # Use LLM to decide if scraping needed and what to search
        decision = await self._llm_analyze(user_query, conversation_context)
        return decision

    def _extract_urls(self, text: str) -> List[str]:
        """Extract URLs from text."""
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        return re.findall(url_pattern, text)

    def _choose_strategy(self, urls: List[str]) -> ScrapingStrategy:
        """
        Choose scraping strategy based on URLs.

        Inline: Single URL, known fast domains
        Background: Multiple URLs, complex domains, or JS-heavy sites
        """
        if len(urls) > 3:
            return ScrapingStrategy.BACKGROUND

        # Check for known fast/slow domains
        fast_domains = {
            "github.com", "docs.", "wikipedia.org",
            "stackoverflow.com", "medium.com"
        }

        slow_domains = {
            "linkedin.com", "twitter.com", "facebook.com",
            "instagram.com", "reddit.com"  # These need JS rendering
        }

        for url in urls:
            if any(slow in url for slow in slow_domains):
                return ScrapingStrategy.BACKGROUND

        # Default to inline for fast domains or unknown
        return ScrapingStrategy.INLINE

    async def _llm_analyze(
        self,
        user_query: str,
        conversation_context: Optional[str],
    ) -> ScrapingDecision:
        """Use LLM to analyze if scraping needed and generate search query."""
        from ..infrastructure.llm_client import chat

        system_prompt = """You are a web research assistant. Analyze if the user's query needs external web information.

Output ONLY a JSON object:
{
    "needs_scraping": true/false,
    "reason": "why scraping is/isn't needed",
    "search_query": "query to search for relevant URLs (if needed)",
    "confidence": 0.0-1.0
}

Needs scraping when:
- Asking about competitors, pricing, reviews
- Requesting latest information, trends, news
- Comparing products/services
- Learning how something works (external docs/tutorials)

Does NOT need scraping when:
- Question is about user's own business/preferences
- General conceptual questions answerable from knowledge
- Already have sufficient context"""

        context = f"Context: {conversation_context}\n\n" if conversation_context else ""
        prompt = f"{context}User Query: {user_query}"

        try:
            response = await chat(
                [{"role": "user", "content": prompt}],
                system=system_prompt,
                max_tokens=200
            )

            # Parse JSON response
            import json
            response_clean = re.sub(r"^```json\s*", "", response)
            response_clean = re.sub(r"\s*```$", "", response_clean)
            data = json.loads(response_clean)

            if data.get("needs_scraping"):
                return ScrapingDecision(
                    strategy=ScrapingStrategy.BACKGROUND,  # Default to background
                    urls=[],  # Will search for URLs
                    reason=data.get("reason", "LLM determined scraping needed"),
                    confidence=data.get("confidence", 0.7),
                    search_query=data.get("search_query")
                )
            else:
                return ScrapingDecision(
                    strategy=ScrapingStrategy.NONE,
                    urls=[],
                    reason=data.get("reason", "No scraping needed"),
                    confidence=data.get("confidence", 0.8)
                )

        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            # Conservative: don't scrape if unsure
            return ScrapingDecision(
                strategy=ScrapingStrategy.NONE,
                urls=[],
                reason=f"Analysis failed: {e}",
                confidence=0.5
            )


class ScraperAgent:
    """
    Main scraper agent that executes scraping based on decisions.

    Handles:
      - Inline scraping (real-time)
      - Background scraping (queued)
      - URL search via web search API
      - Storage in vector memory
    """

    def __init__(self):
        self.analyzer = ScraperAgentAnalyzer()

    async def process_query(
        self,
        user_query: str,
        user_id: str,
        conversation_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process user query and scrape if needed.

        Returns:
            {
                "scraped": bool,
                "strategy": str,
                "urls_scraped": List[str],
                "chunks_stored": int,
                "search_results": List[str],  # If web search performed
                "message": str
            }
        """
        # Analyze query
        decision = await self.analyzer.analyze_query(user_query, conversation_context)

        if decision.strategy == ScrapingStrategy.NONE:
            return {
                "scraped": False,
                "strategy": "none",
                "urls_scraped": [],
                "chunks_stored": 0,
                "message": decision.reason
            }

        # Get URLs (either from decision or via search)
        urls = decision.urls
        if not urls and decision.search_query:
            urls = await self._search_for_urls(decision.search_query)

        if not urls:
            return {
                "scraped": False,
                "strategy": decision.strategy.value,
                "urls_scraped": [],
                "chunks_stored": 0,
                "message": "No relevant URLs found"
            }

        # Execute scraping based on strategy
        if decision.strategy == ScrapingStrategy.INLINE:
            result = await self._scrape_inline(urls, user_id, user_query)
        else:  # BACKGROUND
            result = await self._scrape_background(urls, user_id, user_query)

        return result

    async def _search_for_urls(self, search_query: str) -> List[str]:
        """
        Search web for relevant URLs.

        Can integrate with:
          - Google Custom Search API
          - Bing Search API
          - DuckDuckGo (no API key)
          - Brave Search API
        """
        # TODO: Integrate real web search API
        # For now, return empty list
        logger.info(f"Would search for: {search_query}")
        return []

    async def _scrape_inline(
        self,
        urls: List[str],
        user_id: str,
        context: str,
    ) -> Dict[str, Any]:
        """
        Scrape URLs immediately (real-time).

        Use for: Fast URLs, small content, user waiting
        """
        from ..memory import scrape_url_to_memory

        all_docs = []
        scraped_urls = []

        for url in urls[:3]:  # Limit to 3 URLs inline
            try:
                logger.info(f"[ScraperAgent] Inline scraping: {url}")

                docs = await scrape_url_to_memory(
                    url=url,
                    user_id=user_id,
                    metadata={
                        "scraping_type": "inline",
                        "context": context,
                        "agent": "scraper_agent"
                    }
                )

                all_docs.extend(docs)
                scraped_urls.append(url)

            except Exception as e:
                logger.error(f"Inline scraping failed for {url}: {e}")
                continue

        return {
            "scraped": True,
            "strategy": "inline",
            "urls_scraped": scraped_urls,
            "chunks_stored": len(all_docs),
            "message": f"Scraped {len(scraped_urls)} URL(s) with {len(all_docs)} chunks"
        }

    async def _scrape_background(
        self,
        urls: List[str],
        user_id: str,
        context: str,
    ) -> Dict[str, Any]:
        """
        Queue URLs for background scraping.

        Use for: Multiple URLs, slow sites, JS-heavy pages
        """
        from ..db.schema import Tables
        from ..nano_deploy.waitlist_db import supabase
        import asyncio

        # Queue each URL as a background job
        job_ids = []

        for url in urls:
            try:
                job = await asyncio.to_thread(
                    supabase.table(Tables.LINQ_JOBS).insert({
                        "job_type": "web_scrape",
                        "payload": {
                            "url": url,
                            "user_id": user_id,
                            "context": context,
                            "agent": "scraper_agent"
                        },
                        "status": "pending"
                    }).execute
                )

                if job.data:
                    job_ids.append(job.data[0]["id"])

            except Exception as e:
                logger.error(f"Failed to queue scraping job for {url}: {e}")
                continue

        return {
            "scraped": True,
            "strategy": "background",
            "urls_scraped": urls,
            "chunks_stored": 0,  # Will be stored by background worker
            "job_ids": job_ids,
            "message": f"Queued {len(urls)} URL(s) for background scraping. You'll be notified when complete."
        }

    async def search_scraped_content(
        self,
        query: str,
        user_id: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Search previously scraped content for a user.

        Returns:
            List of relevant chunks with URLs and scores
        """
        from ..memory import get_scraper_integration

        scraper = get_scraper_integration()

        results = await scraper.search_scraped_content(
            query=query,
            namespace=f"user_{user_id}",
            limit=limit
        )

        return [
            {
                "content": result.document.content,
                "url": result.document.metadata.get("url"),
                "score": result.score,
                "scraped_at": result.document.metadata.get("scraped_at")
            }
            for result in results
        ]


# Global singleton
_scraper_agent: Optional[ScraperAgent] = None


def get_scraper_agent() -> ScraperAgent:
    """Get global scraper agent instance."""
    global _scraper_agent
    if _scraper_agent is None:
        _scraper_agent = ScraperAgent()
    return _scraper_agent


# Convenience functions
async def analyze_query_for_scraping(
    user_query: str,
    conversation_context: Optional[str] = None,
) -> ScrapingDecision:
    """Analyze if query needs web scraping."""
    agent = get_scraper_agent()
    return await agent.analyzer.analyze_query(user_query, conversation_context)


async def scrape_for_query(
    user_query: str,
    user_id: str,
    conversation_context: Optional[str] = None,
) -> Dict[str, Any]:
    """Process query and scrape if needed."""
    agent = get_scraper_agent()
    return await agent.process_query(user_query, user_id, conversation_context)


async def search_scraped(
    query: str,
    user_id: str,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Search previously scraped content."""
    agent = get_scraper_agent()
    return await agent.search_scraped_content(query, user_id, limit)
