# Custom Report Builder - Security Validation

This document describes the security measures implemented in the custom report builder to prevent SQL injection, DoS attacks, and other security vulnerabilities.

## Overview

The custom report builder implements **defense-in-depth** security with multiple layers of protection:

1. **Field & Table Whitelisting** (Primary Defense)
2. **Parameterized Queries** (Primary Defense)
3. **Input Validation & Sanitization** (Secondary Defense)
4. **Size & Complexity Limits** (DoS Prevention)
5. **API Authentication** (Access Control)

## Security Layers

### Layer 1: Field & Table Whitelisting

**Location:** `src/glp/reports/query_builder.py`

All field names and table names are validated against strict whitelists:

```python
ALLOWED_FIELDS = {
    "devices": {"id", "mac_address", "serial_number", "device_type", ...},
    "subscriptions": {"id", "key", "subscription_type", ...}
}

ALLOWED_TABLES = {"devices", "subscriptions"}
```

**Protection:**
- ✅ Prevents access to system tables (pg_user, information_schema, etc.)
- ✅ Prevents arbitrary table/column injection
- ✅ Limits query scope to intended data

**Example Attack Blocked:**
```python
# Attempt to access postgres system tables
FieldConfig(table="pg_user", field="usename")
# ❌ REJECTED: "Invalid table: pg_user"

# Attempt to inject via field name
FieldConfig(table="devices", field="id; DROP TABLE devices--")
# ❌ REJECTED: "Invalid field: devices.id; DROP TABLE devices--"
```

### Layer 2: Parameterized Queries

**Location:** `src/glp/reports/query_builder.py`

All user input values are passed as parameters, never concatenated into SQL:

```python
# Generated SQL uses placeholders
sql = "SELECT * FROM devices WHERE device_type = $param_1"
params = {"param_1": "SWITCH"}

# Values are NEVER in the SQL string
```

**Protection:**
- ✅ Prevents SQL injection in filter values
- ✅ Values treated as data, not code
- ✅ Database driver handles proper escaping

**Example Attack Blocked:**
```python
# Attempt SQL injection via filter value
FilterConfig(
    field="device_name",
    operator=FilterOperator.EQUALS,
    value="admin' OR '1'='1"
)
# ✅ Safe: Value passed as parameter, not concatenated
# Generated SQL: WHERE device_name = $param_1
# Params: {"param_1": "admin' OR '1'='1"}
```

### Layer 3: Input Validation & Sanitization

**Location:** `src/glp/reports/security.py`

Additional validation layer that checks for malicious patterns:

**SQL Keyword Detection:**
```python
SQL_INJECTION_PATTERNS = [
    r"(\b(UNION|SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC)\b)",
    r"(--|;|\/\*|\*\/)",  # Comments and terminators
    r"(\bOR\b.*=.*)",     # OR 1=1 patterns
    ...
]
```

**Value Sanitization:**
- String length limits (500 chars)
- Array length limits (100 items)
- Numeric range limits (±1e15)
- LIKE pattern sanitization

**Protection:**
- ✅ Defense-in-depth: Catches injection attempts even with parameterized queries
- ✅ Prevents malformed inputs
- ✅ Limits resource consumption

**Example Attacks Blocked:**
```python
# SQL injection attempts in filter values
"admin' OR '1'='1"           # ❌ REJECTED: Contains OR =
"1; DROP TABLE devices--"    # ❌ REJECTED: Contains DROP, --, ;
"1' UNION SELECT * FROM..."  # ❌ REJECTED: Contains UNION, SELECT

# Overly broad LIKE patterns
"%"                          # ❌ REJECTED: Too broad
"__"                         # ❌ REJECTED: Too broad
```

### Layer 4: Size & Complexity Limits

**Location:** `src/glp/reports/security.py`

Prevents DoS attacks via resource exhaustion:

**Configuration Limits:**
```python
MAX_FIELDS = 50         # Max fields to select
MAX_FILTERS = 25        # Max filter conditions
MAX_GROUPING = 10       # Max GROUP BY fields
MAX_SORTING = 10        # Max ORDER BY fields
MAX_LIMIT = 10_000      # Max rows to return
```

**Size Limits:**
```python
MAX_CONFIG_SIZE_BYTES = 100_000     # 100KB config JSON
MAX_STRING_VALUE_LENGTH = 500        # 500 chars per value
MAX_ARRAY_LENGTH = 100               # 100 items in arrays
```

**Protection:**
- ✅ Prevents expensive queries that could DoS the database
- ✅ Limits memory consumption
- ✅ Prevents payload bombs

**Example Attacks Blocked:**
```python
# Too many fields (memory exhaustion)
ReportConfig(fields=[...51 fields...])
# ❌ REJECTED: "Too many fields: 51 (max: 50)"

# Too many filters (query complexity)
ReportConfig(filters=[...26 filters...])
# ❌ REJECTED: "Too many filters: 26 (max: 25)"

# Extremely large limit (memory/time exhaustion)
ReportConfig(limit=1_000_000)
# ❌ REJECTED: "Limit too high: 1000000 (max: 10000)"
```

### Layer 5: API Authentication

**Location:** `src/glp/assignment/api/dependencies.py`

All endpoints require API key authentication:

```python
@router.post("/api/reports/custom")
async def create_report(
    _auth: bool = Depends(verify_api_key),
    ...
):
```

**Protection:**
- ✅ Prevents unauthorized access
- ✅ Rate limiting per API key
- ✅ Audit trail

## Validation Flow

```
User Request
    ↓
[1. API Authentication]
    ↓
[2. Pydantic Schema Validation]
    ↓
[3. Security Validation]
    ├─ Config size check
    ├─ Complexity limits
    └─ Filter value validation
        ├─ SQL keyword detection
        ├─ Size limits
        └─ Pattern sanitization
    ↓
[4. QueryBuilder Validation]
    ├─ Field whitelist check
    ├─ Table whitelist check
    └─ Operator validation
    ↓
[5. SQL Generation]
    ├─ Parameterized query
    └─ No value concatenation
    ↓
[6. Database Execution]
```

## Security Testing

**Location:** `tests/test_report_security.py`

Comprehensive security test suite covering:

### SQL Injection Tests
- ✅ Field name injection
- ✅ Table name injection
- ✅ Filter value injection (OR 1=1, UNION, etc.)
- ✅ Comment injection (--, /**/)
- ✅ Stored procedure calls (xp_, sp_)

### Input Validation Tests
- ✅ Oversized strings
- ✅ Oversized arrays
- ✅ Excessive config complexity
- ✅ Extreme numeric values

### Pattern Injection Tests
- ✅ LIKE pattern abuse (%, _, etc.)
- ✅ Pattern sanitization

### Field Whitelist Tests
- ✅ System table access blocked
- ✅ Information schema blocked
- ✅ Only whitelisted fields allowed

**Run Tests:**
```bash
uv run pytest tests/test_report_security.py -v
```

Expected output: All tests pass ✓

## Manual Security Testing

### Test 1: SQL Injection in Filter Values

```bash
curl -X POST http://localhost:8000/api/reports/custom \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Injection Test",
    "config": {
      "fields": [{"table": "devices", "field": "id"}],
      "filters": [{
        "table": "devices",
        "field": "device_name",
        "operator": "equals",
        "value": "admin'\'' OR '\''1'\''='\''1"
      }]
    }
  }'
```

**Expected:** HTTP 400 with error message about SQL keywords

### Test 2: Invalid Field Names

```bash
curl -X POST http://localhost:8000/api/reports/custom \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Field Injection Test",
    "config": {
      "fields": [{"table": "devices", "field": "id; DROP TABLE devices--"}],
      "filters": []
    }
  }'
```

**Expected:** HTTP 400 with error message about invalid field

### Test 3: Large Payload Attack

```bash
# Generate a config with 100 fields
python3 -c "
import json
config = {
    'name': 'Large Config',
    'config': {
        'fields': [{'table': 'devices', 'field': 'id', 'alias': f'field_{i}'} for i in range(100)],
        'filters': []
    }
}
print(json.dumps(config))
" | curl -X POST http://localhost:8000/api/reports/custom \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d @-
```

**Expected:** HTTP 400 with error message about too many fields

### Test 4: System Table Access

```bash
curl -X POST http://localhost:8000/api/reports/custom \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "System Table Test",
    "config": {
      "fields": [{"table": "pg_user", "field": "usename"}],
      "filters": []
    }
  }'
```

**Expected:** HTTP 400 with error message about invalid table

### Test 5: Overly Broad LIKE Pattern

```bash
curl -X POST http://localhost:8000/api/reports/custom \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Pattern Test",
    "config": {
      "fields": [{"table": "devices", "field": "device_name"}],
      "filters": [{
        "table": "devices",
        "field": "device_name",
        "operator": "contains",
        "value": "%"
      }]
    }
  }'
```

**Expected:** HTTP 400 with error message about pattern being too broad

## Error Messages

Security validation returns clear, safe error messages:

### Good Error Messages (Safe)
- ✅ "Invalid field: devices.nonexistent_field"
- ✅ "Filter value contains disallowed SQL keywords"
- ✅ "Too many fields: 51 (max: 50)"
- ✅ "Configuration too large: 150000 bytes (max: 100000)"

### Bad Error Messages (Avoid)
- ❌ Exposing database structure
- ❌ Showing internal SQL queries
- ❌ Revealing table/column names not in whitelist
- ❌ Detailed stack traces in production

## Rate Limiting (Future Enhancement)

The architecture supports rate limiting using the existing `TenantRateLimiter`:

```python
from src.glp.agent.security.tenant_rate_limiter import get_rate_limiter

@router.post("/api/reports/custom/{id}/execute")
async def execute_report(
    rate_limiter: TenantRateLimiter = Depends(get_rate_limiter),
    ...
):
    await rate_limiter.check_rate_limit("api-user")
    ...
```

**Recommended Limits:**
- 10 report executions per minute per user
- 100 report creates/updates per hour per user

## Security Checklist

- [x] Field names validated against whitelist
- [x] Table names validated against whitelist
- [x] All values use parameterized queries
- [x] SQL keyword detection in filter values
- [x] Input size limits enforced
- [x] Configuration complexity limits enforced
- [x] LIKE pattern sanitization
- [x] Numeric value range validation
- [x] Array length validation
- [x] API key authentication required
- [x] Comprehensive security tests
- [ ] Rate limiting (recommended for production)

## Security Monitoring

### Logs to Monitor

```python
# SQL injection attempts (logged at WARNING level)
logger.warning(f"Potential SQL injection attempt detected: {value[:100]}")
```

**Alerting Recommendations:**
- Alert on multiple validation failures from same IP
- Alert on SQL keyword detection
- Alert on attempts to access system tables
- Monitor rate limit violations

### Metrics to Track

- Validation failures per hour
- Top rejected patterns
- Average config complexity
- Execution time per report

## References

- OWASP SQL Injection Prevention: https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html
- CWE-89 SQL Injection: https://cwe.mitre.org/data/definitions/89.html
- PostgreSQL Security: https://www.postgresql.org/docs/current/sql-syntax-lexical.html#SQL-SYNTAX-IDENTIFIERS

## Summary

The custom report builder implements comprehensive security controls:

1. **Primary defenses** (field whitelisting + parameterized queries) prevent SQL injection
2. **Secondary defenses** (input validation) provide defense-in-depth
3. **Resource limits** prevent DoS attacks
4. **Authentication** controls access
5. **Comprehensive tests** verify security posture

All user inputs are validated, sanitized, and parameterized. No user input is ever directly concatenated into SQL queries.
