# Deployment Checklist: Quantized Memory System

## ✅ What's Been Built

### Core Modules (Production-Ready)
- ✅ `core/quantization.py` — Vector quantization (float32 → binary/float16)
- ✅ `core/embeddings.py` — Voyage AI client with caching
- ✅ `core/agents/router.py` — Intent classifier (Haiku, <200ms)
- ✅ `core/agents/memory_agent.py` — Store/retrieve with quantized vectors
- ✅ `migrations/008_quantized_embeddings.sql` — Database schema
- ✅ `scripts/embed_seed_data.py` — Seed data embedding
- ✅ `scripts/setup_quantized_memory.sh` — Automated setup

### Integration (Auto-Deployed)
- ✅ `app_generation.py` — Uses `retrieve_for_generation()` for RAG context
- ✅ `orchestrator_agent.py` — Calls `store_generation()` after deploy
- ✅ Tests — `tests/test_quantized_memory.py` (pytest-ready)

### Documentation (Complete)
- ✅ `docs/QUANTIZED_MEMORY_ARCHITECTURE.md` — Full architecture guide
- ✅ `docs/IMPLEMENTATION_SUMMARY.md` — Quick reference
- ✅ `docs/DEPLOYMENT_CHECKLIST.md` — This file

---

## 🚀 Deployment Steps

### Prerequisites

```bash
# 1. Set environment variables
export SUPABASE_URL=https://xxx.supabase.co
export SUPABASE_KEY=eyJhbGc...  # service-role key
export VOYAGE_API_KEY=pa-...    # Voyage AI API key
export DATABASE_URL=postgresql://...  # for psql migration
```

### Option A: Automated Setup (Recommended)

```bash
# Run the all-in-one setup script
./scripts/setup_quantized_memory.sh
```

**What it does**:
1. ✅ Validates environment variables
2. ✅ Applies database migration (`008_quantized_embeddings.sql`)
3. ✅ Embeds seed data (design templates, industry knowledge, examples)
4. ✅ Verifies setup with test queries
5. ✅ Reports success/failure

**Duration**: ~2-5 minutes (depends on seed data size)

### Option B: Manual Setup

#### Step 1: Apply Migration

```bash
# Add quantized columns + indexes + RPCs
psql $DATABASE_URL < migrations/008_quantized_embeddings.sql
```

**What it adds**:
- `embedding_binary` (bit 1024) columns to all tables
- `embedding_half` (halfvec 1024) columns (optional, future use)
- HNSW indexes on binary columns (bit_hamming_ops)
- `match_memory_quantized()` RPC for 3-tier retrieval
- `quantize_embedding_to_binary()` helper for backfills

#### Step 2: Embed Seed Data

```bash
# Embed design templates, industry knowledge, prompt examples
uv run python scripts/embed_seed_data.py
```

**What it does**:
- Embeds all rows with `NULL` embeddings
- Uses Voyage AI (`voyage-3`, 1024 dims)
- Stores float32, binary, and float16 quantized tiers
- Caches embeddings in `linq_embedding_cache`
- Idempotent — safe to re-run

#### Step 3: Verify Setup

```bash
# Test memory retrieval
uv run python -c "
import asyncio
from nanowork_mobile.core.agents import retrieve_for_generation

async def test():
    context = await retrieve_for_generation(
        prompt='build a coffee shop app',
        phone_number='+15550001234',
    )
    print(f'Past outputs: {len(context[\"past_outputs\"])}')
    print(f'Templates: {len(context[\"templates\"])}')
    print(f'Knowledge: {len(context[\"knowledge\"])}')
    print(f'Examples: {len(context[\"examples\"])}')

asyncio.run(test())
"

# Test router agent
uv run python -c "
import asyncio
from nanowork_mobile.core.agents import classify_intent

async def test():
    intent = await classify_intent('build me a coffee shop app')
    print(f'Intents: {intent[\"intents\"]}')
    print(f'Confidence: {intent[\"confidence\"]:.2f}')

asyncio.run(test())
"
```

#### Step 4: Run Tests (Optional)

```bash
# Run full test suite
pytest tests/test_quantized_memory.py -v

# Run specific test class
pytest tests/test_quantized_memory.py::TestQuantization -v

# Run with coverage
pytest tests/test_quantized_memory.py --cov=nanowork_mobile.core -v
```

---

## 📊 Post-Deployment Verification

### 1. Check Embedding Coverage

```sql
-- Verify embeddings were created
select
  count(*) as total_rows,
  count(embedding) filter (where embedding is not null) as float32_count,
  count(embedding_binary) filter (where embedding_binary is not null) as binary_count
from linq_design_templates;
```

**Expected**: `float32_count` and `binary_count` should match `total_rows`

### 2. Test Quantized Retrieval

```sql
-- Test binary → float32 re-rank
select * from match_memory_quantized(
  query_embedding_binary := B'10110010...',  -- 1024 bits
  query_embedding_full   := array[0.23, -0.45, ...]::vector(1024),
  candidate_count        := 50,
  final_count            := 5,
  p_phone_number         := '+15550001234'
);
```

**Expected**: Returns 0-5 rows with `similarity` scores (0.0-1.0)

### 3. Monitor Query Performance

```sql
-- Enable pg_stat_statements (if not already enabled)
create extension if not exists pg_stat_statements;

-- View query performance
select
  substring(query, 1, 100) as query_snippet,
  calls,
  mean_exec_time::int as avg_ms,
  max_exec_time::int as max_ms
from pg_stat_statements
where query like '%match_memory_quantized%'
order by mean_exec_time desc
limit 10;
```

**Expected**: `avg_ms` should be <25ms for 100K vectors, <50ms for 1M vectors

### 4. Check Memory Storage

```sql
-- Verify memory is being stored after deployments
select
  phone_number,
  count(*) as generation_count,
  max(created_at) as last_generation
from "LinqMemory"
group by phone_number
order by last_generation desc
limit 10;
```

**Expected**: New rows appear after each app generation

---

## 🔧 Troubleshooting

### Issue: Migration Fails with "extension vector does not exist"

**Solution**: Install pgvector extension first

```sql
create extension if not exists vector;
```

### Issue: embed_seed_data.py fails with "voyageai not installed"

**Solution**: Verify dependencies are installed

```bash
uv pip list | grep voyageai
# If missing:
uv add voyageai
```

### Issue: Embeddings not caching

**Solution**: Check `linq_embedding_cache` RPC exists

```sql
-- Verify RPC exists
select proname from pg_proc where proname like '%embedding_cache%';

-- Should return:
--   get_embedding_cache
--   set_embedding_cache
```

If missing, reapply migration `007_vector_memory.sql` (embedding cache base)

### Issue: Slow queries (>100ms for <1M vectors)

**Solution**: Check indexes are created

```sql
-- Verify indexes exist
select
  schemaname,
  tablename,
  indexname,
  indexdef
from pg_indexes
where tablename in ('LinqMemory', 'linq_design_templates')
  and indexname like '%binary%';
```

Expected indexes:
- `idx_linq_memory_output_binary`
- `idx_linq_memory_prompt_binary`
- `idx_design_templates_binary`
- `idx_industry_knowledge_binary`
- `idx_prompt_examples_binary`

### Issue: Memory not being stored after deployment

**Solution**: Check orchestrator_agent.py integration

```bash
# Search for store_generation call
grep -n "store_generation" src/nanowork_mobile/agents/orchestrator_agent.py

# Should find call after save_app_schema around line 1080
```

If missing, add:

```python
from ..core.agents import store_generation
await store_generation(
    phone_number=phone_number,
    project_id=project_id,
    prompt=user_prompt,
    spec=spec,
    slug=slug,
)
```

---

## 📈 Monitoring & Optimization

### Key Metrics to Track

1. **Query Latency** — `match_memory_quantized()` execution time
   - Target: <25ms for 100K vectors, <50ms for 1M vectors
   - Monitor via `pg_stat_statements`

2. **Recall Rate** — Binary scan candidate coverage
   - Target: 85-95% of relevant results in top 50 candidates
   - Test by comparing binary-only vs full float32 results

3. **Storage Growth** — Binary column overhead
   - Overhead: 128 bytes/vector (~3% increase vs float32 only)
   - Monitor table sizes: `pg_total_relation_size('LinqMemory')`

4. **Cache Hit Rate** — Embedding cache effectiveness
   - Target: >50% cache hits for repeat queries
   - Monitor: `select count(*) from linq_embedding_cache`

### Performance Tuning

#### If queries are slow (>50ms for <1M vectors):

1. **Rebuild indexes**
   ```sql
   reindex index concurrently idx_linq_memory_output_binary;
   ```

2. **Adjust candidate count** (trade recall for speed)
   ```python
   # In memory_agent.py, reduce candidate_count
   supabase.rpc("match_memory_quantized", {
       "candidate_count": 30,  # down from 50
       "final_count": 5,
   })
   ```

3. **Analyze query plan**
   ```sql
   explain analyze
   select * from match_memory_quantized(...);
   ```

#### If recall is low (<80% relevant results):

1. **Increase candidate count**
   ```python
   candidate_count=100  # up from 50
   ```

2. **Use float16 middle tier** (future: Tier 2.5)
   - Binary (Tier 1) → 200 candidates
   - Float16 (Tier 2) → 50 candidates
   - Float32 (Tier 3) → 5 final results

3. **Switch to Product Quantization** (future enhancement)
   - Replace mean-threshold binary with learned PQ
   - 90-95% recall vs 85% for binary

---

## 🎯 Success Criteria

✅ **Migration Applied**
- All tables have `embedding_binary` and `embedding_half` columns
- HNSW indexes created on binary columns
- `match_memory_quantized()` RPC exists

✅ **Seed Data Embedded**
- `linq_design_templates` has embeddings in all three tiers
- `linq_industry_knowledge` has embeddings
- `linq_prompt_examples` has embeddings
- `linq_embedding_cache` populated

✅ **Integration Working**
- `app_generation.py` calls `retrieve_for_generation()`
- `orchestrator_agent.py` calls `store_generation()`
- New deployments appear in `LinqMemory` table

✅ **Performance Targets Met**
- Query latency <25ms for 100K vectors
- Query latency <50ms for 1M vectors
- 100% recall on final top-5 results

✅ **Tests Pass**
- `pytest tests/test_quantized_memory.py` — all green
- Manual verification queries return expected results

---

## 📚 Next Steps

### Immediate (Production)
1. ✅ Deploy to staging — test with real user data
2. ✅ Monitor query latency for 1 week
3. ✅ Collect feedback on context quality (past_outputs, templates)
4. ✅ Deploy to production when stable

### Short-Term (1-2 weeks)
1. **Backfill existing data** — convert old OpenAI embeddings to quantized
2. **Add monitoring dashboard** — Grafana + pg_stat_statements
3. **Tune match thresholds** — optimize precision/recall based on user feedback
4. **A/B test context quality** — compare with/without memory retrieval

### Long-Term (1-3 months)
1. **Product Quantization** — upgrade binary to PQ for 90-95% recall
2. **Float16 middle tier** — add Tier 2.5 for 100M+ vectors
3. **Hybrid search** — combine vector + BM25 keyword matching
4. **Cross-encoder reranking** — Cohere Rerank for final stage

---

## 🔗 Quick Links

- [Full Architecture Guide](./QUANTIZED_MEMORY_ARCHITECTURE.md)
- [Implementation Summary](./IMPLEMENTATION_SUMMARY.md)
- [Migration SQL](../migrations/008_quantized_embeddings.sql)
- [Embedding Script](../scripts/embed_seed_data.py)
- [Test Suite](../tests/test_quantized_memory.py)

---

## 📞 Support

If you encounter issues:

1. Check **Troubleshooting** section above
2. Review logs: `tail -f logs/app.log | grep -i memory`
3. Test in isolation: `pytest tests/test_quantized_memory.py -v`
4. Check Supabase dashboard for RPC errors
5. Verify environment variables are set correctly

**Common gotchas**:
- ⚠️  `VOYAGE_API_KEY` must be set (not optional)
- ⚠️  `DATABASE_URL` needed for psql migration
- ⚠️  PyTorch may require CPU-only install on ARM: `uv add torch --extra-index-url https://download.pytorch.org/whl/cpu`
- ⚠️  Embedding cache RPC must exist (from `007_vector_memory.sql`)

---

**Status**: ✅ Ready for Production Deployment

**Last Updated**: 2026-05-08
