"""
Tests for AgentDB Memory Patterns.

Tests cover:
- Persistent session store
- Pattern learning store
- Memory versioning store
- Integration with orchestrator
"""

import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.glp.agent.memory.agentdb import (
    AgentDBAdapter,
    LearnedPattern,
    MemoryRevision,
    MemoryVersion,
    MemoryVersioningStore,
    PatternLearningStore,
    PatternType,
    PersistentSessionStore,
    SessionData,
    SessionType,
)


# ============================================
# Helpers
# ============================================


class AsyncContextManager:
    """Helper class to create async context managers for mocking."""

    def __init__(self, return_value):
        self.return_value = return_value

    async def __aenter__(self):
        return self.return_value

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


# ============================================
# Fixtures
# ============================================


@pytest.fixture
def mock_db_pool():
    """Create a mock database pool."""
    pool = MagicMock()

    # Create mock connection
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.fetchval = AsyncMock(return_value=1)

    # Mock transaction context manager
    mock_conn.transaction = MagicMock(return_value=AsyncContextManager(None))

    # Mock acquire to return async context manager
    pool.acquire = MagicMock(return_value=AsyncContextManager(mock_conn))
    pool._mock_conn = mock_conn  # Store for test access

    return pool


@pytest.fixture
def mock_embedding_provider():
    """Create a mock embedding provider."""
    provider = AsyncMock()
    provider.embed = AsyncMock(return_value=([0.1] * 1536, "text-embedding-3-large", 1536))
    return provider


@pytest.fixture
def session_store(mock_db_pool):
    """Create a session store with mock DB."""
    return PersistentSessionStore(mock_db_pool)


@pytest.fixture
def pattern_store(mock_db_pool, mock_embedding_provider):
    """Create a pattern store with mock DB and embeddings."""
    return PatternLearningStore(mock_db_pool, mock_embedding_provider)


@pytest.fixture
def versioning_store(mock_db_pool):
    """Create a versioning store with mock DB."""
    return MemoryVersioningStore(mock_db_pool)


@pytest.fixture
def agentdb_adapter(mock_db_pool, mock_embedding_provider):
    """Create a full AgentDB adapter."""
    return AgentDBAdapter(mock_db_pool, mock_embedding_provider)


# ============================================
# SessionData Tests
# ============================================


class TestSessionData:
    """Tests for SessionData dataclass."""

    def test_session_data_creation(self):
        """Test basic session data creation."""
        session = SessionData(
            id=uuid4(),
            tenant_id="tenant-123",
            user_id="user-456",
            session_type=SessionType.CONFIRMATION,
            key="conv:op-123",
            data={"operation_id": "op-123"},
        )

        assert session.tenant_id == "tenant-123"
        assert session.user_id == "user-456"
        assert session.session_type == SessionType.CONFIRMATION
        assert session.key == "conv:op-123"
        assert session.data["operation_id"] == "op-123"
        assert session.expires_at is None

    def test_session_data_with_ttl(self):
        """Test session data with TTL sets expiration."""
        session = SessionData(
            id=uuid4(),
            tenant_id="tenant-123",
            user_id="user-456",
            session_type=SessionType.CACHE,
            key="cache-key",
            data={"cached": "value"},
            ttl_seconds=3600,
        )

        assert session.expires_at is not None
        assert session.expires_at > datetime.utcnow()
        assert session.expires_at < datetime.utcnow() + timedelta(hours=2)


# ============================================
# PersistentSessionStore Tests
# ============================================


class TestPersistentSessionStore:
    """Tests for PersistentSessionStore."""

    @pytest.mark.asyncio
    async def test_set_session(self, session_store, mock_db_pool):
        """Test storing a session."""
        # Store session
        session = await session_store.set(
            tenant_id="tenant-123",
            user_id="user-456",
            session_type=SessionType.CONFIRMATION,
            key="conv:op-123",
            data={"operation_id": "op-123", "tool_call": {"name": "add_device"}},
            ttl_seconds=3600,
        )

        assert session.tenant_id == "tenant-123"
        assert session.session_type == SessionType.CONFIRMATION
        assert session.key == "conv:op-123"
        mock_db_pool._mock_conn.execute.assert_called()

    @pytest.mark.asyncio
    async def test_get_session(self, session_store, mock_db_pool):
        """Test retrieving a session."""
        # Setup mock return value
        mock_db_pool._mock_conn.fetchrow.return_value = {
            "id": uuid4(),
            "tenant_id": "tenant-123",
            "user_id": "user-456",
            "session_type": "confirmation",
            "key": "conv:op-123",
            "data": json.dumps({"operation_id": "op-123"}),
            "expires_at": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        # Get session
        session = await session_store.get(
            tenant_id="tenant-123",
            user_id="user-456",
            session_type=SessionType.CONFIRMATION,
            key="conv:op-123",
        )

        assert session is not None
        assert session.tenant_id == "tenant-123"
        assert session.data["operation_id"] == "op-123"

    @pytest.mark.asyncio
    async def test_get_and_delete_session(self, session_store, mock_db_pool):
        """Test atomic get and delete."""
        # Setup mock return value
        mock_db_pool._mock_conn.fetchrow.return_value = {
            "id": uuid4(),
            "tenant_id": "tenant-123",
            "user_id": "user-456",
            "session_type": "confirmation",
            "key": "conv:op-123",
            "data": json.dumps({"operation_id": "op-123"}),
            "expires_at": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        # Get and delete
        session = await session_store.get_and_delete(
            tenant_id="tenant-123",
            user_id="user-456",
            session_type=SessionType.CONFIRMATION,
            key="conv:op-123",
        )

        assert session is not None
        # Verify DELETE query was used
        call_args = mock_db_pool._mock_conn.fetchrow.call_args
        assert "DELETE" in str(call_args)

    @pytest.mark.asyncio
    async def test_get_nonexistent_session(self, session_store, mock_db_pool):
        """Test getting a session that doesn't exist."""
        mock_db_pool._mock_conn.fetchrow.return_value = None

        session = await session_store.get(
            tenant_id="tenant-123",
            user_id="user-456",
            session_type=SessionType.CONFIRMATION,
            key="nonexistent",
        )

        assert session is None


# ============================================
# LearnedPattern Tests
# ============================================


class TestLearnedPattern:
    """Tests for LearnedPattern dataclass."""

    def test_pattern_creation(self):
        """Test basic pattern creation."""
        pattern = LearnedPattern(
            id=uuid4(),
            tenant_id="tenant-123",
            pattern_type=PatternType.TOOL_SUCCESS,
            trigger="List all devices",
            response="search_devices",
            context={"region": "us-west"},
            success_count=5,
            failure_count=1,
        )

        assert pattern.pattern_type == PatternType.TOOL_SUCCESS
        assert pattern.confidence == 1.0  # Default

    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        pattern = LearnedPattern(
            id=uuid4(),
            tenant_id="tenant-123",
            pattern_type=PatternType.TOOL_SUCCESS,
            trigger="test",
            response="test",
            success_count=8,
            failure_count=2,
        )

        assert pattern.success_rate == 0.8  # 8/10

    def test_success_rate_zero_total(self):
        """Test success rate with zero total."""
        pattern = LearnedPattern(
            id=uuid4(),
            tenant_id="tenant-123",
            pattern_type=PatternType.TOOL_SUCCESS,
            trigger="test",
            response="test",
            success_count=0,
            failure_count=0,
        )

        assert pattern.success_rate == 0.0


# ============================================
# PatternLearningStore Tests
# ============================================


class TestPatternLearningStore:
    """Tests for PatternLearningStore."""

    @pytest.mark.asyncio
    async def test_learn_new_pattern(self, pattern_store, mock_db_pool, mock_embedding_provider):
        """Test learning a new pattern."""
        mock_db_pool._mock_conn.fetchrow.return_value = {
            "id": uuid4(),
            "tenant_id": "tenant-123",
            "pattern_type": "tool_success",
            "trigger_text": "List all devices",
            "response": "search_devices",
            "context": json.dumps({"region": "us-west"}),
            "success_count": 1,
            "failure_count": 0,
            "confidence": 1.0,
            "last_used_at": None,
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        pattern = await pattern_store.learn(
            tenant_id="tenant-123",
            pattern_type=PatternType.TOOL_SUCCESS,
            trigger="List all devices",
            response="search_devices",
            context={"region": "us-west"},
            success=True,
        )

        assert pattern.pattern_type == PatternType.TOOL_SUCCESS
        assert pattern.trigger == "List all devices"
        assert pattern.response == "search_devices"
        mock_embedding_provider.embed.assert_called_once_with("List all devices")

    @pytest.mark.asyncio
    async def test_learn_failure_pattern(self, pattern_store, mock_db_pool, mock_embedding_provider):
        """Test learning from a failure."""
        mock_db_pool._mock_conn.fetchrow.return_value = {
            "id": uuid4(),
            "tenant_id": "tenant-123",
            "pattern_type": "error_recovery",
            "trigger_text": "Device not found",
            "response": "retry_with_different_id",
            "context": None,
            "success_count": 0,
            "failure_count": 1,
            "confidence": 0.0,
            "last_used_at": None,
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        pattern = await pattern_store.learn(
            tenant_id="tenant-123",
            pattern_type=PatternType.ERROR_RECOVERY,
            trigger="Device not found",
            response="retry_with_different_id",
            success=False,
        )

        assert pattern.failure_count == 1
        assert pattern.success_count == 0

    @pytest.mark.asyncio
    async def test_find_similar_patterns(self, pattern_store, mock_db_pool, mock_embedding_provider):
        """Test finding similar patterns."""
        mock_db_pool._mock_conn.fetch.return_value = [
            {
                "id": uuid4(),
                "tenant_id": "tenant-123",
                "pattern_type": "tool_success",
                "trigger_text": "Show devices in region",
                "response": "search_devices",
                "context": json.dumps({"region": "us-west"}),
                "success_count": 10,
                "failure_count": 1,
                "confidence": 0.91,
                "last_used_at": datetime.utcnow(),
                "is_active": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "similarity": 0.95,
            }
        ]

        results = await pattern_store.find_similar(
            tenant_id="tenant-123",
            query="List devices in us-west",
            pattern_type=PatternType.TOOL_SUCCESS,
            limit=5,
        )

        assert len(results) == 1
        pattern, similarity = results[0]
        assert pattern.response == "search_devices"
        assert similarity == 0.95


# ============================================
# MemoryRevision Tests
# ============================================


class TestMemoryRevision:
    """Tests for MemoryRevision dataclass."""

    def test_revision_creation(self):
        """Test basic revision creation."""
        memory_id = uuid4()
        revision = MemoryRevision(
            id=uuid4(),
            memory_id=memory_id,
            tenant_id="tenant-123",
            user_id="user-456",
            version=1,
            version_state=MemoryVersion.CURRENT,
            content="User prefers metric units",
            previous_content="User prefers imperial units",
            change_reason="User correction",
        )

        assert revision.memory_id == memory_id
        assert revision.version == 1
        assert revision.version_state == MemoryVersion.CURRENT
        assert revision.change_reason == "User correction"


# ============================================
# MemoryVersioningStore Tests
# ============================================


class TestMemoryVersioningStore:
    """Tests for MemoryVersioningStore."""

    @pytest.mark.asyncio
    async def test_create_revision(self, versioning_store, mock_db_pool):
        """Test creating a memory revision."""
        memory_id = uuid4()

        revision = await versioning_store.create_revision(
            memory_id=memory_id,
            tenant_id="tenant-123",
            user_id="user-456",
            content="Corrected: User prefers metric",
            previous_content="User prefers imperial",
            change_reason="User correction via chat",
            changed_by="user-456",
        )

        assert revision.memory_id == memory_id
        assert revision.version == 1
        assert revision.content == "Corrected: User prefers metric"

    @pytest.mark.asyncio
    async def test_get_revision_history(self, versioning_store, mock_db_pool):
        """Test getting revision history."""
        memory_id = uuid4()
        mock_db_pool._mock_conn.fetch.return_value = [
            {
                "id": uuid4(),
                "memory_id": memory_id,
                "tenant_id": "tenant-123",
                "user_id": "user-456",
                "version": 2,
                "version_state": "current",
                "content": "Version 2 content",
                "previous_content": "Version 1 content",
                "change_reason": "Update",
                "changed_by": "user-456",
                "confidence": 1.0,
                "metadata": None,
                "created_at": datetime.utcnow(),
            },
            {
                "id": uuid4(),
                "memory_id": memory_id,
                "tenant_id": "tenant-123",
                "user_id": "user-456",
                "version": 1,
                "version_state": "superseded",
                "content": "Version 1 content",
                "previous_content": None,
                "change_reason": "Initial",
                "changed_by": "user-456",
                "confidence": 1.0,
                "metadata": None,
                "created_at": datetime.utcnow(),
            },
        ]

        revisions = await versioning_store.get_history(
            memory_id=memory_id,
            tenant_id="tenant-123",
            user_id="user-456",
        )

        assert len(revisions) == 2
        assert revisions[0].version == 2
        assert revisions[0].version_state == MemoryVersion.CURRENT
        assert revisions[1].version == 1
        assert revisions[1].version_state == MemoryVersion.SUPERSEDED


# ============================================
# AgentDBAdapter Tests
# ============================================


class TestAgentDBAdapter:
    """Tests for the unified AgentDBAdapter."""

    def test_adapter_initialization(self, agentdb_adapter):
        """Test adapter initializes all stores."""
        assert agentdb_adapter.sessions is not None
        assert agentdb_adapter.patterns is not None
        assert agentdb_adapter.versions is not None

    @pytest.mark.asyncio
    async def test_adapter_cleanup(self, agentdb_adapter):
        """Test adapter cleanup method."""
        # Patch the cleanup method directly
        with patch.object(agentdb_adapter.sessions, 'cleanup_expired', new_callable=AsyncMock, return_value=5):
            stats = await agentdb_adapter.cleanup(tenant_id="tenant-123")

        assert stats["expired_sessions"] == 5


# ============================================
# Integration Tests
# ============================================


class TestAgentDBIntegration:
    """Integration tests for AgentDB with orchestrator."""

    def test_session_type_enum_values(self):
        """Test all session types have correct values."""
        assert SessionType.CONFIRMATION.value == "confirmation"
        assert SessionType.OPERATION.value == "operation"
        assert SessionType.CONTEXT.value == "context"
        assert SessionType.CACHE.value == "cache"

    def test_pattern_type_enum_values(self):
        """Test all pattern types have correct values."""
        assert PatternType.TOOL_SUCCESS.value == "tool_success"
        assert PatternType.QUERY_RESPONSE.value == "query_response"
        assert PatternType.ERROR_RECOVERY.value == "error_recovery"
        assert PatternType.WORKFLOW.value == "workflow"

    def test_memory_version_enum_values(self):
        """Test all memory version states have correct values."""
        assert MemoryVersion.CURRENT.value == "current"
        assert MemoryVersion.SUPERSEDED.value == "superseded"
        assert MemoryVersion.CORRECTED.value == "corrected"
        assert MemoryVersion.MERGED.value == "merged"

    def test_session_data_ttl_calculation(self):
        """Test TTL is correctly calculated."""
        before = datetime.utcnow()
        session = SessionData(
            id=uuid4(),
            tenant_id="tenant-123",
            user_id="user-456",
            session_type=SessionType.CONFIRMATION,
            key="test-key",
            data={},
            ttl_seconds=60,
        )
        after = datetime.utcnow() + timedelta(seconds=60)

        assert session.expires_at is not None
        assert session.expires_at >= before + timedelta(seconds=60)
        assert session.expires_at <= after + timedelta(seconds=1)
