## Vector Memory & Web Scraper System

Complete guide to the vector embeddings, semantic memory, and web scraper integration.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Setup](#setup)
4. [Usage Examples](#usage-examples)
5. [API Reference](#api-reference)
6. [Web Scraper Integration](#web-scraper-integration)
7. [Advanced Features](#advanced-features)
8. [Performance & Scaling](#performance--scaling)

---

## Overview

The vector memory system provides:

✅ **Semantic Search** - Find relevant information by meaning, not keywords  
✅ **Conversation Memory** - Remember past conversations with context  
✅ **User Preferences** - Store and retrieve user-specific settings  
✅ **Web Scraping** - Scrape URLs and make content searchable  
✅ **Multi-Provider** - Support for Voyage AI, OpenAI, and local models  
✅ **Namespace Isolation** - Per-user data separation  

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Application Layer                         │
│                                                              │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐           │
│  │   Agent    │  │    API     │  │  Workflow  │           │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘           │
└────────┼────────────────┼────────────────┼──────────────────┘
         │                │                │
         ▼                ▼                ▼
┌──────────────────────────────────────────────────────────────┐
│                 Vector Memory Layer                          │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │            EmbeddingService                             ││
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐                  ││
│  │  │ Voyage  │ │ OpenAI  │ │  Local  │                  ││
│  │  └─────────┘ └─────────┘ └─────────┘                  ││
│  └─────────────────────────────────────────────────────────┘│
│                           │                                  │
│                           ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐│
│  │        VectorMemoryStore                                ││
│  │  • Store documents with embeddings                      ││
│  │  • Semantic search                                      ││
│  │  • Conversation tracking                                ││
│  │  • User preferences                                     ││
│  └─────────────────────────────────────────────────────────┘│
│                           │                                  │
│                           ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐│
│  │     WebScraperIntegration                               ││
│  │  • Scrape URLs                                          ││
│  │  • Chunk content                                        ││
│  │  • Embed & store                                        ││
│  └─────────────────────────────────────────────────────────┘│
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│              Supabase PostgreSQL + pgvector                  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  vector_memory table                                   │ │
│  │  • id, content, embedding (1024-d)                     │ │
│  │  • metadata (JSONB), source, namespace                 │ │
│  │  • HNSW index for fast similarity search               │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  RPC Functions:                                              │
│  • match_vector_memory (semantic search)                     │
│  • get_recent_memories (time-based)                          │
│  • cleanup_old_memories (maintenance)                        │
└──────────────────────────────────────────────────────────────┘
```

---

## Setup

### 1. Install Dependencies

```bash
# Update dependencies (includes sentence-transformers, pgvector)
uv sync
```

### 2. Run Database Migration

```bash
# Apply vector memory table and functions
python scripts/run_migrations.py

# Or manually via Supabase CLI
supabase db push
```

### 3. Configure Environment

```bash
# .env file

# Embedding Provider (voyage, openai, or local)
EMBEDDING_PROVIDER=voyage

# Voyage AI (recommended for production)
VOYAGE_API_KEY=your_voyage_key
VOYAGE_MODEL=voyage-3  # Optional, defaults to voyage-3

# OpenAI (alternative)
OPENAI_API_KEY=your_openai_key

# Local model (no API key needed, runs on CPU/GPU)
# Uses sentence-transformers/all-MiniLM-L6-v2 by default

# Supabase (required)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your_service_key

# Web Scraper
SCRAPER_BACKEND=jina  # or browserbase
JINA_API_KEY=your_jina_key  # Optional, works without key
```

### 4. Verify Setup

```bash
# Test embedding service
python -c "
import asyncio
from nanowork_mobile.memory import embed_text

async def test():
    embedding = await embed_text('Hello world')
    print(f'Embedding dimension: {len(embedding)}')

asyncio.run(test())
"

# Should print: Embedding dimension: 1024 (or 384 for local)
```

---

## Usage Examples

### Store and Search Memories

```python
from nanowork_mobile.memory import store_memory, search_memory

# Store a memory
doc = await store_memory(
    content="User prefers subscription pricing with annual discount",
    user_id="user123",
    metadata={"context": "financial_planning", "confidence": 0.95}
)

print(f"Stored: {doc.id}")

# Search memories
results = await search_memory(
    query="What pricing model does the user prefer?",
    user_id="user123",
    limit=5
)

for result in results:
    print(f"Score: {result.score:.3f} | {result.document.content}")
```

### Conversation Memory

```python
from nanowork_mobile.memory import get_vector_memory

memory = get_vector_memory()

# Store conversation turn
await memory.store_conversation_turn(
    user_id="user123",
    user_message="I want to build a SaaS platform",
    assistant_message="Great! Let's start with your target audience.",
    metadata={"task": "onboarding", "turn": 1}
)

# Get relevant conversation context
context = await memory.get_conversation_context(
    user_id="user123",
    query="What is the user building?",
    limit=5
)

print(context)
# Output:
# --- CONVERSATION HISTORY ---
# [Relevance: 0.92]
# User: I want to build a SaaS platform
# Assistant: Great! Let's start with your target audience.
# --- END CONVERSATION HISTORY ---
```

### User Preferences

```python
from nanowork_mobile.memory import get_vector_memory

memory = get_vector_memory()

# Store preference
await memory.store_user_preference(
    user_id="user123",
    preference_key="pricing_model",
    preference_value="subscription with 3 tiers",
    description="User chose subscription over one-time payment"
)

# Get preferences (with optional context filter)
preferences = await memory.get_user_preferences(
    user_id="user123",
    context="pricing"  # Semantic filter
)

print(preferences)
# Output: {"pricing_model": "subscription with 3 tiers"}
```

### Web Scraping to Memory

```python
from nanowork_mobile.memory import scrape_url_to_memory

# Scrape competitor website
documents = await scrape_url_to_memory(
    url="https://competitor.com/pricing",
    user_id="user123",
    metadata={
        "purpose": "competitor_research",
        "competitor_name": "Acme Corp"
    }
)

print(f"Stored {len(documents)} chunks")

# Later: search scraped content
from nanowork_mobile.memory import search_memory

results = await search_memory(
    query="competitor pricing models",
    user_id="user123",
    limit=3
)

for result in results:
    if result.document.source == "web_scrape":
        url = result.document.metadata.get("url")
        print(f"From {url}: {result.document.content[:200]}...")
```

---

## API Reference

### REST Endpoints

All endpoints are under `/memory`:

#### POST /memory/store

Store a memory with embedding.

**Request:**
```json
{
  "content": "User prefers dark mode",
  "user_id": "user123",
  "metadata": {"key": "value"},
  "source": "user_preference"
}
```

**Response:**
```json
{
  "success": true,
  "document_id": "user_123_pref_dark_mode",
  "message": "Memory stored successfully"
}
```

#### POST /memory/search

Semantic search across memories.

**Request:**
```json
{
  "query": "What UI preferences does the user have?",
  "user_id": "user123",
  "limit": 5,
  "threshold": 0.7
}
```

**Response:**
```json
{
  "results": [
    {
      "content": "User prefers dark mode",
      "score": 0.89,
      "rank": 1,
      "metadata": {},
      "source": "user_preference",
      "timestamp": "2026-05-08T10:30:00Z"
    }
  ],
  "count": 1
}
```

#### POST /memory/scrape

Scrape URL and store in memory.

**Request:**
```json
{
  "url": "https://example.com/article",
  "user_id": "user123",
  "metadata": {"category": "research"}
}
```

**Response:**
```json
{
  "success": true,
  "chunks_stored": 5,
  "document_ids": ["user_123_scrape_abc_chunk_0", "..."],
  "message": "Scraped and stored 5 chunks from https://example.com/article"
}
```

#### POST /memory/conversation

Get conversation context for a query.

**Request:**
```json
{
  "query": "What did we discuss about pricing?",
  "user_id": "user123",
  "limit": 5
}
```

**Response:**
```json
{
  "context": "--- CONVERSATION HISTORY ---\n...\n--- END ---",
  "relevant_turns": 3
}
```

#### POST /memory/preference

Store user preference.

**Request:**
```json
{
  "user_id": "user123",
  "preference_key": "theme",
  "preference_value": "dark",
  "description": "User prefers dark mode"
}
```

#### POST /memory/preferences

Get user preferences (optionally filtered by context).

**Request:**
```json
{
  "user_id": "user123",
  "context": "UI settings"
}
```

**Response:**
```json
{
  "preferences": {
    "theme": "dark",
    "font_size": "medium"
  },
  "count": 2
}
```

#### GET /memory/stats

Get memory system statistics (admin endpoint).

**Response:**
```json
{
  "total_memories": 15420,
  "by_source": {
    "conversation": 8500,
    "user_preference": 1200,
    "web_scrape": 5720
  },
  "namespace_count": 342,
  "oldest_memory": "2026-01-15T08:00:00Z",
  "newest_memory": "2026-05-08T14:30:00Z"
}
```

---

## Web Scraper Integration

### Supported Backends

#### 1. Jina AI (Default)
- **Pros**: Fast, no API key needed, markdown output
- **Cons**: No JavaScript rendering
- **Best for**: Static content, blogs, documentation

```bash
SCRAPER_BACKEND=jina
JINA_API_KEY=optional_for_higher_limits
```

#### 2. Browserbase
- **Pros**: Full browser, JavaScript support
- **Cons**: Requires API key, slower
- **Best for**: SPAs, dynamic content, social media

```bash
SCRAPER_BACKEND=browserbase
BROWSERBASE_API_KEY=your_key
BROWSERBASE_PROJECT_ID=your_project
```

### Chunking Strategy

Content is intelligently chunked:

```python
scraper = WebScraperIntegration(
    memory_store,
    chunk_size=1000,      # Max chars per chunk
    chunk_overlap=200     # Overlap between chunks
)
```

**Chunking rules:**
1. Prefer paragraph breaks (`\n\n`)
2. Fall back to sentence breaks (`. `)
3. Hard break at `chunk_size`
4. Overlap maintains context continuity

### Example: Competitor Research

```python
from nanowork_mobile.memory import get_scraper_integration

scraper = get_scraper_integration()

# Scrape multiple competitor pages
competitors = [
    "https://competitor1.com/pricing",
    "https://competitor2.com/features",
    "https://competitor3.com/about",
]

for url in competitors:
    docs = await scraper.scrape_and_store(
        url=url,
        namespace="user_123",
        metadata={"purpose": "competitor_analysis"}
    )
    print(f"Stored {len(docs)} chunks from {url}")

# Search all scraped content
results = await scraper.search_scraped_content(
    query="competitor pricing strategies",
    namespace="user_123",
    limit=10
)

for result in results:
    url = result.document.metadata["url"]
    print(f"{result.score:.2f} | {url}")
    print(f"  {result.document.content[:150]}...\n")
```

---

## Advanced Features

### Multi-Provider Embedding

Switch providers dynamically:

```python
from nanowork_mobile.memory import EmbeddingService, EmbeddingProvider

# Voyage AI (best quality)
voyage = EmbeddingService(provider=EmbeddingProvider.VOYAGE)
embedding = await voyage.embed_text("High quality embedding")

# OpenAI (widely available)
openai_service = EmbeddingService(provider=EmbeddingProvider.OPENAI)
embedding = await openai_service.embed_text("OpenAI embedding")

# Local (offline, free)
local = EmbeddingService(provider=EmbeddingProvider.LOCAL)
embedding = await local.embed_text("Local embedding")
```

### Namespace Isolation

Namespaces provide data isolation:

```python
# Per-user namespace
await memory.store_document(
    content="User A's data",
    namespace="user_A",
    source="user_memory"
)

await memory.store_document(
    content="User B's data",
    namespace="user_B",
    source="user_memory"
)

# Search only sees own namespace
results_a = await memory.search("data", namespace="user_A")
# Returns only User A's data

# Global namespace for shared knowledge
await memory.store_document(
    content="Industry best practices",
    namespace="global",
    source="business_knowledge"
)
```

### Metadata Filtering

Rich metadata enables complex queries:

```python
# Store with detailed metadata
await memory.store_document(
    content="Competitor uses freemium model",
    namespace="user_123",
    metadata={
        "competitor_name": "Acme Corp",
        "url": "https://acme.com/pricing",
        "confidence": 0.95,
        "date_scraped": "2026-05-08",
        "tags": ["pricing", "competitor", "freemium"]
    },
    source="web_scrape"
)

# Search with source filter
results = await memory.search(
    query="freemium pricing",
    namespace="user_123",
    source_filter="web_scrape"  # Only scraped content
)
```

### Conversation Context Window

Get relevant context for multi-turn conversations:

```python
# Store multiple turns
for turn in range(10):
    await memory.store_conversation_turn(
        user_id="user123",
        user_message=f"Turn {turn} user message",
        assistant_message=f"Turn {turn} assistant response",
        metadata={"turn": turn}
    )

# Get context for current query
context = await memory.get_conversation_context(
    user_id="user123",
    query="pricing discussion",
    limit=5  # Top 5 most relevant turns
)

# Use context in prompt
from nanowork_mobile.llm_client import chat

response = await chat([
    {"role": "user", "content": f"{context}\n\nUser: {current_message}"}
])
```

---

## Performance & Scaling

### Embedding Performance

| Provider | Dimension | Latency | Cost | Quality |
|----------|-----------|---------|------|---------|
| **Voyage-3** | 1024 | 100-200ms | $0.10/1M tokens | ⭐⭐⭐⭐⭐ |
| **OpenAI small** | 1536 | 150-300ms | $0.02/1M tokens | ⭐⭐⭐⭐ |
| **Local** | 384 | 20-50ms (CPU) | Free | ⭐⭐⭐ |

**Recommendation**: Voyage-3 for production, Local for development

### Search Performance

With HNSW index:
- **< 10ms** for queries on 10K vectors
- **< 50ms** for queries on 100K vectors
- **< 200ms** for queries on 1M vectors

### Scaling Guidelines

| Scale | Vectors | RAM | Index | Notes |
|-------|---------|-----|-------|-------|
| Small | < 10K | 2 GB | HNSW m=16 | Single instance |
| Medium | 10K-100K | 4 GB | HNSW m=24 | Vertical scaling |
| Large | 100K-1M | 8 GB | HNSW m=32 | Consider partitioning |
| Enterprise | > 1M | 16+ GB | Multiple indexes | Namespace-based sharding |

### Optimization Tips

1. **Batch Embeddings**
   ```python
   # Inefficient: 100 API calls
   for text in texts:
       await service.embed_text(text)

   # Efficient: 1 API call
   embeddings = await service.embed_batch(texts)
   ```

2. **Index Tuning**
   ```sql
   -- Higher m = better recall, slower build
   CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)
   WITH (m = 32, ef_construction = 128);
   ```

3. **Namespace Partitioning**
   - Keep per-user namespaces
   - Use global for shared knowledge
   - Clean up old namespaces

4. **Memory Cleanup**
   ```python
   # Run periodically (cron job)
   await memory.supabase.rpc("cleanup_old_memories", {
       "days_old": 90,
       "exclude_sources": ["user_preference"]
   }).execute()
   ```

---

## Troubleshooting

### "Embedding service unavailable"

**Solution:**
```bash
# Check API key
echo $VOYAGE_API_KEY

# Fall back to local
export EMBEDDING_PROVIDER=local

# Test connection
python -c "from nanowork_mobile.memory import embed_text; import asyncio; print(asyncio.run(embed_text('test')))"
```

### "Vector dimension mismatch"

**Problem**: Changing embedding providers mid-project

**Solution:**
```sql
-- Recreate table with new dimension
ALTER TABLE vector_memory 
ALTER COLUMN embedding TYPE vector(384);  -- For local model

-- Reindex
REINDEX INDEX idx_vector_memory_embedding_hnsw;
```

### "Slow search queries"

**Solution:**
```sql
-- Check index usage
EXPLAIN ANALYZE 
SELECT * FROM vector_memory 
ORDER BY embedding <=> '[0.1, 0.2, ...]' 
LIMIT 10;

-- Rebuild index if needed
REINDEX INDEX idx_vector_memory_embedding_hnsw;

-- Or increase HNSW parameters
DROP INDEX idx_vector_memory_embedding_hnsw;
CREATE INDEX idx_vector_memory_embedding_hnsw ON vector_memory
USING hnsw (embedding vector_cosine_ops)
WITH (m = 48, ef_construction = 256);  -- More accurate, slower
```

---

## Next Steps

1. **Run migrations**: `python scripts/run_migrations.py`
2. **Test setup**: `pytest tests/test_vector_memory.py -v`
3. **Try examples**: See [Usage Examples](#usage-examples)
4. **Deploy**: Add memory endpoints to your API
5. **Monitor**: Check `/memory/stats` endpoint

For more help:
- 📧 Email: engineering@nanowork.ai
- 📝 Issues: GitHub with [vector-memory] tag
- 📚 API Docs: `/docs` (FastAPI auto-docs)
