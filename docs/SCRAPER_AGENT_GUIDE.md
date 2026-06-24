## Intelligent Web Scraper Agent

Automatic web scraping agent that decides when to fetch external content based on user queries.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [How It Works](#how-it-works)
4. [Usage Examples](#usage-examples)
5. [API Reference](#api-reference)
6. [Render Worker Deployment](#render-worker-deployment)
7. [Configuration](#configuration)

---

## Overview

The Scraper Agent is an intelligent system that:

✅ **Analyzes user queries** to detect when external information is needed  
✅ **Automatically scrapes relevant URLs** without explicit user commands  
✅ **Runs inline or background** depending on complexity  
✅ **Stores scraped content** in vector memory for semantic search  
✅ **Notifies users** when background scraping completes  

### Use Cases

| User Query | Agent Action |
|------------|--------------|
| "Research competitor pricing" | Searches for competitor URLs, scrapes pricing pages |
| "What do people say about X?" | Scrapes reviews, forums, social media |
| "Latest trends in Y industry" | Scrapes news, blogs, industry reports |
| "How does Z work?" | Scrapes documentation, tutorials |
| "Compare A vs B" | Scrapes both products' websites |

---

## Architecture

```
User Query
    ↓
┌────────────────────────────────────────────────────┐
│         ScraperAgentAnalyzer                       │
│  • Keyword detection                               │
│  • LLM-based intent analysis                       │
│  • URL extraction or search query generation       │
│  • Strategy selection (inline vs background)       │
└─────────────┬──────────────────────────────────────┘
              │
              ▼
        ┌─────────────┐
        │  Decision   │
        └──┬──────┬───┘
           │      │
    ┌──────┘      └──────┐
    ▼                    ▼
┌────────────┐    ┌────────────────┐
│  INLINE    │    │  BACKGROUND    │
│  Scraping  │    │  Scraping      │
│            │    │                │
│ • Fast     │    │ • Slow/complex │
│ • 1-3 URLs │    │ • Multiple URLs│
│ • Real-time│    │ • Queued       │
└─────┬──────┘    └──────┬─────────┘
      │                  │
      │                  ▼
      │           ┌──────────────────┐
      │           │  Render Worker   │
      │           │  • Polls queue   │
      │           │  • Processes jobs│
      │           │  • Stores results│
      │           └──────┬───────────┘
      │                  │
      └──────────┬───────┘
                 ▼
         ┌───────────────────┐
         │  Vector Memory    │
         │  • Chunked        │
         │  • Embedded       │
         │  • Searchable     │
         └───────────────────┘
                 ↓
         Enhanced Response
```

---

## How It Works

### 1. Query Analysis

When a user sends a message, the agent analyzes it:

```python
decision = await analyze_query_for_scraping(
    user_query="What's Notion's pricing model?",
    conversation_context="Discussing SaaS pricing"
)

# Returns:
# {
#     "strategy": "inline",
#     "urls": ["https://notion.so/pricing"],
#     "reason": "User asking about competitor pricing",
#     "confidence": 0.95
# }
```

**Analysis steps:**
1. **Keyword check** - Fast detection of scraping keywords
2. **URL extraction** - Find any URLs mentioned
3. **LLM analysis** - Deep understanding of intent
4. **Strategy selection** - Inline vs background

### 2. Strategy Selection

| Condition | Strategy | Reason |
|-----------|----------|---------|
| 1-3 fast URLs | Inline | Quick response, user waiting |
| > 3 URLs | Background | Too slow for real-time |
| JS-heavy sites | Background | Needs browser rendering |
| User waiting | Inline | Immediate feedback |

### 3. Scraping Execution

#### Inline Scraping
```python
# User gets results immediately
result = await scrape_for_query(
    user_query="Check Notion pricing",
    user_id="user123"
)

# Result:
# {
#     "scraped": true,
#     "strategy": "inline",
#     "urls_scraped": ["https://notion.so/pricing"],
#     "chunks_stored": 8,
#     "message": "Scraped 1 URL with 8 chunks"
# }
```

#### Background Scraping
```python
# Jobs queued, user notified later
result = await scrape_for_query(
    user_query="Research all PM tool pricing",
    user_id="user123"
)

# Result:
# {
#     "scraped": true,
#     "strategy": "background",
#     "urls_scraped": ["url1", "url2", "url3", ...],
#     "chunks_stored": 0,  # Not yet processed
#     "job_ids": ["job_123", "job_456"],
#     "message": "Queued 5 URLs for scraping. You'll be notified."
# }
```

### 4. Content Storage

Scraped content is:
1. **Chunked** - Split into semantic chunks (1000 chars)
2. **Embedded** - Converted to vectors (Voyage-3)
3. **Stored** - Saved in vector_memory table
4. **Indexed** - HNSW index for fast search

### 5. Search & Retrieval

Later, users can query the scraped content:

```python
results = await search_scraped(
    query="competitor pricing tiers",
    user_id="user123"
)

# Returns relevant chunks from all scraped content
```

---

## Usage Examples

### Example 1: Automatic Scraping

```python
# In your message handler
from nanowork_mobile.agents.scraper_agent import scrape_for_query

async def handle_message(user_text, user_id):
    # Automatically analyze and scrape if needed
    scrape_result = await scrape_for_query(
        user_query=user_text,
        user_id=user_id
    )
    
    if scrape_result["scraped"]:
        # Content was scraped - use it in response
        scraped_content = await search_scraped(user_text, user_id)
        # ... use content in LLM prompt
    
    # Continue with normal response
    response = await generate_response(user_text, scraped_content)
    return response
```

### Example 2: Explicit Scraping

```python
# User says: "Scrape https://competitor.com/pricing"
from nanowork_mobile.routers.scraper import scrape_for_query_endpoint

result = await scrape_for_query_endpoint(
    request={
        "query": "Scrape https://competitor.com/pricing",
        "user_id": "user123"
    }
)

# Returns:
# {
#     "scraped": true,
#     "strategy": "inline",
#     "urls_scraped": ["https://competitor.com/pricing"],
#     "chunks_stored": 12,
#     "message": "Scraped 1 URL with 12 chunks"
# }
```

### Example 3: Search Scraped Content

```python
# Later: user asks about pricing
from nanowork_mobile.routers.scraper import search_scraped_content

results = await search_scraped_content(
    request={
        "query": "pricing tiers and features",
        "user_id": "user123",
        "limit": 5
    }
)

# Returns:
# {
#     "results": [
#         {
#             "content": "Competitor offers 3 tiers: Free, Pro ($10/mo), Enterprise...",
#             "url": "https://competitor.com/pricing",
#             "score": 0.89,
#             "scraped_at": "2026-05-08T10:30:00Z"
#         }
#     ],
#     "count": 1
# }
```

### Example 4: Webhook Integration

```python
# Enable auto-scraping in your webhook
from nanowork_mobile.routers.scraper import auto_scrape_webhook

@app.post("/webhook/message")
async def handle_message_webhook(user_message: str, user_id: str):
    # Automatically scrape if query needs it
    await auto_scrape_webhook(
        user_message=user_message,
        user_id=user_id
    )
    
    # Continue processing message
    # Scraping happens in background, doesn't block
    ...
```

---

## API Reference

### POST /scraper/analyze

Analyze if query needs scraping.

**Request:**
```json
{
  "query": "Research competitor pricing",
  "conversation_context": "User building SaaS tool"
}
```

**Response:**
```json
{
  "needs_scraping": true,
  "strategy": "background",
  "urls": [],
  "reason": "Query requests competitor research",
  "confidence": 0.9,
  "search_query": "SaaS competitor pricing"
}
```

### POST /scraper/scrape

Execute scraping for a query.

**Request:**
```json
{
  "query": "What's Notion's pricing?",
  "user_id": "user123",
  "conversation_context": "Discussing pricing models"
}
```

**Response (inline):**
```json
{
  "scraped": true,
  "strategy": "inline",
  "urls_scraped": ["https://notion.so/pricing"],
  "chunks_stored": 8,
  "message": "Scraped 1 URL with 8 chunks"
}
```

**Response (background):**
```json
{
  "scraped": true,
  "strategy": "background",
  "urls_scraped": ["url1", "url2"],
  "chunks_stored": 0,
  "job_ids": ["job_123", "job_456"],
  "message": "Queued 2 URLs. You'll be notified when complete."
}
```

### POST /scraper/search

Search scraped content.

**Request:**
```json
{
  "query": "pricing tiers",
  "user_id": "user123",
  "limit": 5
}
```

**Response:**
```json
{
  "results": [
    {
      "content": "Pricing information...",
      "url": "https://example.com",
      "score": 0.89,
      "scraped_at": "2026-05-08T10:30:00Z"
    }
  ],
  "count": 1
}
```

### GET /scraper/status/{job_id}

Check background job status.

**Response:**
```json
{
  "job_id": "job_123",
  "status": "completed",
  "created_at": "2026-05-08T10:00:00Z",
  "completed_at": "2026-05-08T10:05:00Z",
  "error": null
}
```

### POST /scraper/webhook/auto-scrape

Webhook for automatic scraping.

**Request:**
```json
{
  "user_message": "Research competitor pricing",
  "user_id": "user123",
  "conversation_context": "Building SaaS"
}
```

**Response:**
```json
{
  "auto_scraped": true,
  "strategy": "background",
  "reason": "Competitor research detected"
}
```

---

## Render Worker Deployment

The background scraper runs as a separate Render worker service.

### Configuration in render.yaml

```yaml
- type: worker
  name: nanowork-scraper-worker
  runtime: python
  plan: starter
  buildCommand: uv sync --frozen && uv cache prune --ci
  startCommand: uv run python -m nanowork_mobile.workers.scraper_worker
  envVars:
    - key: SUPABASE_URL
      sync: false
    - key: VOYAGE_API_KEY
      sync: false
    - key: WORKER_POLL_INTERVAL
      value: "2.0"
```

### Worker Features

✅ **Automatic polling** - Checks for jobs every 2 seconds  
✅ **Graceful shutdown** - Handles SIGTERM/SIGINT  
✅ **Error handling** - Retries failed scrapes  
✅ **User notifications** - Sends message when complete  
✅ **Exponential backoff** - Reduces polling when idle  

### Scaling

| Load | Workers | Cost | Latency |
|------|---------|------|---------|
| Low (< 10 jobs/min) | 1 | $7/mo | 2-5 min |
| Medium (10-50 jobs/min) | 2-3 | $14-21/mo | 1-3 min |
| High (> 50 jobs/min) | 5+ | $35+/mo | < 1 min |

### Monitoring

```bash
# View worker logs
render logs --service nanowork-scraper-worker --tail

# Check job queue depth
curl http://localhost:8000/memory/stats

# Monitor worker health
# (Worker auto-restarts if crashes)
```

---

## Configuration

### Environment Variables

```bash
# Embedding Provider
EMBEDDING_PROVIDER=voyage  # or openai, local
VOYAGE_API_KEY=your_key

# Scraper Backend
SCRAPER_BACKEND=jina  # or browserbase
JINA_API_KEY=optional
BROWSERBASE_API_KEY=your_key  # For JS-heavy sites
BROWSERBASE_PROJECT_ID=your_project

# Worker Settings
WORKER_POLL_INTERVAL=2.0  # Seconds between job checks
WORKER_MAX_RETRIES=3  # Max retries per job
WORKER_TIMEOUT=300  # Timeout per URL (seconds)

# Supabase
SUPABASE_URL=your_url
SUPABASE_SERVICE_KEY=your_key

# Notifications
LINQ_API_KEY=your_key  # For user notifications
```

### Scraping Keywords

The agent detects these keywords:

```python
scraping_keywords = {
    "competitor", "compare", "research",
    "what do people say", "reviews", "pricing",
    "trends", "latest", "how does",
    "documentation", "guide", "tutorial",
    "market", "industry", "best practices",
    "alternatives"
}
```

Add custom keywords:

```python
from nanowork_mobile.agents.scraper_agent import get_scraper_agent

agent = get_scraper_agent()
agent.analyzer.scraping_keywords.add("analyze")
agent.analyzer.scraping_keywords.add("investigate")
```

### Strategy Selection

Control when to use inline vs background:

```python
# In scraper_agent.py, modify _choose_strategy():

def _choose_strategy(self, urls: List[str]) -> ScrapingStrategy:
    # Inline for <= 5 URLs (default is 3)
    if len(urls) > 5:
        return ScrapingStrategy.BACKGROUND
    
    # Always inline for specific domains
    if any("docs." in url or "github.com" in url for url in urls):
        return ScrapingStrategy.INLINE
    
    return ScrapingStrategy.INLINE
```

---

## Best Practices

### 1. Rate Limiting

Respect target sites:

```python
# Add delay between scrapes
import asyncio

for url in urls:
    await scrape_url(url)
    await asyncio.sleep(1)  # 1 second between requests
```

### 2. Caching

Avoid re-scraping same URLs:

```python
# Check if URL was scraped recently
from datetime import datetime, timedelta

async def needs_rescrape(url: str, user_id: str) -> bool:
    results = await search_scraped(
        query=url,
        user_id=user_id,
        limit=1
    )
    
    if results:
        scraped_at = results[0]["scraped_at"]
        age = datetime.now() - datetime.fromisoformat(scraped_at)
        return age > timedelta(days=7)  # Re-scrape after 7 days
    
    return True  # Not scraped yet
```

### 3. Error Handling

Handle scraping failures gracefully:

```python
try:
    result = await scrape_for_query(query, user_id)
except Exception as e:
    # Fall back to web search or LLM knowledge
    logger.error(f"Scraping failed: {e}")
    # Continue without scraped content
```

### 4. User Privacy

Store scraped content per-user:

```python
# Each user has their own namespace
namespace = f"user_{user_id}"

# Users can't access others' scraped content
# Automatically enforced by namespace isolation
```

---

## Troubleshooting

### "No URLs found"

**Problem**: Agent can't find URLs to scrape

**Solutions**:
1. Integrate web search API (Google, Bing, DuckDuckGo)
2. Provide URLs explicitly in query
3. Use fallback to LLM knowledge

### "Scraping timed out"

**Problem**: URL takes too long to scrape

**Solutions**:
1. Increase `WORKER_TIMEOUT`
2. Use background scraping
3. Skip problematic domains

### "Worker not processing jobs"

**Problem**: Background jobs stuck in queue

**Check**:
```bash
# View worker logs
render logs --service nanowork-scraper-worker

# Check if worker is running
render services list | grep scraper

# Restart worker
render services restart nanowork-scraper-worker
```

### "Content quality is poor"

**Problem**: Scraped content has too much noise

**Solutions**:
1. Use Browserbase instead of Jina (better extraction)
2. Adjust chunking strategy
3. Filter out navigation/footer content

---

## Next Steps

1. **Deploy Worker**: Push to Render, worker starts automatically
2. **Test Scraping**: Try `/scraper/scrape` endpoint
3. **Enable Auto-scrape**: Add webhook to message handler
4. **Monitor**: Check `/memory/stats` and worker logs
5. **Optimize**: Adjust strategies based on usage patterns

---

## Support

- 📧 Email: engineering@nanowork.ai
- 📝 Issues: GitHub with [scraper-agent] tag
- 📚 API Docs: `/docs` (FastAPI)
