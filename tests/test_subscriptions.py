#!/usr/bin/env python3
"""Unit tests for Subscription Synchronization.

Tests cover:
    - SubscriptionSyncer initialization
    - Subscription fetching via GLPClient
    - Database sync operations
    - JSON export functionality
    - Filtering (by status, by type, expiring soon)

Note: SubscriptionSyncer composes GLPClient for HTTP operations.
      The tests mock GLPClient rather than aiohttp directly.
"""
import json

# Import the classes we're testing
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(__file__).rsplit("/tests", 1)[0])
from src.glp.api.client import APIError, GLPClient
from src.glp.api.subscriptions import SubscriptionSyncer

# ============================================
# SubscriptionSyncer Initialization Tests
# ============================================

class TestSubscriptionSyncerInit:
    """Test SubscriptionSyncer initialization."""

    def test_syncer_requires_client(self):
        """Should require a GLPClient instance."""
        mock_client = MagicMock(spec=GLPClient)
        syncer = SubscriptionSyncer(client=mock_client)

        assert syncer.client is mock_client
        assert syncer.db_pool is None

    def test_syncer_accepts_db_pool(self):
        """Should accept optional database pool."""
        mock_client = MagicMock(spec=GLPClient)
        mock_pool = MagicMock()

        syncer = SubscriptionSyncer(client=mock_client, db_pool=mock_pool)

        assert syncer.db_pool is mock_pool

    def test_endpoint_constant(self):
        """Should have correct API endpoint constant."""
        assert SubscriptionSyncer.ENDPOINT == "/subscriptions/v1/subscriptions"


# ============================================
# Subscription Fetching Tests
# ============================================

class TestSubscriptionFetching:
    """Test subscription fetching via GLPClient."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock GLPClient."""
        client = MagicMock(spec=GLPClient)
        return client

    @pytest.fixture
    def syncer(self, mock_client):
        """Create a SubscriptionSyncer with mocked GLPClient."""
        return SubscriptionSyncer(client=mock_client)

    @pytest.mark.asyncio
    async def test_fetch_all_subscriptions(self, syncer, mock_client):
        """Should fetch subscriptions via GLPClient.fetch_all."""
        expected_subs = [
            {"id": "sub-1", "key": "KEY001", "subscriptionType": "CENTRAL_SWITCH"},
            {"id": "sub-2", "key": "KEY002", "subscriptionType": "CENTRAL_AP"},
        ]

        mock_client.fetch_all = AsyncMock(return_value=expected_subs)

        subs = await syncer.fetch_all_subscriptions()

        # Verify correct endpoint
        mock_client.fetch_all.assert_called_once()
        call_args = mock_client.fetch_all.call_args
        assert call_args[0][0] == "/subscriptions/v1/subscriptions"

        assert len(subs) == 2
        assert subs[0]["id"] == "sub-1"

    @pytest.mark.asyncio
    async def test_fetch_subscription_by_id(self, syncer, mock_client):
        """Should fetch single subscription by ID."""
        expected_sub = {"id": "sub-123", "key": "KEYABC"}

        mock_client.get = AsyncMock(return_value=expected_sub)

        sub = await syncer.fetch_subscription_by_id("sub-123")

        mock_client.get.assert_called_once_with("/subscriptions/v1/subscriptions/sub-123")
        assert sub["id"] == "sub-123"

    @pytest.mark.asyncio
    async def test_fetch_and_save_json(self, syncer, mock_client, tmp_path):
        """Should save subscriptions to JSON file."""
        mock_subs = [
            {"id": "sub-1", "key": "KEY001"},
        ]

        mock_client.fetch_all = AsyncMock(return_value=mock_subs)

        output_file = tmp_path / "subscriptions.json"
        count = await syncer.fetch_and_save_json(str(output_file))

        assert count == 1
        assert output_file.exists()

        with open(output_file) as f:
            saved_data = json.load(f)

        assert len(saved_data) == 1
        assert saved_data[0]["id"] == "sub-1"


# ============================================
# Filtering Tests
# ============================================

class TestSubscriptionFiltering:
    """Test subscription filtering capabilities."""

    @pytest.fixture
    def mock_client(self):
        return MagicMock(spec=GLPClient)

    @pytest.fixture
    def syncer(self, mock_client):
        return SubscriptionSyncer(client=mock_client)

    @pytest.mark.asyncio
    async def test_fetch_by_status(self, syncer, mock_client):
        """Should filter by status."""
        mock_client.fetch_all = AsyncMock(return_value=[{"id": "sub-1"}])

        await syncer.fetch_by_status("STARTED")

        # Verify filter was passed
        call_args = mock_client.fetch_all.call_args
        params = call_args[1].get("params", {})
        assert "filter" in params
        assert "STARTED" in params["filter"]

    @pytest.mark.asyncio
    async def test_fetch_by_status_invalid(self, syncer, mock_client):
        """Should raise error for invalid status."""
        with pytest.raises(ValueError) as exc:
            await syncer.fetch_by_status("INVALID_STATUS")

        assert "Invalid status" in str(exc.value)

    @pytest.mark.asyncio
    async def test_fetch_by_type(self, syncer, mock_client):
        """Should filter by subscription type."""
        mock_client.fetch_all = AsyncMock(return_value=[{"id": "sub-1"}])

        await syncer.fetch_by_type("CENTRAL_SWITCH")

        call_args = mock_client.fetch_all.call_args
        params = call_args[1].get("params", {})
        assert "CENTRAL_SWITCH" in params["filter"]

    @pytest.mark.asyncio
    async def test_fetch_expiring_soon(self, syncer, mock_client):
        """Should filter for expiring subscriptions."""
        mock_client.fetch_all = AsyncMock(return_value=[])

        await syncer.fetch_expiring_soon(days=90)

        call_args = mock_client.fetch_all.call_args
        params = call_args[1].get("params", {})
        # Should have filter with date conditions
        assert "subscriptionStatus eq 'STARTED'" in params["filter"]
        assert "endTime" in params["filter"]


# ============================================
# Database Sync Tests
# ============================================

class TestDatabaseSync:
    """Test database synchronization."""

    @pytest.fixture
    def mock_client(self):
        return MagicMock(spec=GLPClient)

    @pytest.fixture
    def mock_db_pool(self):
        """Create a mock database connection pool."""
        pool = MagicMock()
        conn = AsyncMock()

        pool.acquire = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        return pool, conn

    @pytest.mark.asyncio
    async def test_sync_requires_db_pool(self, mock_client):
        """Should raise error when syncing without database pool."""
        syncer = SubscriptionSyncer(client=mock_client)

        with pytest.raises(ValueError) as exc:
            await syncer.sync_to_postgres([{"id": "test"}])

        assert "Database connection pool is required" in str(exc.value)

    @pytest.mark.asyncio
    async def test_sync_inserts_new_subscription(self, mock_client, mock_db_pool):
        """Should insert new subscriptions."""
        pool, conn = mock_db_pool

        # Subscription doesn't exist
        conn.fetchval = AsyncMock(return_value=None)
        conn.execute = AsyncMock()

        syncer = SubscriptionSyncer(client=mock_client, db_pool=pool)

        subs = [{
            "id": "sub-1",
            "key": "KEY001",
            "subscriptionType": "CENTRAL_SWITCH",
            "subscriptionStatus": "STARTED",
        }]

        stats = await syncer.sync_to_postgres(subs)

        assert stats["inserted"] == 1
        assert stats["updated"] == 0
        assert stats["errors"] == 0

    @pytest.mark.asyncio
    async def test_sync_updates_existing_subscription(self, mock_client, mock_db_pool):
        """Should update existing subscriptions."""
        pool, conn = mock_db_pool

        # Subscription exists
        conn.fetchval = AsyncMock(return_value=1)
        conn.execute = AsyncMock()

        syncer = SubscriptionSyncer(client=mock_client, db_pool=pool)

        subs = [{
            "id": "sub-1",
            "key": "KEY001",
        }]

        stats = await syncer.sync_to_postgres(subs)

        assert stats["inserted"] == 0
        assert stats["updated"] == 1


# ============================================
# Business Logic Tests
# ============================================

class TestBusinessLogic:
    """Test business logic helpers."""

    @pytest.fixture
    def mock_client(self):
        return MagicMock(spec=GLPClient)

    @pytest.fixture
    def syncer(self, mock_client):
        return SubscriptionSyncer(client=mock_client)

    def test_summarize_by_status(self, syncer):
        """Should summarize subscriptions by status."""
        subs = [
            {"subscriptionStatus": "STARTED"},
            {"subscriptionStatus": "STARTED"},
            {"subscriptionStatus": "ENDED"},
        ]

        summary = syncer.summarize_by_status(subs)

        assert summary["STARTED"] == 2
        assert summary["ENDED"] == 1

    def test_summarize_by_type(self, syncer):
        """Should summarize subscriptions by type."""
        subs = [
            {"subscriptionType": "CENTRAL_SWITCH"},
            {"subscriptionType": "CENTRAL_AP"},
            {"subscriptionType": "CENTRAL_SWITCH"},
        ]

        summary = syncer.summarize_by_type(subs)

        assert summary["CENTRAL_SWITCH"] == 2
        assert summary["CENTRAL_AP"] == 1


# ============================================
# Error Handling Tests
# ============================================

class TestErrorHandling:
    """Test error handling scenarios."""

    @pytest.fixture
    def mock_client(self):
        return MagicMock(spec=GLPClient)

    @pytest.mark.asyncio
    async def test_fetch_propagates_api_error(self, mock_client):
        """Should propagate APIError from GLPClient."""
        mock_client.fetch_all = AsyncMock(
            side_effect=APIError(status=500, message="Server Error")
        )

        syncer = SubscriptionSyncer(client=mock_client)

        with pytest.raises(APIError) as exc:
            await syncer.fetch_all_subscriptions()

        assert exc.value.status == 500


# ============================================
# Run tests
# ============================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
