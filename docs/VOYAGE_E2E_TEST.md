# Voyage AI E2E Test Guide

This guide documents the end-to-end testing procedure for Voyage AI embedding provider integration.

## Prerequisites

1. **Voyage AI API Key**: You need a valid Voyage AI API key from https://www.voyageai.com/
2. **PostgreSQL Database**: Running database with agent_messages table
3. **API Server**: FastAPI server (src/glp/assignment/app.py)

## Test Setup

### 1. Configure Environment Variables

Add the following to your `.env` file:

```bash
# Voyage AI Configuration
VOYAGE_API_KEY=pa-your-actual-voyage-api-key
VOYAGE_EMBEDDING_MODEL=voyage-2  # or voyage-large-2, voyage-code-2, voyage-lite-02-instruct
EMBEDDING_PROVIDER=voyageai  # or 'voyage' (both work)

# Ensure you have database configured
DATABASE_URL=postgresql://glp:password@localhost:5432/greenlake

# Optional: Disable auth for testing
REQUIRE_AUTH=false
DISABLE_AUTH=true
```

### 2. Verify VoyageAI Package is Installed

```bash
# Check if voyageai is installed
python -c "import voyageai; print('VoyageAI package available')"

# If not installed, add it:
uv add voyageai
# or
pip install voyageai
```

### 3. Verify Provider Implementation

```bash
# Verify VoyageAIProvider can be imported
python -c "from src.glp.agent.providers.voyageai import VoyageAIProvider, VOYAGEAI_AVAILABLE; print(f'Available: {VOYAGEAI_AVAILABLE}')"

# Verify it's exported from agent module
python -c "from src.glp.agent import VoyageAIProvider; print('Export OK')"
```

## E2E Test Procedure

### Step 1: Start the API Server

```bash
# Terminal 1: Start the API server
uv run uvicorn src.glp.assignment.app:app --reload --port 8000

# Expected log output should include:
# INFO:src.glp.assignment.app:Using Voyage AI embedding provider: voyage-2
```

**Verification Checkpoint 1**: Check the startup logs for:
- ✅ "Using Voyage AI embedding provider: {model_name}"
- ❌ If you see "Falling back to OpenAI", check VOYAGE_API_KEY and EMBEDDING_PROVIDER

### Step 2: Send a Chat Message via API

```bash
# Terminal 2: Send a test chat message
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What devices are currently active?",
    "conversation_id": null
  }'
```

Expected response:
```json
{
  "response": "...",
  "conversation_id": "uuid-...",
  "message_id": "uuid-...",
  "model": "claude-sonnet-4-5-20250929"
}
```

**Verification Checkpoint 2**: Chat response received successfully

### Step 3: Verify Embedding Worker Processes Message

Monitor the API server logs (Terminal 1) for embedding worker activity:

```
INFO:src.glp.agent.memory.semantic:Processing embedding for message: msg-xxx
INFO:src.glp.agent.memory.semantic:Embedding generated: model=voyage-2, dim=1024
```

Expected log patterns:
- ✅ "Processing embedding for message: {message_id}"
- ✅ "Embedding generated: model=voyage-2, dim=1024" (or 1536 for voyage-large-2)
- ❌ If logs show "model=text-embedding-3-large", Voyage AI is NOT being used

**Verification Checkpoint 3**: Embedding worker logs show Voyage AI model

### Step 4: Check Database for Embeddings

```bash
# Connect to PostgreSQL
psql $DATABASE_URL

# Query agent_messages table
SELECT
    id,
    role,
    content,
    embedding_model,
    vector_length(embedding) as embedding_dimension,
    created_at
FROM agent_messages
ORDER BY created_at DESC
LIMIT 5;
```

Expected output:
```
                  id                  | role | content | embedding_model | embedding_dimension | created_at
--------------------------------------+------+---------+-----------------+---------------------+------------
 msg-uuid-xxx                        | user | What... | voyage-2        | 1024                | 2026-01-14...
```

**Verification Checkpoint 4**: Database confirmation
- ✅ `embedding_model` column shows "voyage-2" (or your configured model)
- ✅ `embedding_dimension` matches expected:
  - voyage-2: 1024
  - voyage-large-2: 1536
  - voyage-code-2: 1536
  - voyage-lite-02-instruct: 1024
- ❌ If `embedding_model` is "text-embedding-3-large", Voyage AI failed

### Step 5: Verify Semantic Search

```bash
# Send a follow-up message that should trigger semantic search
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Tell me more about those devices",
    "conversation_id": "uuid-from-step-2"
  }'
```

Monitor logs for semantic search activity:
```
INFO:src.glp.agent.memory.semantic:Searching for similar messages: query="Tell me more..."
INFO:src.glp.agent.memory.semantic:Found 3 similar messages (similarity > 0.7)
```

**Verification Checkpoint 5**: Semantic search with Voyage AI embeddings
- ✅ Search logs appear in API server
- ✅ Similar messages are found
- ✅ Response incorporates conversation context

### Step 6: Test Provider Fallback (Optional)

Test that fallback to OpenAI works when Voyage AI fails:

```bash
# Stop the API server (Ctrl+C)

# Temporarily break Voyage AI (invalid key)
export VOYAGE_API_KEY=invalid-key-test
export EMBEDDING_PROVIDER=voyageai

# Restart API server
uv run uvicorn src.glp.assignment.app:app --reload --port 8000
```

Expected log output:
```
WARNING:src.glp.assignment.app:Failed to initialize Voyage AI embedding provider: ...
INFO:src.glp.assignment.app:Falling back to OpenAI embeddings...
INFO:src.glp.assignment.app:Using OpenAI embedding provider: text-embedding-3-large
```

**Verification Checkpoint 6**: Automatic fallback to OpenAI
- ✅ Warning logged about Voyage AI failure
- ✅ Fallback to OpenAI announced
- ✅ API server continues to work with OpenAI embeddings

## Expected Results Summary

### ✅ Success Criteria

1. **Provider Selection**: API server logs confirm Voyage AI provider initialization
2. **Chat Functionality**: Messages can be sent and responses received
3. **Embedding Generation**: Logs show embeddings generated with Voyage AI model
4. **Database Storage**: `agent_messages` table contains embeddings with correct model name and dimensions
5. **Semantic Search**: Follow-up queries successfully find similar messages
6. **Fallback Logic**: System falls back to OpenAI when Voyage AI is unavailable

### ❌ Failure Indicators

1. Logs show "Falling back to OpenAI" without invalid configuration
2. Database shows `embedding_model=text-embedding-3-large` instead of Voyage model
3. Embedding dimensions don't match expected values (1024 or 1536 for Voyage)
4. API server fails to start with Voyage AI configured
5. Semantic search returns no results or errors

## Troubleshooting

### Issue: "VOYAGE_API_KEY not configured"

**Cause**: Environment variable not set or not loaded

**Solution**:
```bash
# Verify .env file has the key
grep VOYAGE_API_KEY .env

# Restart API server to reload environment
```

### Issue: "voyageai package is required"

**Cause**: voyageai Python package not installed

**Solution**:
```bash
uv add voyageai
# or
pip install voyageai
```

### Issue: "Invalid EMBEDDING_PROVIDER"

**Cause**: Typo in EMBEDDING_PROVIDER value

**Solution**: Must be exactly "voyageai", "voyage", or "openai" (case-insensitive)

### Issue: Embeddings still use OpenAI model

**Cause**: Provider initialization failed silently

**Solution**: Check API server startup logs for specific error messages

### Issue: "Rate limited" errors

**Cause**: Voyage AI API rate limits exceeded

**Solution**:
- Use voyage-lite-02-instruct model (higher rate limits)
- Add retry logic
- Reduce batch sizes

## Model Selection Guide

Choose your Voyage AI model based on requirements:

| Model | Dimensions | Use Case | Cost |
|-------|------------|----------|------|
| voyage-2 | 1024 | General purpose, balanced | $$ |
| voyage-large-2 | 1536 | Highest quality, enterprise | $$$ |
| voyage-code-2 | 1536 | Code and technical docs | $$$ |
| voyage-lite-02-instruct | 1024 | High throughput, budget | $ |

**Note**: All Voyage models use the same API endpoint and client, only the model name changes.

## Performance Benchmarks

Expected performance (compared to OpenAI text-embedding-3-large):

- **Latency**: 20-30% faster for large batches
- **Cost**: 60-70% cheaper per 1M tokens
- **Storage**: 66% less disk space (1024 vs 3072 dimensions for base models)
- **Quality**: Comparable or better for retrieval tasks

## Migration Considerations

If you have existing embeddings with OpenAI:

1. **Dimension Mismatch**: Voyage (1024) ≠ OpenAI (3072)
   - Cannot directly compare embeddings from different models
   - Need to re-embed existing messages
   - See `docs/EMBEDDING_MIGRATION.md` for migration strategies

2. **Database Schema**: No changes required
   - `embedding` column is `vector(3072)` - supports both sizes
   - `embedding_model` column tracks which model was used
   - `embedding_dimension` can be calculated with `vector_length(embedding)`

3. **Search Compatibility**: Queries only search within same embedding model
   - Filter by `embedding_model` in semantic search
   - Or re-embed all messages to single provider

## Cleanup

After testing, restore your environment:

```bash
# Stop API server (Ctrl+C in Terminal 1)

# Optional: Clear test messages from database
psql $DATABASE_URL -c "DELETE FROM agent_messages WHERE created_at > NOW() - INTERVAL '1 hour';"

# Optional: Switch back to OpenAI
# Edit .env and set:
# EMBEDDING_PROVIDER=openai
```

## Status

**Test Status**: ⚠️ **Manual Verification Required**

**Reason**: No VOYAGE_API_KEY available in current environment

**To Complete**:
1. Obtain Voyage AI API key from https://www.voyageai.com/
2. Add to `.env` file
3. Follow this guide to perform E2E test
4. Document results in build-progress.txt

## Automated Test Alternative

If you cannot obtain a Voyage AI API key, the following automated tests provide coverage:

```bash
# Unit tests for VoyageAI provider
pytest tests/agent/test_voyageai_embedding.py -v

# Provider selection and fallback tests
pytest tests/agent/test_provider_factory.py -v

# All embedding-related tests
pytest tests/agent/ -v -k embedding
```

These tests use mocks and don't require actual API keys, but don't verify end-to-end behavior with real Voyage AI API.
