"""Tests for the SyncSubscriptionsUseCase.

These tests use mock ports to test the use case in isolation,
demonstrating the testability benefits of Clean Architecture.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import pytest

from src.glp.sync.domain.entities import (
    Subscription,
    SubscriptionTag,
    SyncResult,
)
from src.glp.sync.domain.ports import ISubscriptionAPI, ISubscriptionFieldMapper, ISubscriptionRepository
from src.glp.sync.use_cases.sync_subscriptions import SyncSubscriptionsUseCase


class MockSubscriptionAPI(ISubscriptionAPI):
    """Mock implementation of ISubscriptionAPI for testing."""

    def __init__(
        self,
        subscriptions: list[dict[str, Any]] | None = None,
        raise_error: Exception | None = None,
    ):
        self.subscriptions = subscriptions or []
        self.raise_error = raise_error
        self.fetch_all_called = False

    async def fetch_all(self) -> list[dict[str, Any]]:
        self.fetch_all_called = True
        if self.raise_error:
            raise self.raise_error
        return self.subscriptions

    async def fetch_paginated(self):
        yield self.subscriptions

    async def fetch_expiring_soon(self, days: int) -> list[dict[str, Any]]:
        return [s for s in self.subscriptions if s.get("subscriptionStatus") == "STARTED"]

    async def fetch_by_status(self, status: str) -> list[dict[str, Any]]:
        return [s for s in self.subscriptions if s.get("subscriptionStatus") == status]


class MockSubscriptionRepository(ISubscriptionRepository):
    """Mock implementation of ISubscriptionRepository for testing."""

    def __init__(self, raise_error: Exception | None = None):
        self.upserted_subscriptions: list[Subscription] = []
        self.synced_tags: list[SubscriptionTag] = []
        self.raise_error = raise_error

    async def upsert_subscriptions(self, subscriptions: list[Subscription]) -> int:
        if self.raise_error:
            raise self.raise_error
        self.upserted_subscriptions.extend(subscriptions)
        return len(subscriptions)

    async def sync_tags(
        self,
        subscription_ids: list[UUID],
        tags: list[SubscriptionTag],
    ) -> None:
        if self.raise_error:
            raise self.raise_error
        self.synced_tags.extend(tags)


class MockSubscriptionFieldMapper(ISubscriptionFieldMapper):
    """Mock implementation of ISubscriptionFieldMapper for testing."""

    def __init__(self, raise_mapping_error: bool = False):
        self.raise_mapping_error = raise_mapping_error
        self.mapped_count = 0

    def map_to_entity(self, raw: dict[str, Any]) -> Subscription:
        if self.raise_mapping_error:
            raise ValueError("Mapping error")

        self.mapped_count += 1
        return Subscription(
            id=UUID(raw["id"]),
            key=raw.get("key"),
            subscription_type=raw.get("subscriptionType"),
            subscription_status=raw.get("subscriptionStatus"),
            raw_data=raw,
        )

    def map_to_record(self, subscription: Subscription) -> tuple[Any, ...]:
        return (str(subscription.id), subscription.key)

    def extract_tags(
        self,
        subscription: Subscription,
        raw: dict[str, Any],
    ) -> list[SubscriptionTag]:
        tags = []
        for key, value in (raw.get("tags") or {}).items():
            tags.append(
                SubscriptionTag(
                    subscription_id=subscription.id,
                    tag_key=key,
                    tag_value=str(value),
                )
            )
        return tags


class TestSyncSubscriptionsUseCase:
    """Tests for SyncSubscriptionsUseCase."""

    @pytest.fixture
    def sample_subscriptions(self):
        """Sample subscription data from API."""
        return [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "key": "SUB-001",
                "subscriptionType": "CENTRAL_SWITCH",
                "subscriptionStatus": "STARTED",
                "tags": {"env": "prod"},
            },
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "key": "SUB-002",
                "subscriptionType": "CENTRAL_AP",
                "subscriptionStatus": "STARTED",
                "tags": {"env": "dev", "team": "network"},
            },
        ]

    async def test_sync_success(self, sample_subscriptions):
        """Test successful subscription sync."""
        api = MockSubscriptionAPI(subscriptions=sample_subscriptions)
        repo = MockSubscriptionRepository()
        mapper = MockSubscriptionFieldMapper()

        use_case = SyncSubscriptionsUseCase(api, repo, mapper)
        result = await use_case.execute()

        # Verify result
        assert result.success is True
        assert result.total == 2
        assert result.upserted == 2
        assert result.errors == 0

        # Verify API was called
        assert api.fetch_all_called is True

        # Verify subscriptions were upserted
        assert len(repo.upserted_subscriptions) == 2

        # Verify tags were synced (1 + 2 tags)
        assert len(repo.synced_tags) == 3

    async def test_sync_empty_subscriptions(self):
        """Test sync with no subscriptions."""
        api = MockSubscriptionAPI(subscriptions=[])
        repo = MockSubscriptionRepository()
        mapper = MockSubscriptionFieldMapper()

        use_case = SyncSubscriptionsUseCase(api, repo, mapper)
        result = await use_case.execute()

        assert result.success is True
        assert result.total == 0
        assert result.upserted == 0
        assert result.errors == 0

    async def test_sync_api_error(self):
        """Test sync handles API errors."""
        api = MockSubscriptionAPI(raise_error=Exception("API connection failed"))
        repo = MockSubscriptionRepository()
        mapper = MockSubscriptionFieldMapper()

        use_case = SyncSubscriptionsUseCase(api, repo, mapper)
        result = await use_case.execute()

        assert result.success is False
        assert result.errors == 1
        assert "API fetch failed" in result.error_details[0]

    async def test_sync_mapping_error(self, sample_subscriptions):
        """Test sync handles mapping errors gracefully."""
        api = MockSubscriptionAPI(subscriptions=sample_subscriptions)
        repo = MockSubscriptionRepository()
        mapper = MockSubscriptionFieldMapper(raise_mapping_error=True)

        use_case = SyncSubscriptionsUseCase(api, repo, mapper)
        result = await use_case.execute()

        # Should still succeed with errors logged
        assert result.total == 2
        assert result.errors == 2  # Both mappings failed
        assert len(result.error_details) == 2

    async def test_sync_database_error(self, sample_subscriptions):
        """Test sync handles database errors."""
        api = MockSubscriptionAPI(subscriptions=sample_subscriptions)
        repo = MockSubscriptionRepository(raise_error=Exception("Database connection lost"))
        mapper = MockSubscriptionFieldMapper()

        use_case = SyncSubscriptionsUseCase(api, repo, mapper)
        result = await use_case.execute()

        # Should complete with errors
        assert result.success is False
        assert result.errors >= 1
        assert any("Database" in e for e in result.error_details)

    async def test_sync_result_to_dict(self, sample_subscriptions):
        """Test sync result can be converted to dict for backward compat."""
        api = MockSubscriptionAPI(subscriptions=sample_subscriptions)
        repo = MockSubscriptionRepository()
        mapper = MockSubscriptionFieldMapper()

        use_case = SyncSubscriptionsUseCase(api, repo, mapper)
        result = await use_case.execute()

        d = result.to_dict()

        assert "total" in d
        assert "upserted" in d
        assert "errors" in d
        assert "synced_at" in d
        assert d["total"] == 2
        assert d["upserted"] == 2

    async def test_sync_extracts_tags_correctly(self, sample_subscriptions):
        """Test that tags are correctly extracted and synced."""
        api = MockSubscriptionAPI(subscriptions=sample_subscriptions)
        repo = MockSubscriptionRepository()
        mapper = MockSubscriptionFieldMapper()

        use_case = SyncSubscriptionsUseCase(api, repo, mapper)
        await use_case.execute()

        # First subscription has 1 tag, second has 2 tags
        assert len(repo.synced_tags) == 3

        tag_keys = {t.tag_key for t in repo.synced_tags}
        assert "env" in tag_keys
        assert "team" in tag_keys

    async def test_summarize_by_status(self, sample_subscriptions):
        """Test summarize_by_status helper."""
        api = MockSubscriptionAPI(subscriptions=sample_subscriptions)
        repo = MockSubscriptionRepository()
        mapper = MockSubscriptionFieldMapper()

        use_case = SyncSubscriptionsUseCase(api, repo, mapper)

        # Map the subscriptions
        subscriptions = [mapper.map_to_entity(raw) for raw in sample_subscriptions]

        summary = use_case.summarize_by_status(subscriptions)

        assert summary["STARTED"] == 2

    async def test_summarize_by_type(self, sample_subscriptions):
        """Test summarize_by_type helper."""
        api = MockSubscriptionAPI(subscriptions=sample_subscriptions)
        repo = MockSubscriptionRepository()
        mapper = MockSubscriptionFieldMapper()

        use_case = SyncSubscriptionsUseCase(api, repo, mapper)

        # Map the subscriptions
        subscriptions = [mapper.map_to_entity(raw) for raw in sample_subscriptions]

        summary = use_case.summarize_by_type(subscriptions)

        assert summary["CENTRAL_SWITCH"] == 1
        assert summary["CENTRAL_AP"] == 1
