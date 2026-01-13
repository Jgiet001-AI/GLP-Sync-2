# Database Integrity Verification

## Overview

The `verify_db_integrity.py` script performs comprehensive database integrity checks after parallel sync operations. It ensures that all database constraints are maintained, data is consistent, and no orphaned records exist.

## Usage

### Basic Execution

```bash
# Using virtual environment Python
.venv/bin/python verify_db_integrity.py

# Or if uv is available
uv run python verify_db_integrity.py

# With python3 (if dependencies are in system Python)
python3 verify_db_integrity.py
```

### Environment Variables

**Required:**
- `DATABASE_URL`: PostgreSQL connection string (e.g., `postgresql://user:pass@localhost:5432/greenlake`)

**Optional:**
- Load from `.env` file in project root

### Exit Codes

- `0`: All integrity checks passed ✅
- `1`: One or more checks failed ❌
- `2`: Database connection error or missing configuration ⚠️

## Verification Checks

The script performs 10 comprehensive integrity checks:

### 1. Devices Count
- **Purpose**: Verify devices table is accessible and has records
- **Query**: `SELECT COUNT(*) FROM devices;`
- **Expected**: Count ≥ 0

### 2. Subscriptions Count
- **Purpose**: Verify subscriptions table is accessible and has records
- **Query**: `SELECT COUNT(*) FROM subscriptions;`
- **Expected**: Count ≥ 0

### 3. Device-Subscription Relationships Count
- **Purpose**: Verify many-to-many relationship table has records
- **Query**: `SELECT COUNT(*) FROM device_subscriptions;`
- **Expected**: Count ≥ 0

### 4. Foreign Key Constraint Integrity
- **Purpose**: Ensure no orphaned device_subscriptions (critical FK constraint check)
- **Query**: Finds device_subscriptions referencing non-existent subscriptions
- **Expected**: 0 orphaned records
- **Impact**: This is the CRITICAL check for parallel sync - subscriptions MUST sync first

### 5. Device References Integrity
- **Purpose**: Ensure all device_subscriptions reference valid devices
- **Query**: Finds device_subscriptions referencing non-existent devices
- **Expected**: 0 orphaned references

### 6. Latest Sync History Entry
- **Purpose**: Verify the most recent sync completed successfully
- **Query**: Gets latest sync_history record with full details
- **Expected**: status = 'completed', no error_message, records_errors = 0
- **Details**: Shows sync ID, type, timing, and record counts

### 7. Relationship Data Completeness
- **Purpose**: Ensure device_subscriptions has no NULL primary keys
- **Query**: Finds relationships with NULL device_id or subscription_id
- **Expected**: 0 invalid relationships

### 8. Device Data Completeness
- **Purpose**: Verify devices have required fields populated
- **Query**: Finds devices with NULL serial_number or raw_data
- **Expected**: 0 devices missing required data

### 9. Subscription Data Completeness
- **Purpose**: Verify subscriptions have raw API data
- **Query**: Finds subscriptions with NULL raw_data
- **Expected**: 0 subscriptions missing raw_data

### 10. Database Summary (Informational)
- **Purpose**: Provide overview of active records
- **Details**: Active devices, active subscriptions, devices with subscriptions
- **Pass Condition**: Always passes (informational only)

## Example Output

```
================================================================================
DATABASE INTEGRITY VERIFICATION
================================================================================
Timestamp: 2026-01-13 16:24:03

✅ PASS | Devices count
       Total devices: 11,727
✅ PASS | Subscriptions count
       Total subscriptions: 27
✅ PASS | Device-subscription relationships count
       Total relationships: 9,099
✅ PASS | Foreign key constraint integrity
       Orphaned device_subscriptions: 0 (expected: 0)
✅ PASS | Device references integrity
       Orphaned device references: 0 (expected: 0)
✅ PASS | Latest sync history entry
       ID: 8, Type: central_devices, Status: completed
       Started: 2026-01-13 21:31:24 (duration: 69.72s)
       Fetched: 0, Inserted: 0, Updated: 0, Errors: 0
✅ PASS | Relationship data completeness
       Invalid relationships (NULL keys): 0 (expected: 0)
✅ PASS | Device data completeness
       Devices with missing required fields: 0 (expected: 0)
✅ PASS | Subscription data completeness
       Subscriptions with missing raw_data: 0 (expected: 0)
✅ PASS | Database summary
       Active devices: 11,727, Active subscriptions: 10, Devices with subscriptions: 9,099

================================================================================
✅ ALL CHECKS PASSED (10/10)
================================================================================

✓ Database integrity verified successfully
```

## Integration with CI/CD

### GitHub Actions Example

```yaml
- name: Verify Database Integrity
  env:
    DATABASE_URL: ${{ secrets.DATABASE_URL }}
  run: |
    .venv/bin/python verify_db_integrity.py
```

### Docker Compose Health Check

```yaml
healthcheck:
  test: ["CMD", "python", "/app/verify_db_integrity.py"]
  interval: 30s
  timeout: 10s
  retries: 3
```

## Automation

### Post-Sync Verification

Add to scheduler.py after sync completes:

```python
import subprocess

# After run_sync() completes
result = subprocess.run(
    [".venv/bin/python", "verify_db_integrity.py"],
    capture_output=True
)

if result.returncode != 0:
    logger.error("Database integrity check failed!")
    # Handle failure (alert, rollback, etc.)
```

### Cron Job

```bash
# Verify integrity every hour
0 * * * * cd /path/to/project && .venv/bin/python verify_db_integrity.py >> /var/log/db_integrity.log 2>&1
```

## Troubleshooting

### Common Issues

**Issue**: `column "records_upserted" does not exist`
- **Solution**: Script expects schema with `records_inserted`, `records_updated` columns (not `records_upserted`)

**Issue**: `DATABASE_URL environment variable not set`
- **Solution**: Create `.env` file with `DATABASE_URL=postgresql://...` or export it

**Issue**: `ModuleNotFoundError: No module named 'asyncpg'`
- **Solution**: Use `.venv/bin/python` instead of system `python`

### Failed Check Investigation

If **Foreign key constraint integrity** fails (orphaned device_subscriptions):
```sql
-- Find orphaned records
SELECT ds.device_id, ds.subscription_id
FROM device_subscriptions ds
WHERE NOT EXISTS (
    SELECT 1 FROM subscriptions s WHERE s.id = ds.subscription_id
);

-- Clean orphaned records (if safe to do so)
DELETE FROM device_subscriptions ds
WHERE NOT EXISTS (
    SELECT 1 FROM subscriptions s WHERE s.id = ds.subscription_id
);
```

If **Latest sync history entry** fails:
```sql
-- View recent sync history
SELECT * FROM sync_history ORDER BY started_at DESC LIMIT 5;

-- Check for errors
SELECT error_message FROM sync_history WHERE status = 'failed' ORDER BY started_at DESC LIMIT 1;
```

## Related Documentation

- [Database Schema](../db/schema.sql) - Devices and device_subscriptions tables
- [Subscriptions Schema](../db/subscriptions_schema.sql) - Subscriptions table
- [Parallel Sync Implementation](../scheduler.py) - Sync orchestration
- [Verification Report](../.auto-claude/specs/031-concurrent-greenlake-and-aruba-central-sync-in-sch/verification_report.md) - Manual verification results

## Technical Details

### Database Schema Dependencies

```
subscriptions (parent)
    ↓ FK: fk_device_subscriptions_sub
device_subscriptions (child)
    ← device_id references devices.id
```

**Critical Constraint**: `device_subscriptions.subscription_id` MUST reference a valid `subscriptions.id`

This is why subscriptions MUST sync before devices in parallel sync implementation.

### Performance Notes

- All queries use indexes (no full table scans)
- Total execution time: ~100-500ms for 10K+ devices
- Suitable for frequent automated checks
- Safe to run while sync is in progress (read-only queries)

## Maintenance

### Adding New Checks

To add a new integrity check:

1. Add query in `verify_database_integrity()` function
2. Create `IntegrityCheck` with name, pass condition, and details
3. Append to `checks` list
4. Update this documentation with check details

Example:
```python
# Check: Verify no duplicate serial numbers
duplicate_serials = await conn.fetchval("""
    SELECT COUNT(*)
    FROM (
        SELECT serial_number
        FROM devices
        GROUP BY serial_number
        HAVING COUNT(*) > 1
    ) duplicates;
""")
checks.append(IntegrityCheck(
    "No duplicate serial numbers",
    duplicate_serials == 0,
    f"Duplicate serial numbers found: {duplicate_serials} (expected: 0)"
))
```

### Schema Evolution

When database schema changes:
1. Update queries to match new column names
2. Add checks for new constraints/relationships
3. Update expected values if data model changes
4. Test script with production-like data

## License

Part of HPE GreenLake Device & Subscription Sync platform.
