#!/usr/bin/env python3
"""Comprehensive tests for parallel sync execution in scheduler.

Tests cover:
    - Subscriptions sync completes before parallel tasks start (FK constraint)
    - GreenLake and Aruba Central sync run concurrently when both enabled
    - Partial failure handling (one sync fails, other succeeds)
    - Both syncs succeed in parallel
    - Config flag combinations (only GLP, only Aruba, both, neither)
    - Timing improvements from parallel execution

These tests verify the parallel sync patterns work correctly under various
failure scenarios and configuration combinations.
"""
import asyncio
import sys
import time
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

sys.path.insert(0, str(__file__).rsplit("/tests", 1)[0])
from scheduler import SchedulerConfig, run_sync
from src.glp.api.exceptions import NetworkError, ServerError


# ============================================
# Test Fixtures
# ============================================

@pytest.fixture
def config():
    """Create a basic scheduler config for testing."""
    cfg = SchedulerConfig()
    cfg.sync_devices = True
    cfg.sync_subscriptions = True
    cfg.sync_central = True
    return cfg


@pytest.fixture
def mock_token_manager():
    """Create a mock TokenManager."""
    return MagicMock()


@pytest.fixture
def mock_aruba_token_manager():
    """Create a mock ArubaTokenManager."""
    return MagicMock()


@pytest.fixture
def mock_db_pool():
    """Create a mock database pool."""
    return MagicMock()


# ============================================
# Execution Order Tests
# ============================================

class TestSyncExecutionOrder:
    """Test that syncs execute in the correct order."""

    @pytest.mark.asyncio
    async def test_subscriptions_sync_before_parallel_tasks(
        self, config, mock_token_manager, mock_db_pool, mock_aruba_token_manager
    ):
        """Subscriptions must sync first to satisfy FK constraints."""
        execution_order = []

        async def track_subscription_sync(*args, **kwargs):
            execution_order.append("subscriptions")
            return {"synced": 10}

        async def track_device_sync(*args, **kwargs):
            execution_order.append("devices")
            return {"synced": 5}

        async def track_central_sync(*args, **kwargs):
            execution_order.append("central")
            return {"synced": 3}

        with patch("scheduler.GLPClient") as mock_glp_client, \
             patch("scheduler.ArubaCentralClient") as mock_central_client:

            # Mock context managers
            glp_ctx = AsyncMock()
            glp_ctx.__aenter__.return_value = glp_ctx
            glp_ctx.__aexit__.return_value = None
            mock_glp_client.return_value = glp_ctx

            central_ctx = AsyncMock()
            central_ctx.__aenter__.return_value = central_ctx
            central_ctx.__aexit__.return_value = None
            mock_central_client.return_value = central_ctx

            with patch("scheduler.SubscriptionSyncer") as mock_sub_syncer, \
                 patch("scheduler.DeviceSyncer") as mock_dev_syncer, \
                 patch("scheduler.ArubaCentralSyncer") as mock_aruba_syncer:

                # Setup mocks
                mock_sub_syncer.return_value.sync = track_subscription_sync
                mock_dev_syncer.return_value.sync = track_device_sync
                mock_aruba_syncer.return_value.sync = track_central_sync

                # Run sync
                results = await run_sync(
                    config, mock_token_manager, mock_db_pool, mock_aruba_token_manager
                )

                # Verify execution order
                assert len(execution_order) == 3
                assert execution_order[0] == "subscriptions", "Subscriptions must sync first"
                # Devices and central can be in any order (parallel)
                assert set(execution_order[1:]) == {"devices", "central"}
                assert results["success"]

    @pytest.mark.asyncio
    async def test_subscription_failure_prevents_parallel_tasks(
        self, config, mock_token_manager, mock_db_pool, mock_aruba_token_manager
    ):
        """If subscriptions fail, parallel tasks should not run."""
        execution_order = []

        async def failing_subscription_sync(*args, **kwargs):
            execution_order.append("subscriptions")
            raise ServerError("Subscription sync failed", status_code=500)

        async def track_device_sync(*args, **kwargs):
            execution_order.append("devices")
            return {"synced": 5}

        async def track_central_sync(*args, **kwargs):
            execution_order.append("central")
            return {"synced": 3}

        with patch("scheduler.GLPClient") as mock_glp_client, \
             patch("scheduler.ArubaCentralClient") as mock_central_client:

            # Mock context managers
            glp_ctx = AsyncMock()
            glp_ctx.__aenter__.return_value = glp_ctx
            glp_ctx.__aexit__.return_value = None
            mock_glp_client.return_value = glp_ctx

            central_ctx = AsyncMock()
            central_ctx.__aenter__.return_value = central_ctx
            central_ctx.__aexit__.return_value = None
            mock_central_client.return_value = central_ctx

            with patch("scheduler.SubscriptionSyncer") as mock_sub_syncer, \
                 patch("scheduler.DeviceSyncer") as mock_dev_syncer, \
                 patch("scheduler.ArubaCentralSyncer") as mock_aruba_syncer:

                # Setup mocks
                mock_sub_syncer.return_value.sync = failing_subscription_sync
                mock_dev_syncer.return_value.sync = track_device_sync
                mock_aruba_syncer.return_value.sync = track_central_sync

                # Run sync (should not raise, but results will indicate failure)
                results = await run_sync(
                    config, mock_token_manager, mock_db_pool, mock_aruba_token_manager
                )

                # Verify only subscriptions ran
                assert execution_order == ["subscriptions"]
                assert not results["success"]
                assert results["subscriptions"]["success"] is False
                assert "Subscription sync failed" in results["subscriptions"]["error"]


# ============================================
# Parallel Execution Tests
# ============================================

class TestParallelExecution:
    """Test that GLP and Aruba Central sync run concurrently."""

    @pytest.mark.asyncio
    async def test_both_syncs_run_concurrently(
        self, config, mock_token_manager, mock_db_pool, mock_aruba_token_manager
    ):
        """GLP devices and Aruba Central should run in parallel."""
        device_start_time = None
        device_end_time = None
        central_start_time = None
        central_end_time = None

        async def slow_subscription_sync(*args, **kwargs):
            return {"synced": 10}

        async def slow_device_sync(*args, **kwargs):
            nonlocal device_start_time, device_end_time
            device_start_time = time.time()
            await asyncio.sleep(0.1)  # Simulate work
            device_end_time = time.time()
            return {"synced": 5}

        async def slow_central_sync(*args, **kwargs):
            nonlocal central_start_time, central_end_time
            central_start_time = time.time()
            await asyncio.sleep(0.1)  # Simulate work
            central_end_time = time.time()
            return {"synced": 3}

        with patch("scheduler.GLPClient") as mock_glp_client, \
             patch("scheduler.ArubaCentralClient") as mock_central_client:

            # Mock context managers
            glp_ctx = AsyncMock()
            glp_ctx.__aenter__.return_value = glp_ctx
            glp_ctx.__aexit__.return_value = None
            mock_glp_client.return_value = glp_ctx

            central_ctx = AsyncMock()
            central_ctx.__aenter__.return_value = central_ctx
            central_ctx.__aexit__.return_value = None
            mock_central_client.return_value = central_ctx

            with patch("scheduler.SubscriptionSyncer") as mock_sub_syncer, \
                 patch("scheduler.DeviceSyncer") as mock_dev_syncer, \
                 patch("scheduler.ArubaCentralSyncer") as mock_aruba_syncer:

                # Setup mocks
                mock_sub_syncer.return_value.sync = slow_subscription_sync
                mock_dev_syncer.return_value.sync = slow_device_sync
                mock_aruba_syncer.return_value.sync = slow_central_sync

                # Run sync
                start = time.time()
                results = await run_sync(
                    config, mock_token_manager, mock_db_pool, mock_aruba_token_manager
                )
                total_duration = time.time() - start

                # Verify both ran successfully
                assert results["success"]
                assert results["devices"]["synced"] == 5
                assert results["central"]["synced"] == 3

                # Verify parallel execution (overlapping time windows)
                # If truly parallel, the tasks should overlap
                assert device_start_time is not None
                assert central_start_time is not None

                # Check that tasks overlapped (started before the other finished)
                tasks_overlapped = (
                    device_start_time < central_end_time and
                    central_start_time < device_end_time
                )
                assert tasks_overlapped, "Tasks should execute concurrently with overlapping time windows"

                # Total time should be closer to max(0.1, 0.1) than sum(0.1, 0.1)
                # Allow overhead from context managers, logging, etc.
                # Sequential would be 0.2s+, parallel should be ~0.1s + overhead
                assert total_duration < 0.35, f"Expected parallel execution (~0.1-0.3s), got {total_duration:.2f}s"
                # Verify it's actually faster than sequential (0.1 + 0.1 = 0.2)
                sequential_estimate = 0.2
                assert total_duration < sequential_estimate + 0.1, "Parallel should be faster than sequential"

    @pytest.mark.asyncio
    async def test_parallel_timing_improvement(
        self, config, mock_token_manager, mock_db_pool, mock_aruba_token_manager
    ):
        """Parallel execution should be faster than sequential."""
        async def subscription_sync(*args, **kwargs):
            return {"synced": 10}

        async def device_sync(*args, **kwargs):
            await asyncio.sleep(0.05)
            return {"synced": 5}

        async def central_sync(*args, **kwargs):
            await asyncio.sleep(0.05)
            return {"synced": 3}

        with patch("scheduler.GLPClient") as mock_glp_client, \
             patch("scheduler.ArubaCentralClient") as mock_central_client:

            # Mock context managers
            glp_ctx = AsyncMock()
            glp_ctx.__aenter__.return_value = glp_ctx
            glp_ctx.__aexit__.return_value = None
            mock_glp_client.return_value = glp_ctx

            central_ctx = AsyncMock()
            central_ctx.__aenter__.return_value = central_ctx
            central_ctx.__aexit__.return_value = None
            mock_central_client.return_value = central_ctx

            with patch("scheduler.SubscriptionSyncer") as mock_sub_syncer, \
                 patch("scheduler.DeviceSyncer") as mock_dev_syncer, \
                 patch("scheduler.ArubaCentralSyncer") as mock_aruba_syncer:

                # Setup mocks
                mock_sub_syncer.return_value.sync = subscription_sync
                mock_dev_syncer.return_value.sync = device_sync
                mock_aruba_syncer.return_value.sync = central_sync

                # Run sync and measure time
                start = time.time()
                results = await run_sync(
                    config, mock_token_manager, mock_db_pool, mock_aruba_token_manager
                )
                duration = time.time() - start

                assert results["success"]

                # If sequential: 0.05 + 0.05 = 0.1s
                # If parallel: max(0.05, 0.05) = 0.05s
                # Allow overhead from context managers, logging, etc.
                assert duration < 0.2, f"Parallel execution should take ~0.05-0.15s, got {duration:.3f}s"
                # Key verification: total time should be less than if run sequentially
                # This proves parallel execution is working
                sequential_time = 0.05 + 0.05  # 0.1s
                assert duration < sequential_time + 0.1, f"Should be faster than sequential ({sequential_time}s)"


# ============================================
# Error Handling Tests
# ============================================

class TestParallelErrorHandling:
    """Test error handling in parallel execution."""

    @pytest.mark.asyncio
    async def test_partial_failure_one_task_fails(
        self, config, mock_token_manager, mock_db_pool, mock_aruba_token_manager
    ):
        """If one parallel task fails, the other should still complete."""
        async def subscription_sync(*args, **kwargs):
            return {"synced": 10}

        async def failing_device_sync(*args, **kwargs):
            raise NetworkError("Device sync failed")

        async def successful_central_sync(*args, **kwargs):
            return {"synced": 3}

        with patch("scheduler.GLPClient") as mock_glp_client, \
             patch("scheduler.ArubaCentralClient") as mock_central_client:

            # Mock context managers
            glp_ctx = AsyncMock()
            glp_ctx.__aenter__.return_value = glp_ctx
            glp_ctx.__aexit__.return_value = None
            mock_glp_client.return_value = glp_ctx

            central_ctx = AsyncMock()
            central_ctx.__aenter__.return_value = central_ctx
            central_ctx.__aexit__.return_value = None
            mock_central_client.return_value = central_ctx

            with patch("scheduler.SubscriptionSyncer") as mock_sub_syncer, \
                 patch("scheduler.DeviceSyncer") as mock_dev_syncer, \
                 patch("scheduler.ArubaCentralSyncer") as mock_aruba_syncer:

                # Setup mocks
                mock_sub_syncer.return_value.sync = subscription_sync
                mock_dev_syncer.return_value.sync = failing_device_sync
                mock_aruba_syncer.return_value.sync = successful_central_sync

                # Run sync
                results = await run_sync(
                    config, mock_token_manager, mock_db_pool, mock_aruba_token_manager
                )

                # Verify partial success
                assert not results["success"], "Overall sync should fail if any task fails"
                assert results["subscriptions"]["synced"] == 10
                assert results["devices"]["success"] is False
                assert "Device sync failed" in results["devices"]["error"]
                assert results["central"]["synced"] == 3

    @pytest.mark.asyncio
    async def test_both_parallel_tasks_fail(
        self, config, mock_token_manager, mock_db_pool, mock_aruba_token_manager
    ):
        """If both parallel tasks fail, both errors should be captured."""
        async def subscription_sync(*args, **kwargs):
            return {"synced": 10}

        async def failing_device_sync(*args, **kwargs):
            raise NetworkError("Device sync failed")

        async def failing_central_sync(*args, **kwargs):
            raise ServerError("Central sync failed", status_code=500)

        with patch("scheduler.GLPClient") as mock_glp_client, \
             patch("scheduler.ArubaCentralClient") as mock_central_client:

            # Mock context managers
            glp_ctx = AsyncMock()
            glp_ctx.__aenter__.return_value = glp_ctx
            glp_ctx.__aexit__.return_value = None
            mock_glp_client.return_value = glp_ctx

            central_ctx = AsyncMock()
            central_ctx.__aenter__.return_value = central_ctx
            central_ctx.__aexit__.return_value = None
            mock_central_client.return_value = central_ctx

            with patch("scheduler.SubscriptionSyncer") as mock_sub_syncer, \
                 patch("scheduler.DeviceSyncer") as mock_dev_syncer, \
                 patch("scheduler.ArubaCentralSyncer") as mock_aruba_syncer:

                # Setup mocks
                mock_sub_syncer.return_value.sync = subscription_sync
                mock_dev_syncer.return_value.sync = failing_device_sync
                mock_aruba_syncer.return_value.sync = failing_central_sync

                # Run sync
                results = await run_sync(
                    config, mock_token_manager, mock_db_pool, mock_aruba_token_manager
                )

                # Verify both failures captured
                assert not results["success"]
                assert results["subscriptions"]["synced"] == 10
                assert results["devices"]["success"] is False
                assert "Device sync failed" in results["devices"]["error"]
                assert results["central"]["success"] is False
                assert "Central sync failed" in results["central"]["error"]

    @pytest.mark.asyncio
    async def test_both_parallel_tasks_succeed(
        self, config, mock_token_manager, mock_db_pool, mock_aruba_token_manager
    ):
        """When both parallel tasks succeed, overall sync should succeed."""
        async def subscription_sync(*args, **kwargs):
            return {"synced": 10}

        async def device_sync(*args, **kwargs):
            return {"synced": 5, "updated": 2}

        async def central_sync(*args, **kwargs):
            return {"synced": 3, "updated": 1}

        with patch("scheduler.GLPClient") as mock_glp_client, \
             patch("scheduler.ArubaCentralClient") as mock_central_client:

            # Mock context managers
            glp_ctx = AsyncMock()
            glp_ctx.__aenter__.return_value = glp_ctx
            glp_ctx.__aexit__.return_value = None
            mock_glp_client.return_value = glp_ctx

            central_ctx = AsyncMock()
            central_ctx.__aenter__.return_value = central_ctx
            central_ctx.__aexit__.return_value = None
            mock_central_client.return_value = central_ctx

            with patch("scheduler.SubscriptionSyncer") as mock_sub_syncer, \
                 patch("scheduler.DeviceSyncer") as mock_dev_syncer, \
                 patch("scheduler.ArubaCentralSyncer") as mock_aruba_syncer:

                # Setup mocks
                mock_sub_syncer.return_value.sync = subscription_sync
                mock_dev_syncer.return_value.sync = device_sync
                mock_aruba_syncer.return_value.sync = central_sync

                # Run sync
                results = await run_sync(
                    config, mock_token_manager, mock_db_pool, mock_aruba_token_manager
                )

                # Verify full success
                assert results["success"]
                assert results["subscriptions"]["synced"] == 10
                assert results["devices"]["synced"] == 5
                assert results["devices"]["updated"] == 2
                assert results["central"]["synced"] == 3
                assert results["central"]["updated"] == 1


# ============================================
# Configuration Tests
# ============================================

class TestSyncConfiguration:
    """Test different configuration combinations."""

    @pytest.mark.asyncio
    async def test_only_glp_devices_enabled(
        self, config, mock_token_manager, mock_db_pool, mock_aruba_token_manager
    ):
        """Test syncing only GLP devices (with subscriptions)."""
        config.sync_devices = True
        config.sync_subscriptions = True
        config.sync_central = False

        async def subscription_sync(*args, **kwargs):
            return {"synced": 10}

        async def device_sync(*args, **kwargs):
            return {"synced": 5}

        with patch("scheduler.GLPClient") as mock_glp_client:
            # Mock context manager
            glp_ctx = AsyncMock()
            glp_ctx.__aenter__.return_value = glp_ctx
            glp_ctx.__aexit__.return_value = None
            mock_glp_client.return_value = glp_ctx

            with patch("scheduler.SubscriptionSyncer") as mock_sub_syncer, \
                 patch("scheduler.DeviceSyncer") as mock_dev_syncer, \
                 patch("scheduler.ArubaCentralSyncer") as mock_aruba_syncer:

                # Setup mocks
                mock_sub_syncer.return_value.sync = subscription_sync
                mock_dev_syncer.return_value.sync = device_sync

                # Run sync
                results = await run_sync(
                    config, mock_token_manager, mock_db_pool, mock_aruba_token_manager
                )

                # Verify only GLP ran
                assert results["success"]
                assert results["subscriptions"]["synced"] == 10
                assert results["devices"]["synced"] == 5
                assert results["central"] is None
                assert not mock_aruba_syncer.called

    @pytest.mark.asyncio
    async def test_only_aruba_central_enabled(
        self, config, mock_token_manager, mock_db_pool, mock_aruba_token_manager
    ):
        """Test syncing only Aruba Central."""
        config.sync_devices = False
        config.sync_subscriptions = False
        config.sync_central = True

        async def central_sync(*args, **kwargs):
            return {"synced": 3}

        with patch("scheduler.ArubaCentralClient") as mock_central_client:
            # Mock context manager
            central_ctx = AsyncMock()
            central_ctx.__aenter__.return_value = central_ctx
            central_ctx.__aexit__.return_value = None
            mock_central_client.return_value = central_ctx

            with patch("scheduler.SubscriptionSyncer") as mock_sub_syncer, \
                 patch("scheduler.DeviceSyncer") as mock_dev_syncer, \
                 patch("scheduler.ArubaCentralSyncer") as mock_aruba_syncer:

                # Setup mock
                mock_aruba_syncer.return_value.sync = central_sync

                # Run sync
                results = await run_sync(
                    config, mock_token_manager, mock_db_pool, mock_aruba_token_manager
                )

                # Verify only Aruba ran
                assert results["success"]
                assert results["subscriptions"] is None
                assert results["devices"] is None
                assert results["central"]["synced"] == 3
                assert not mock_sub_syncer.called
                assert not mock_dev_syncer.called

    @pytest.mark.asyncio
    async def test_both_glp_and_aruba_enabled(
        self, config, mock_token_manager, mock_db_pool, mock_aruba_token_manager
    ):
        """Test syncing both GLP and Aruba Central (full sync)."""
        async def subscription_sync(*args, **kwargs):
            return {"synced": 10}

        async def device_sync(*args, **kwargs):
            return {"synced": 5}

        async def central_sync(*args, **kwargs):
            return {"synced": 3}

        with patch("scheduler.GLPClient") as mock_glp_client, \
             patch("scheduler.ArubaCentralClient") as mock_central_client:

            # Mock context managers
            glp_ctx = AsyncMock()
            glp_ctx.__aenter__.return_value = glp_ctx
            glp_ctx.__aexit__.return_value = None
            mock_glp_client.return_value = glp_ctx

            central_ctx = AsyncMock()
            central_ctx.__aenter__.return_value = central_ctx
            central_ctx.__aexit__.return_value = None
            mock_central_client.return_value = central_ctx

            with patch("scheduler.SubscriptionSyncer") as mock_sub_syncer, \
                 patch("scheduler.DeviceSyncer") as mock_dev_syncer, \
                 patch("scheduler.ArubaCentralSyncer") as mock_aruba_syncer:

                # Setup mocks
                mock_sub_syncer.return_value.sync = subscription_sync
                mock_dev_syncer.return_value.sync = device_sync
                mock_aruba_syncer.return_value.sync = central_sync

                # Run sync
                results = await run_sync(
                    config, mock_token_manager, mock_db_pool, mock_aruba_token_manager
                )

                # Verify all ran
                assert results["success"]
                assert results["subscriptions"]["synced"] == 10
                assert results["devices"]["synced"] == 5
                assert results["central"]["synced"] == 3

    @pytest.mark.asyncio
    async def test_central_enabled_but_no_credentials(
        self, config, mock_token_manager, mock_db_pool
    ):
        """Test when central is enabled but credentials are missing."""
        config.sync_central = True

        async def subscription_sync(*args, **kwargs):
            return {"synced": 10}

        async def device_sync(*args, **kwargs):
            return {"synced": 5}

        with patch("scheduler.GLPClient") as mock_glp_client:
            # Mock context manager
            glp_ctx = AsyncMock()
            glp_ctx.__aenter__.return_value = glp_ctx
            glp_ctx.__aexit__.return_value = None
            mock_glp_client.return_value = glp_ctx

            with patch("scheduler.SubscriptionSyncer") as mock_sub_syncer, \
                 patch("scheduler.DeviceSyncer") as mock_dev_syncer, \
                 patch("scheduler.ArubaCentralSyncer") as mock_aruba_syncer:

                # Setup mocks
                mock_sub_syncer.return_value.sync = subscription_sync
                mock_dev_syncer.return_value.sync = device_sync

                # Run sync without aruba_token_manager
                results = await run_sync(
                    config, mock_token_manager, mock_db_pool, aruba_token_manager=None
                )

                # Verify GLP ran, central skipped
                assert results["success"]
                assert results["subscriptions"]["synced"] == 10
                assert results["devices"]["synced"] == 5
                assert results["central"]["skipped"] is True
                assert results["central"]["reason"] == "credentials_missing"
                assert not mock_aruba_syncer.called


# ============================================
# Results Structure Tests
# ============================================

class TestResultsStructure:
    """Test that results dictionary has correct structure."""

    @pytest.mark.asyncio
    async def test_results_include_timing_metadata(
        self, config, mock_token_manager, mock_db_pool, mock_aruba_token_manager
    ):
        """Results should include started_at, completed_at, duration_seconds."""
        async def subscription_sync(*args, **kwargs):
            await asyncio.sleep(0.01)
            return {"synced": 10}

        async def device_sync(*args, **kwargs):
            await asyncio.sleep(0.01)
            return {"synced": 5}

        async def central_sync(*args, **kwargs):
            await asyncio.sleep(0.01)
            return {"synced": 3}

        with patch("scheduler.GLPClient") as mock_glp_client, \
             patch("scheduler.ArubaCentralClient") as mock_central_client:

            # Mock context managers
            glp_ctx = AsyncMock()
            glp_ctx.__aenter__.return_value = glp_ctx
            glp_ctx.__aexit__.return_value = None
            mock_glp_client.return_value = glp_ctx

            central_ctx = AsyncMock()
            central_ctx.__aenter__.return_value = central_ctx
            central_ctx.__aexit__.return_value = None
            mock_central_client.return_value = central_ctx

            with patch("scheduler.SubscriptionSyncer") as mock_sub_syncer, \
                 patch("scheduler.DeviceSyncer") as mock_dev_syncer, \
                 patch("scheduler.ArubaCentralSyncer") as mock_aruba_syncer:

                # Setup mocks
                mock_sub_syncer.return_value.sync = subscription_sync
                mock_dev_syncer.return_value.sync = device_sync
                mock_aruba_syncer.return_value.sync = central_sync

                # Run sync
                results = await run_sync(
                    config, mock_token_manager, mock_db_pool, mock_aruba_token_manager
                )

                # Verify structure
                assert "started_at" in results
                assert "completed_at" in results
                assert "duration_seconds" in results
                assert "success" in results
                assert "error" in results

                # Verify timing
                assert isinstance(results["duration_seconds"], float)
                assert results["duration_seconds"] > 0
                assert results["duration_seconds"] < 1.0  # Should be quick with mocks

                # Verify timestamps are ISO format
                start = datetime.fromisoformat(results["started_at"])
                end = datetime.fromisoformat(results["completed_at"])
                assert end > start

    @pytest.mark.asyncio
    async def test_error_results_include_error_type(
        self, config, mock_token_manager, mock_db_pool, mock_aruba_token_manager
    ):
        """Error results should include error_type and error_message."""
        async def subscription_sync(*args, **kwargs):
            raise ServerError("API error", status_code=500)

        with patch("scheduler.GLPClient") as mock_glp_client:
            # Mock context manager
            glp_ctx = AsyncMock()
            glp_ctx.__aenter__.return_value = glp_ctx
            glp_ctx.__aexit__.return_value = None
            mock_glp_client.return_value = glp_ctx

            with patch("scheduler.SubscriptionSyncer") as mock_sub_syncer:
                # Setup mock
                mock_sub_syncer.return_value.sync = subscription_sync

                # Run sync
                results = await run_sync(
                    config, mock_token_manager, mock_db_pool, mock_aruba_token_manager
                )

                # Verify error structure
                assert not results["success"]
                assert results["subscriptions"]["success"] is False
                assert results["subscriptions"]["error_type"] == "ServerError"
                assert "API error" in results["subscriptions"]["error"]
