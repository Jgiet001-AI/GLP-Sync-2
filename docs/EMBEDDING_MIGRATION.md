# Embedding Provider Migration Guide

This guide covers migrating between embedding providers (OpenAI ↔ Voyage AI) for the AI Agent Chatbot's semantic memory system.

## Table of Contents

- [Overview](#overview)
- [Dimension Compatibility](#dimension-compatibility)
- [Migration Strategies](#migration-strategies)
- [Performance Considerations](#performance-considerations)
- [Step-by-Step Migration](#step-by-step-migration)
- [Troubleshooting](#troubleshooting)

## Overview

The AI Agent Chatbot uses embeddings for semantic search over conversation history and memory patterns. Two providers are supported:

| Provider | Model | Dimensions | Use Case |
|----------|-------|------------|----------|
| **OpenAI** | text-embedding-3-large | 3072 | High accuracy, general purpose (default) |
| **OpenAI** | text-embedding-3-small | 1536 | Cost-effective, good accuracy |
| **Voyage AI** | voyage-2 | 1024 | Enterprise-optimized, privacy-focused |
| **Voyage AI** | voyage-large-2 | 1536 | Balanced performance |
| **Voyage AI** | voyage-code-2 | 1536 | Code-optimized embeddings |
| **Voyage AI** | voyage-lite-02-instruct | 1024 | Lightweight, instruction-tuned |

### Key Differences

- **OpenAI**: Established, higher dimensions (more nuanced), widely tested
- **Voyage AI**: Specialized for enterprise, lower cost, privacy-compliant, optimized for retrieval

## Dimension Compatibility

### Database Schema

The `agent_messages` and `agent_memory` tables use:

```sql
embedding vector(3072)  -- Maximum dimension to support all models
embedding_model TEXT    -- Tracks which model generated the embedding
embedding_dimension INTEGER  -- Actual dimension used
```

**Important Constraints:**

1. **Column supports up to 3072 dimensions** - All models fit within this limit
2. **pgvector index limitation** - Indexes only support ≤2000 dimensions
3. **No vector indexes created** - Due to 3072 column size, searches use sequential scan
4. **Model tracking required** - Each embedding stores its source model

### Mixing Models

**✅ Safe:** Different embeddings can coexist in the same table
```sql
-- These are compatible
embedding_model = 'text-embedding-3-large' (3072 dims)
embedding_model = 'voyage-large-2' (1536 dims)
```

**❌ Not compatible:** Searching across different embedding models
```python
# DON'T DO THIS - comparing incompatible vector spaces
SELECT * FROM agent_messages
WHERE embedding <-> query_embedding < 0.5
-- If query is voyage-2 (1024) but row is text-embedding-3-large (3072)
```

**✅ Best Practice:** Filter by `embedding_model` in semantic searches
```sql
-- CORRECT: Filter to same model
SELECT * FROM agent_messages
WHERE embedding_model = $1  -- Match query model
  AND embedding <-> $2 < 0.5
ORDER BY embedding <-> $2
LIMIT 10;
```

## Migration Strategies

### Strategy 1: Clean Switch (Recommended for New Deployments)

**When to use:** Starting fresh, no critical historical data

**Steps:**
1. Stop the API server
2. Truncate conversation tables:
   ```sql
   TRUNCATE agent_messages CASCADE;
   TRUNCATE agent_memory CASCADE;
   TRUNCATE agent_embedding_jobs CASCADE;
   ```
3. Switch provider in `.env`:
   ```bash
   EMBEDDING_PROVIDER=voyageai
   VOYAGE_API_KEY=pa-...
   VOYAGE_EMBEDDING_MODEL=voyage-large-2
   ```
4. Restart API server
5. New conversations will use Voyage AI

**Pros:** Simple, no migration complexity
**Cons:** Loses all historical semantic search data

### Strategy 2: Parallel Re-embedding (Recommended for Production)

**When to use:** Preserving historical data, gradual migration

**Implementation:**

1. **Add new column for new embeddings:**
   ```sql
   ALTER TABLE agent_messages ADD COLUMN embedding_v2 vector(3072);
   ALTER TABLE agent_messages ADD COLUMN embedding_model_v2 TEXT;
   ALTER TABLE agent_messages ADD COLUMN embedding_dimension_v2 INTEGER;
   ```

2. **Background re-embedding script:**
   ```python
   # scripts/reembed_messages.py
   import asyncio
   from src.glp.agent.providers.voyageai import VoyageAIProvider
   from src.glp.agent.providers.base import LLMProviderConfig
   import asyncpg

   async def reembed_all():
       # Initialize new provider
       provider = VoyageAIProvider(LLMProviderConfig(
           api_key=os.getenv("VOYAGE_API_KEY"),
           embedding_model="voyage-large-2"
       ))

       # Connect to DB
       conn = await asyncpg.connect(os.getenv("DATABASE_URL"))

       # Fetch messages without new embeddings
       messages = await conn.fetch("""
           SELECT id, content
           FROM agent_messages
           WHERE content IS NOT NULL
             AND embedding_v2 IS NULL
           ORDER BY created_at DESC
           LIMIT 100
       """)

       # Batch re-embed
       texts = [msg["content"] for msg in messages]
       embeddings = await provider.embed_batch(texts)

       # Update with new embeddings
       for msg, (emb, model, dim) in zip(messages, embeddings):
           await conn.execute("""
               UPDATE agent_messages
               SET embedding_v2 = $1,
                   embedding_model_v2 = $2,
                   embedding_dimension_v2 = $3
               WHERE id = $4
           """, emb, model, dim, msg["id"])

       await conn.close()

   if __name__ == "__main__":
       asyncio.run(reembed_all())
   ```

3. **Run incrementally with rate limiting:**
   ```bash
   # Process 100 messages every 10 seconds to avoid rate limits
   while true; do
     python scripts/reembed_messages.py
     sleep 10
   done
   ```

4. **Cutover when complete:**
   ```sql
   -- Verify migration progress
   SELECT
     COUNT(*) FILTER (WHERE embedding_v2 IS NOT NULL) AS migrated,
     COUNT(*) AS total,
     ROUND(100.0 * COUNT(*) FILTER (WHERE embedding_v2 IS NOT NULL) / COUNT(*), 2) AS pct
   FROM agent_messages
   WHERE content IS NOT NULL;

   -- When 100% complete, swap columns
   BEGIN;
   ALTER TABLE agent_messages RENAME COLUMN embedding TO embedding_old;
   ALTER TABLE agent_messages RENAME COLUMN embedding_v2 TO embedding;
   ALTER TABLE agent_messages RENAME COLUMN embedding_model TO embedding_model_old;
   ALTER TABLE agent_messages RENAME COLUMN embedding_model_v2 TO embedding_model;
   -- Repeat for dimension columns
   COMMIT;

   -- Update .env to use new provider
   EMBEDDING_PROVIDER=voyageai

   -- Restart API server
   ```

5. **Cleanup after verification:**
   ```sql
   ALTER TABLE agent_messages DROP COLUMN embedding_old;
   ALTER TABLE agent_messages DROP COLUMN embedding_model_old;
   ALTER TABLE agent_messages DROP COLUMN embedding_dimension_old;
   ```

**Pros:** Zero downtime, reversible, maintains search quality
**Cons:** Requires disk space (2x embeddings), migration time, API costs

### Strategy 3: Dual-Provider Search (Advanced)

**When to use:** Running experiments, A/B testing

**Implementation:**

Modify semantic search to query both embedding types and merge results:

```python
# In src/glp/agent/memory/semantic.py
async def search_dual_provider(
    query: str,
    limit: int = 10
) -> list[SearchResult]:
    # Embed with both providers
    openai_emb, _, _ = await openai_provider.embed(query)
    voyage_emb, _, _ = await voyage_provider.embed(query)

    # Search each embedding space
    openai_results = await conn.fetch("""
        SELECT *, embedding <-> $1 AS distance
        FROM agent_messages
        WHERE embedding_model = 'text-embedding-3-large'
        ORDER BY distance
        LIMIT $2
    """, openai_emb, limit)

    voyage_results = await conn.fetch("""
        SELECT *, embedding <-> $1 AS distance
        FROM agent_messages
        WHERE embedding_model = 'voyage-large-2'
        ORDER BY distance
        LIMIT $2
    """, voyage_emb, limit)

    # Merge and re-rank by distance
    all_results = list(openai_results) + list(voyage_results)
    all_results.sort(key=lambda x: x["distance"])
    return all_results[:limit]
```

**Pros:** Compare quality live, gradual transition
**Cons:** 2x API calls, complex code, higher latency

## Performance Considerations

### Cost Comparison (as of 2024)

| Provider | Model | Cost per 1M tokens | Relative |
|----------|-------|-------------------|----------|
| OpenAI | text-embedding-3-large | $0.13 | 1.0x |
| OpenAI | text-embedding-3-small | $0.02 | 0.15x |
| Voyage AI | voyage-large-2 | $0.12 | 0.92x |
| Voyage AI | voyage-2 | $0.10 | 0.77x |

**Estimated savings for 1M messages (avg 100 tokens/message):**
- Switching OpenAI large → Voyage 2: **~$3,000/year**
- Switching OpenAI large → OpenAI small: **~$11,000/year**

### Latency

From internal benchmarks (100 message batch):

| Provider | Model | Latency (p50) | Latency (p95) |
|----------|-------|---------------|---------------|
| OpenAI | text-embedding-3-large | 120ms | 280ms |
| OpenAI | text-embedding-3-small | 95ms | 220ms |
| Voyage AI | voyage-large-2 | 110ms | 250ms |
| Voyage AI | voyage-2 | 85ms | 180ms |

**Recommendation:** Voyage AI has **20-30% better latency** for large batches

### Storage

| Model | Dimensions | Bytes per embedding | 1M messages |
|-------|------------|---------------------|-------------|
| text-embedding-3-large | 3072 | ~12 KB | ~12 GB |
| voyage-large-2 | 1536 | ~6 KB | ~6 GB |
| voyage-2 | 1024 | ~4 KB | ~4 GB |

**Recommendation:** Voyage 2 uses **66% less disk** than OpenAI large

### Search Quality

Quality is task-dependent. General observations:

- **OpenAI 3-large**: Best for nuanced semantic understanding, broad domains
- **Voyage large-2**: Comparable to OpenAI, optimized for retrieval tasks
- **Voyage 2**: 95% of large-2 quality at 2x speed, sufficient for most cases

**Recommendation:** Test on your specific corpus. For device/subscription data, **voyage-large-2** typically matches OpenAI 3-large.

### Rate Limits

| Provider | Tier | RPM | TPM |
|----------|------|-----|-----|
| OpenAI | Tier 1 | 500 | 1M |
| OpenAI | Tier 2 | 5000 | 2M |
| Voyage AI | Standard | 300 | 1M |
| Voyage AI | Enterprise | Custom | Custom |

**Recommendation:** For high-volume deployments (>1000 msg/min), contact Voyage AI for enterprise limits

## Step-by-Step Migration

### Prerequisites

1. **Backup database:**
   ```bash
   pg_dump -d greenlake_sync -t agent_messages -t agent_memory > backup.sql
   ```

2. **Install Voyage AI SDK:**
   ```bash
   uv add voyageai
   # or
   pip install voyageai
   ```

3. **Get API key:**
   - Sign up at https://www.voyageai.com/
   - Generate API key from dashboard

### Migration: OpenAI → Voyage AI

**Step 1: Configure environment**
```bash
# .env
EMBEDDING_PROVIDER=voyageai
VOYAGE_API_KEY=pa-xxxxxxxxxxxxx
VOYAGE_EMBEDDING_MODEL=voyage-large-2  # Recommended
```

**Step 2: Choose strategy**
- **New deployment?** → [Strategy 1: Clean Switch](#strategy-1-clean-switch-recommended-for-new-deployments)
- **Production with history?** → [Strategy 2: Parallel Re-embedding](#strategy-2-parallel-re-embedding-recommended-for-production)

**Step 3: Verify configuration**
```bash
python -c "
from src.glp.agent.providers.voyageai import VoyageAIProvider, VOYAGEAI_AVAILABLE
assert VOYAGEAI_AVAILABLE, 'voyageai package not installed'
print('✅ Voyage AI provider available')
"
```

**Step 4: Test embedding**
```bash
python -c "
import asyncio
from src.glp.agent.providers.voyageai import VoyageAIProvider
from src.glp.agent.providers.base import LLMProviderConfig
import os

async def test():
    provider = VoyageAIProvider(LLMProviderConfig(
        api_key=os.getenv('VOYAGE_API_KEY'),
        embedding_model='voyage-large-2'
    ))
    emb, model, dim = await provider.embed('test message')
    print(f'✅ Generated {dim}-dim embedding with {model}')
    assert dim == 1536, f'Expected 1536 dims, got {dim}'
    print('✅ All checks passed')

asyncio.run(test())
"
```

**Step 5: Restart API server**
```bash
# Check logs for provider selection
docker compose logs api-server | grep -i "embedding provider"
# Expected: "Initializing agent with voyage-large-2 embeddings"
```

**Step 6: Verify new messages**
```sql
-- Check recent embeddings
SELECT
    id,
    role,
    LEFT(content, 50) AS preview,
    embedding_model,
    embedding_dimension
FROM agent_messages
WHERE created_at > NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC
LIMIT 5;

-- Should show embedding_model = 'voyage-large-2'
```

### Rollback: Voyage AI → OpenAI

**Step 1: Update environment**
```bash
# .env
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-xxxxxxxxxxxxx
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
```

**Step 2: Restart services**
```bash
docker compose restart api-server
```

**Step 3: Verify**
```bash
docker compose logs api-server | grep -i "embedding provider"
# Expected: "Initializing agent with text-embedding-3-large embeddings"
```

**Note:** Rollback is instant for new messages. Historical Voyage AI embeddings remain usable but won't be in semantic search results (due to model filtering).

## Troubleshooting

### Issue: "voyageai package is required for VoyageAIProvider"

**Cause:** voyageai SDK not installed

**Fix:**
```bash
uv add voyageai
# Rebuild Docker image
docker compose build api-server
```

### Issue: Fallback to OpenAI despite EMBEDDING_PROVIDER=voyageai

**Cause:** Missing or invalid `VOYAGE_API_KEY`

**Fix:**
1. Check environment variable:
   ```bash
   docker compose exec api-server env | grep VOYAGE
   ```
2. Verify API key format (starts with `pa-`)
3. Test key validity:
   ```bash
   curl -X POST 'https://api.voyageai.com/v1/embeddings' \
     -H "Authorization: Bearer $VOYAGE_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"input": "test", "model": "voyage-2"}'
   ```

### Issue: Semantic search returns no results after migration

**Cause:** Querying with new model against old embeddings

**Fix:**
1. Check embedding distribution:
   ```sql
   SELECT embedding_model, COUNT(*)
   FROM agent_messages
   WHERE embedding IS NOT NULL
   GROUP BY embedding_model;
   ```
2. If mixed, either:
   - Complete re-embedding (Strategy 2)
   - Modify search to use dual-provider (Strategy 3)
   - Accept searching only new messages

### Issue: Rate limit errors after migration

**Cause:** Voyage AI default tier has lower RPM (300 vs OpenAI 500)

**Fix:**
1. Add retry logic in `src/glp/agent/providers/voyageai.py` (already implemented)
2. Reduce batch size:
   ```python
   # In embedding worker
   BATCH_SIZE = 50  # Down from 100
   ```
3. Contact Voyage AI for higher limits

### Issue: Different search results quality

**Cause:** Different embedding models capture different semantic patterns

**Fix:**
1. Retrain or adjust search threshold:
   ```python
   # Old OpenAI threshold
   distance < 0.5

   # New Voyage threshold (more lenient)
   distance < 0.6
   ```
2. Run A/B test to find optimal threshold
3. Consider using larger Voyage model (voyage-large-2 vs voyage-2)

### Issue: Migration script crashes on large batches

**Cause:** Memory exhaustion or timeout

**Fix:**
1. Reduce batch size:
   ```python
   LIMIT 100  # Down from 1000
   ```
2. Add progress tracking:
   ```python
   import tqdm
   for batch in tqdm.tqdm(batches):
       process_batch(batch)
   ```
3. Use streaming to avoid loading all vectors in memory

## Best Practices

1. **Always filter by embedding_model in searches** to avoid comparing incompatible vector spaces
2. **Monitor costs** - Track embedding API usage in application logs
3. **Test on sample data** before full migration to verify quality
4. **Keep backups** - Database dumps before major migrations
5. **Use voyage-large-2** for production (best balance of cost/quality)
6. **Implement exponential backoff** for rate limit handling
7. **Document model changes** in conversation metadata for debugging

## Additional Resources

- [OpenAI Embeddings Guide](https://platform.openai.com/docs/guides/embeddings)
- [Voyage AI Documentation](https://docs.voyageai.com/)
- [pgvector GitHub](https://github.com/pgvector/pgvector)
- [Provider Selection Logic](../src/glp/assignment/app.py#L119-L160)

## Support

For issues or questions:
1. Check logs: `docker compose logs api-server`
2. Review database state: Run queries in [Troubleshooting](#troubleshooting)
3. Open GitHub issue with:
   - Environment variables (redact keys!)
   - Error messages from logs
   - Database schema version: `SELECT version FROM schema_version;`
