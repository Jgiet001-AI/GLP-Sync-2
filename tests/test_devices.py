#!/usr/bin/env python3
"""Unit tests for Device Synchronization.

Tests cover:
    - DeviceSyncer initialization
    - Device fetching via GLPClient
    - Database sync operations
    - JSON export functionality

Note: DeviceSyncer now composes GLPClient for HTTP operations.
      The tests mock GLPClient rather than aiohttp directly.
"""
import json

# Import the classes we're testing
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(__file__).rsplit("/tests", 1)[0])
from src.glp.api.client import APIError, GLPClient
from src.glp.api.devices import DeviceSyncer

# ============================================
# DeviceSyncer Initialization Tests
# ============================================

class TestDeviceSyncerInit:
    """Test DeviceSyncer initialization."""

    def test_syncer_requires_client(self):
        """Should require a GLPClient instance."""
        mock_client = MagicMock(spec=GLPClient)
        syncer = DeviceSyncer(client=mock_client)

        assert syncer.client is mock_client
        assert syncer.db_pool is None

    def test_syncer_accepts_db_pool(self):
        """Should accept optional database pool."""
        mock_client = MagicMock(spec=GLPClient)
        mock_pool = MagicMock()

        syncer = DeviceSyncer(client=mock_client, db_pool=mock_pool)

        assert syncer.db_pool is mock_pool

    def test_endpoint_constant(self):
        """Should have correct API endpoint constant."""
        assert DeviceSyncer.ENDPOINT == "/devices/v1/devices"


# ============================================
# Device Fetching Tests
# ============================================

class TestDeviceFetching:
    """Test device fetching via GLPClient."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock GLPClient."""
        client = MagicMock(spec=GLPClient)
        return client

    @pytest.fixture
    def syncer(self, mock_client):
        """Create a DeviceSyncer with mocked GLPClient."""
        return DeviceSyncer(client=mock_client)

    @pytest.mark.asyncio
    async def test_fetch_all_devices(self, syncer, mock_client):
        """Should fetch devices via GLPClient.fetch_all."""
        expected_devices = [
            {"id": "device-1", "serialNumber": "SN001"},
            {"id": "device-2", "serialNumber": "SN002"},
        ]

        mock_client.fetch_all = AsyncMock(return_value=expected_devices)

        devices = await syncer.fetch_all_devices()

        # Verify correct endpoint and pagination config
        mock_client.fetch_all.assert_called_once()
        call_args = mock_client.fetch_all.call_args
        assert call_args[0][0] == "/devices/v1/devices"

        assert len(devices) == 2
        assert devices[0]["id"] == "device-1"

    @pytest.mark.asyncio
    async def test_fetch_devices_generator(self, syncer, mock_client):
        """Should yield device pages via GLPClient.paginate."""
        page1 = [{"id": "device-1"}, {"id": "device-2"}]
        page2 = [{"id": "device-3"}]

        async def mock_paginate(*args, **kwargs):
            yield page1
            yield page2

        mock_client.paginate = mock_paginate

        all_pages = []
        async for page in syncer.fetch_devices_generator():
            all_pages.append(page)

        assert len(all_pages) == 2
        assert len(all_pages[0]) == 2
        assert len(all_pages[1]) == 1

    @pytest.mark.asyncio
    async def test_fetch_and_save_json(self, syncer, mock_client, tmp_path):
        """Should save devices to JSON file."""
        mock_devices = [
            {"id": "device-1", "serialNumber": "SN001"},
        ]

        mock_client.fetch_all = AsyncMock(return_value=mock_devices)

        output_file = tmp_path / "devices.json"
        count = await syncer.fetch_and_save_json(str(output_file))

        assert count == 1
        assert output_file.exists()

        with open(output_file) as f:
            saved_data = json.load(f)

        assert len(saved_data) == 1
        assert saved_data[0]["id"] == "device-1"


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

        # Mock the pool.acquire() async context manager
        pool.acquire = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        return pool, conn

    @pytest.mark.asyncio
    async def test_sync_requires_db_pool(self, mock_client):
        """Should raise error when syncing without database pool."""
        syncer = DeviceSyncer(client=mock_client)

        with pytest.raises(ValueError) as exc:
            await syncer.sync_to_postgres([{"id": "test"}])

        assert "Database connection pool is required" in str(exc.value)

    @pytest.mark.asyncio
    async def test_sync_inserts_new_device(self, mock_client, mock_db_pool):
        """Should insert new devices."""
        pool, conn = mock_db_pool

        # Device doesn't exist (fetchval returns None)
        conn.fetchval = AsyncMock(return_value=None)
        conn.execute = AsyncMock()

        syncer = DeviceSyncer(client=mock_client, db_pool=pool)

        devices = [{
            "id": "device-1",
            "serialNumber": "SN001",
            "macAddress": "AA:BB:CC:DD:EE:FF",
        }]

        stats = await syncer.sync_to_postgres(devices)

        assert stats["inserted"] == 1
        assert stats["updated"] == 0
        assert stats["errors"] == 0

    @pytest.mark.asyncio
    async def test_sync_updates_existing_device(self, mock_client, mock_db_pool):
        """Should update existing devices."""
        pool, conn = mock_db_pool

        # Device exists (fetchval returns truthy)
        conn.fetchval = AsyncMock(return_value=1)
        conn.execute = AsyncMock()

        syncer = DeviceSyncer(client=mock_client, db_pool=pool)

        devices = [{
            "id": "device-1",
            "serialNumber": "SN001",
        }]

        stats = await syncer.sync_to_postgres(devices)

        assert stats["inserted"] == 0
        assert stats["updated"] == 1


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

        syncer = DeviceSyncer(client=mock_client)

        with pytest.raises(APIError) as exc:
            await syncer.fetch_all_devices()

        assert exc.value.status == 500


# ============================================
# Run tests
# ============================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
