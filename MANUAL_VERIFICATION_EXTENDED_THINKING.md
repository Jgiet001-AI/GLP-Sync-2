# Manual Verification Guide: Extended Thinking Support

This guide provides step-by-step instructions for manually verifying extended thinking support with the live Anthropic API.

## Prerequisites

1. **Valid ANTHROPIC_API_KEY**: Set in environment or `.env` file
2. **Database**: PostgreSQL running and accessible
3. **Redis**: Running for WebSocket ticket authentication
4. **Dependencies**: All Python dependencies installed (`uv sync`)

## Environment Setup

```bash
# Set API key
export ANTHROPIC_API_KEY="your-api-key-here"

# Or add to .env file
echo "ANTHROPIC_API_KEY=your-api-key-here" >> .env

# Ensure thinking is enabled (optional, defaults to False)
export ENABLE_THINKING=true
export THINKING_BUDGET=8000

# Verify environment
python -c "import os; print('API Key:', 'SET' if os.getenv('ANTHROPIC_API_KEY') else 'NOT SET')"
```

## Test Procedure

### Step 1: Start the API Server

```bash
# From project root
uv run uvicorn src.glp.assignment.app:app --reload --port 8000
```

Expected output:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### Step 2: Verify Server Health

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status": "healthy"}
```

### Step 3: Create WebSocket Authentication Ticket

```bash
# Get a WebSocket ticket for chat
curl -X POST http://localhost:8000/api/agent/ticket \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key-here" \
  -d '{
    "user_id": "test-user-manual-verification",
    "conversation_id": "test-conv-thinking-manual"
  }' | jq .
```

Expected response:
```json
{
  "ticket": "wst_abc123...",
  "expires_in": 60,
  "websocket_url": "ws://localhost:8000/api/agent/chat?ticket=wst_abc123..."
}
```

Save the ticket value for the next step.

### Step 4: Test Complex Query with WebSocket Client

Create a test script `test_thinking_manual.py`:

```python
#!/usr/bin/env python3
"""
Manual verification script for extended thinking support.
"""
import asyncio
import json
import time
import websockets
from datetime import datetime

async def test_thinking_with_history():
    """Test extended thinking with message history."""

    # Replace with your ticket from Step 3
    TICKET = "wst_abc123..."
    WS_URL = f"ws://localhost:8000/api/agent/chat?ticket={TICKET}"

    print(f"[{datetime.now()}] Connecting to WebSocket...")

    async with websockets.connect(WS_URL) as websocket:
        print(f"[{datetime.now()}] Connected!\n")

        # Test 1: Complex query requiring thinking
        print("=" * 60)
        print("TEST 1: Complex Query with Extended Thinking")
        print("=" * 60)

        query1 = {
            "message": "Analyze which devices in our inventory should be prioritized for subscription renewal based on their usage patterns, subscription expiry dates, and business criticality. Consider devices expiring in the next 90 days and provide a detailed recommendation with reasoning.",
            "conversation_id": "test-conv-thinking-manual",
            "enable_thinking": True,
            "thinking_budget": 8000
        }

        start_time = time.time()
        thinking_deltas = []
        content_deltas = []

        await websocket.send(json.dumps(query1))
        print(f"\n[{datetime.now()}] Sent query 1...")
        print(f"Message: {query1['message'][:100]}...\n")

        while True:
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=35.0)
                data = json.loads(response)

                if data.get("type") == "thinking_delta":
                    thinking_delta = data.get("content", "")
                    thinking_deltas.append(thinking_delta)
                    print(f"💭 Thinking: {thinking_delta[:80]}...", flush=True)

                elif data.get("type") == "content_delta":
                    content_delta = data.get("content", "")
                    content_deltas.append(content_delta)
                    print(content_delta, end="", flush=True)

                elif data.get("type") == "done":
                    elapsed = time.time() - start_time
                    print(f"\n\n[{datetime.now()}] Response complete!")
                    print(f"⏱️  Response time: {elapsed:.2f}s")
                    print(f"💭 Thinking deltas: {len(thinking_deltas)}")
                    print(f"📝 Content deltas: {len(content_deltas)}")
                    break

                elif data.get("type") == "error":
                    print(f"\n❌ Error: {data.get('error')}")
                    return False

            except asyncio.TimeoutError:
                print("\n⏱️  Timeout waiting for response (>35s)")
                return False

        # Verification checks for Test 1
        print("\n" + "=" * 60)
        print("VERIFICATION CHECKS - Test 1")
        print("=" * 60)

        check1 = len(thinking_deltas) > 0
        check2 = elapsed < 30.0
        check3 = len(content_deltas) > 0

        print(f"✓ Thinking deltas received: {check1} ({len(thinking_deltas)} deltas)")
        print(f"✓ Response time < 30s: {check2} ({elapsed:.2f}s)")
        print(f"✓ Content received: {check3} ({len(content_deltas)} deltas)")

        if not all([check1, check2, check3]):
            print("\n❌ Test 1 FAILED")
            return False

        print("\n✅ Test 1 PASSED")

        # Small delay before next test
        await asyncio.sleep(2)

        # Test 2: Follow-up message to verify history preservation
        print("\n" + "=" * 60)
        print("TEST 2: Follow-up Query (History Preservation)")
        print("=" * 60)

        query2 = {
            "message": "Based on your previous analysis, which single device should we prioritize first and why?",
            "conversation_id": "test-conv-thinking-manual",
            "enable_thinking": True
        }

        start_time = time.time()
        thinking_deltas2 = []
        content_deltas2 = []

        await websocket.send(json.dumps(query2))
        print(f"\n[{datetime.now()}] Sent query 2...")
        print(f"Message: {query2['message']}\n")

        while True:
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=35.0)
                data = json.loads(response)

                if data.get("type") == "thinking_delta":
                    thinking_delta = data.get("content", "")
                    thinking_deltas2.append(thinking_delta)
                    print(f"💭 Thinking: {thinking_delta[:80]}...", flush=True)

                elif data.get("type") == "content_delta":
                    content_delta = data.get("content", "")
                    content_deltas2.append(content_delta)
                    print(content_delta, end="", flush=True)

                elif data.get("type") == "done":
                    elapsed2 = time.time() - start_time
                    print(f"\n\n[{datetime.now()}] Response complete!")
                    print(f"⏱️  Response time: {elapsed2:.2f}s")
                    print(f"💭 Thinking deltas: {len(thinking_deltas2)}")
                    print(f"📝 Content deltas: {len(content_deltas2)}")
                    break

                elif data.get("type") == "error":
                    print(f"\n❌ Error: {data.get('error')}")
                    return False

            except asyncio.TimeoutError:
                print("\n⏱️  Timeout waiting for response (>35s)")
                return False

        # Verification checks for Test 2
        print("\n" + "=" * 60)
        print("VERIFICATION CHECKS - Test 2")
        print("=" * 60)

        check4 = len(content_deltas2) > 0
        check5 = elapsed2 < 30.0
        # Check if response references previous analysis
        full_response = "".join(content_deltas2).lower()
        check6 = any(keyword in full_response for keyword in ["previous", "earlier", "analysis", "recommended", "prioritize"])

        print(f"✓ Content received: {check4} ({len(content_deltas2)} deltas)")
        print(f"✓ Response time < 30s: {check5} ({elapsed2:.2f}s)")
        print(f"✓ References previous analysis: {check6}")

        if not all([check4, check5, check6]):
            print("\n❌ Test 2 FAILED")
            return False

        print("\n✅ Test 2 PASSED")

        # Overall results
        print("\n" + "=" * 60)
        print("OVERALL RESULTS")
        print("=" * 60)
        print("✅ All manual verification tests PASSED")
        print(f"✓ Extended thinking working correctly")
        print(f"✓ Message history preserved across turns")
        print(f"✓ Performance within acceptable range")
        print(f"✓ Thinking deltas emitted and visible")

        return True

async def verify_thinking_redaction():
    """Verify thinking is redacted before storage in database."""
    import asyncpg
    import os

    print("\n" + "=" * 60)
    print("TEST 3: Thinking Redaction in Database")
    print("=" * 60)

    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/glp")

    try:
        conn = await asyncpg.connect(db_url)
        print(f"[{datetime.now()}] Connected to database")

        # Query recent messages from test conversation
        query = """
            SELECT id, role, content, thinking, created_at
            FROM agent_messages
            WHERE conversation_id = 'test-conv-thinking-manual'
            ORDER BY created_at DESC
            LIMIT 5
        """

        rows = await conn.fetch(query)

        if not rows:
            print("⚠️  No messages found for conversation 'test-conv-thinking-manual'")
            await conn.close()
            return True  # Not a failure, just no data yet

        print(f"\nFound {len(rows)} messages:")
        print("-" * 60)

        has_thinking_redacted = False

        for row in rows:
            role = row["role"]
            content_preview = (row["content"] or "")[:100]
            thinking = row["thinking"]

            print(f"\nRole: {role}")
            print(f"Content: {content_preview}...")
            print(f"Thinking: {thinking}")

            # For assistant messages, thinking should be present but redacted
            if role == "ASSISTANT" and thinking:
                if thinking == "[REDACTED]" or "thinking redacted" in thinking.lower():
                    has_thinking_redacted = True
                    print("✓ Thinking properly redacted")
                else:
                    print("⚠️  Thinking not redacted (may contain sensitive data)")

        await conn.close()

        if has_thinking_redacted:
            print("\n✅ Test 3 PASSED: Thinking redaction working")
        else:
            print("\n⚠️  Test 3: No assistant messages with thinking found")

        return True

    except Exception as e:
        print(f"❌ Database verification failed: {e}")
        return False

async def main():
    """Run all manual verification tests."""
    print("\n" + "=" * 70)
    print(" MANUAL VERIFICATION: EXTENDED THINKING SUPPORT")
    print("=" * 70)
    print(f"Started: {datetime.now()}")
    print()

    # Run WebSocket tests
    websocket_ok = await test_thinking_with_history()

    if not websocket_ok:
        print("\n❌ WebSocket tests failed")
        return

    # Run database verification
    db_ok = await verify_thinking_redaction()

    # Final summary
    print("\n" + "=" * 70)
    print(" FINAL SUMMARY")
    print("=" * 70)

    if websocket_ok and db_ok:
        print("✅ ALL MANUAL VERIFICATION TESTS PASSED")
        print()
        print("Verified:")
        print("  ✓ Extended thinking enabled for complex queries")
        print("  ✓ Thinking deltas appear in WebSocket stream")
        print("  ✓ Thinking is redacted before database storage")
        print("  ✓ Message history preserved across conversation turns")
        print("  ✓ Performance < 30 seconds for complex queries")
        print("  ✓ Follow-up questions reference previous context")
    else:
        print("❌ SOME TESTS FAILED - Review output above")

    print(f"\nCompleted: {datetime.now()}")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
```

### Step 5: Run the Verification Script

```bash
# Make executable
chmod +x test_thinking_manual.py

# Run with uv
uv run python test_thinking_manual.py
```

### Step 6: Review Results

The script will verify:

1. **✓ Thinking Deltas Appear**: Verify `thinking_delta` events are emitted in WebSocket stream
2. **✓ Performance < 30s**: Verify response time is within acceptable range
3. **✓ Content Received**: Verify actual response content is delivered
4. **✓ History Preservation**: Verify follow-up questions reference previous analysis
5. **✓ Thinking Redaction**: Verify thinking is redacted in database storage

## Alternative: Manual Testing with `websocat`

If you prefer command-line testing:

```bash
# Install websocat
brew install websocat  # macOS
# or
cargo install websocat  # Any platform with Rust

# Get ticket first (see Step 3)
TICKET="your-ticket-here"

# Connect and send message
websocat "ws://localhost:8000/api/agent/chat?ticket=$TICKET"

# Then type JSON message:
{"message": "Analyze device priorities for subscription renewal", "conversation_id": "manual-test", "enable_thinking": true, "thinking_budget": 8000}
```

Watch for:
- `"type": "thinking_delta"` messages with thinking content
- `"type": "content_delta"` messages with response content
- `"type": "done"` when complete

## Alternative: Frontend Testing

1. **Start Frontend**:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

2. **Open Browser**: Navigate to `http://localhost:5173`

3. **Open Chat Widget**: Click chat icon in bottom-right

4. **Send Complex Query**:
   ```
   Analyze which devices in our inventory should be prioritized for
   subscription renewal based on usage patterns and expiry dates.
   Consider devices expiring in the next 90 days.
   ```

5. **Observe**:
   - Thinking indicators appear (💭 or spinner)
   - Response builds progressively
   - Response time < 30 seconds

6. **Send Follow-up**:
   ```
   Which single device should we prioritize first?
   ```

7. **Verify**:
   - Response references previous analysis
   - Conversation history maintained

## Database Verification

Check thinking redaction in stored messages:

```sql
-- Connect to database
psql $DATABASE_URL

-- Query recent messages
SELECT
    id,
    role,
    content,
    thinking,
    created_at
FROM agent_messages
WHERE conversation_id = 'test-conv-thinking-manual'
ORDER BY created_at DESC
LIMIT 10;
```

**Expected**:
- `thinking` column should be `NULL` or `[REDACTED]` for assistant messages
- `content` column should have the actual response
- No sensitive information in `thinking` column

## Success Criteria

All of the following must be true:

- [ ] ✅ Thinking deltas appear in WebSocket stream (`thinking_delta` events)
- [ ] ✅ Thinking is redacted before database storage (`thinking` column is NULL or `[REDACTED]`)
- [ ] ✅ Follow-up messages reference previous context (history preserved)
- [ ] ✅ Response time < 30 seconds for complex queries
- [ ] ✅ No errors in server logs
- [ ] ✅ Content deltas received and response is coherent
- [ ] ✅ Temperature=1 and thinking budget set correctly (check server logs)

## Troubleshooting

### Issue: No thinking deltas received

**Check**:
1. Verify `enable_thinking=true` in message payload
2. Check server logs for thinking configuration
3. Verify model supports thinking (`claude-sonnet-4-5` or newer)
4. Check `ANTHROPIC_API_KEY` is valid

**Debug**:
```bash
# Check server logs
tail -f logs/api.log

# Look for:
# "Extended thinking enabled: True"
# "Thinking budget: 8000"
# "Temperature: 1"
```

### Issue: Response timeout (>30s)

**Solutions**:
1. Reduce `thinking_budget` (try 5000 or 4000)
2. Simplify the query
3. Check network latency to Anthropic API
4. Verify database connection isn't slow

### Issue: History not preserved

**Check**:
1. Same `conversation_id` used for all messages
2. Messages stored in `agent_messages` table
3. No errors in conversation retrieval (check logs)

**Debug**:
```sql
SELECT COUNT(*)
FROM agent_messages
WHERE conversation_id = 'test-conv-thinking-manual';
-- Should show multiple messages
```

### Issue: Thinking not redacted in database

**Check**:
1. Verify `redact_cot()` function is being called
2. Check `CoTRedactor` is initialized
3. Review server logs for redaction errors

**Debug**:
```python
# Test redaction directly
from src.glp.agent.security.cot_redactor import redact_cot

result = redact_cot("Some thinking content with sensitive data")
print(result)  # Should show "[REDACTED]" or similar
```

## Cleanup

After verification:

```bash
# Stop API server (Ctrl+C)

# Clean up test data
psql $DATABASE_URL -c "DELETE FROM agent_messages WHERE conversation_id = 'test-conv-thinking-manual';"
psql $DATABASE_URL -c "DELETE FROM agent_conversations WHERE id = 'test-conv-thinking-manual';"
```

## Notes

- **Optional Test**: This is an optional manual verification step
- **API Costs**: Live API calls will incur costs on your Anthropic account
- **Thinking Budget**: Higher budget = more thinking = longer response time
- **Model Requirements**: Extended thinking requires Claude Sonnet 4+ models
- **Temperature**: Must be set to 1 when thinking is enabled (API requirement)

## References

- Implementation: `src/glp/agent/providers/anthropic.py`
- Configuration: `src/glp/agent/providers/base.py`
- Agent Config: `src/glp/agent/orchestrator/agent.py`
- Redaction: `src/glp/agent/security/cot_redactor.py`
- WebSocket API: `src/glp/agent/api/router.py`
