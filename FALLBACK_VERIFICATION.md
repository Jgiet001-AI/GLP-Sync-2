# Voyage AI to OpenAI Fallback Verification

This document describes how to verify that the embedding provider correctly falls back from Voyage AI to OpenAI when Voyage AI is unavailable or misconfigured.

## Automated Test Coverage

The fallback behavior is thoroughly tested in `tests/agent/test_provider_factory.py` with the following test cases:

### 1. TestVoyageAIFallbackLogic Class

#### test_fallback_when_voyage_api_key_missing
- **Scenario**: `EMBEDDING_PROVIDER=voyageai` but `VOYAGE_API_KEY` not set
- **Expected**: Falls back to OpenAI provider
- **Verification**: Confirms OpenAIProvider instance is created

#### test_fallback_when_voyage_init_fails
- **Scenario**: `EMBEDDING_PROVIDER=voyageai` with invalid `VOYAGE_API_KEY`
- **Expected**: Voyage AI initialization fails, falls back to OpenAI
- **Verification**: Simulates API key error, confirms OpenAI fallback

#### test_fallback_when_voyageai_not_available
- **Scenario**: voyageai package not installed
- **Expected**: Falls back to OpenAI provider
- **Verification**: Patches VOYAGEAI_AVAILABLE to False, confirms fallback

## Running Automated Tests

```bash
# Run all provider factory tests (includes fallback tests)
pytest tests/agent/test_provider_factory.py -v

# Run only fallback tests
pytest tests/agent/test_provider_factory.py::TestVoyageAIFallbackLogic -v

# Run specific fallback test
pytest tests/agent/test_provider_factory.py::TestVoyageAIFallbackLogic::test_fallback_when_voyage_api_key_missing -v
```

## Manual Verification Steps

If you want to manually verify the fallback behavior in a running system:

### Test 1: Invalid Voyage API Key

1. **Set environment variables**:
   ```bash
   export EMBEDDING_PROVIDER=voyageai
   export VOYAGE_API_KEY=invalid-key-12345
   export OPENAI_API_KEY=your-valid-openai-key
   ```

2. **Start the API server**:
   ```bash
   uvicorn src.glp.assignment.app:app --reload --port 8000
   ```

3. **Expected log output**:
   ```
   WARNING - Failed to initialize Voyage AI embedding provider: [error details]
   INFO - Falling back to OpenAI embeddings...
   INFO - Using OpenAI embedding provider: text-embedding-3-large
   ```

4. **Verification**: Check that the server starts successfully and uses OpenAI

### Test 2: Missing Voyage API Key

1. **Set environment variables**:
   ```bash
   export EMBEDDING_PROVIDER=voyageai
   unset VOYAGE_API_KEY  # Ensure it's not set
   export OPENAI_API_KEY=your-valid-openai-key
   ```

2. **Start the API server**:
   ```bash
   uvicorn src.glp.assignment.app:app --reload --port 8000
   ```

3. **Expected log output**:
   ```
   WARNING - VOYAGE_API_KEY not configured, falling back to OpenAI
   INFO - Using OpenAI embedding provider: text-embedding-3-large
   ```

4. **Verification**: Check that the server starts successfully and uses OpenAI

### Test 3: Voyage Package Not Available

1. **Create a test environment without voyageai package**:
   ```bash
   # In a fresh virtual environment
   pip install fastapi uvicorn openai  # Install everything except voyageai
   ```

2. **Set environment variables**:
   ```bash
   export EMBEDDING_PROVIDER=voyageai
   export VOYAGE_API_KEY=test-key
   export OPENAI_API_KEY=your-valid-openai-key
   ```

3. **Start the API server**:
   ```bash
   uvicorn src.glp.assignment.app:app --reload --port 8000
   ```

4. **Expected log output**:
   ```
   WARNING - VoyageAIProvider not available, falling back to OpenAI
   INFO - Using OpenAI embedding provider: text-embedding-3-large
   ```

5. **Verification**: Check that the server starts successfully and uses OpenAI

## Code Implementation Details

The fallback logic is implemented in `src/glp/assignment/app.py` in the `_init_agent_orchestrator()` function:

```python
# Lines 134-151: Primary provider selection with error handling
if embedding_provider_name == "voyageai" or embedding_provider_name == "voyage":
    voyage_key = os.getenv("VOYAGE_API_KEY")
    if voyage_key and VoyageAIProvider:
        try:
            embedding_config = LLMProviderConfig(...)
            embedding_provider = VoyageAIProvider(embedding_config)
            logger.info(f"Using Voyage AI embedding provider: {embedding_config.embedding_model}")
        except Exception as e:
            logger.warning(f"Failed to initialize Voyage AI embedding provider: {e}")
            logger.info("Falling back to OpenAI embeddings...")
    elif not voyage_key:
        logger.warning("VOYAGE_API_KEY not configured, falling back to OpenAI")
    elif not VoyageAIProvider:
        logger.warning("VoyageAIProvider not available, falling back to OpenAI")

# Lines 154-164: Fallback to OpenAI
if not embedding_provider and openai_key:
    try:
        embedding_config = LLMProviderConfig(...)
        embedding_provider = OpenAIProvider(embedding_config)
        logger.info(f"Using OpenAI embedding provider: {embedding_config.embedding_model}")
    except Exception as e:
        logger.warning(f"Failed to initialize OpenAI embedding provider: {e}")
```

## Acceptance Criteria

- ✅ **Invalid Voyage AI key**: System logs warning and falls back to OpenAI
- ✅ **Missing Voyage API key**: System logs warning and falls back to OpenAI
- ✅ **Voyage package unavailable**: System logs warning and falls back to OpenAI
- ✅ **OpenAI used as fallback**: System successfully initializes with OpenAI provider
- ✅ **Comprehensive logging**: All fallback scenarios logged appropriately
- ✅ **Automated tests**: All fallback scenarios covered by unit tests

## Test Results

Run the tests with:
```bash
pytest tests/agent/test_provider_factory.py::TestVoyageAIFallbackLogic -v
```

Expected output:
```
tests/agent/test_provider_factory.py::TestVoyageAIFallbackLogic::test_fallback_when_voyage_api_key_missing PASSED
tests/agent/test_provider_factory.py::TestVoyageAIFallbackLogic::test_fallback_when_voyage_init_fails PASSED/SKIPPED
tests/agent/test_provider_factory.py::TestVoyageAIFallbackLogic::test_fallback_when_voyageai_not_available PASSED
```

Note: `test_fallback_when_voyage_init_fails` may be skipped if the voyageai package is not installed, which is expected behavior.
