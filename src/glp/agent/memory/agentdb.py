"""
AgentDB Memory Patterns Implementation.

Provides AgentDB-style memory patterns using PostgreSQL + pgvector:
- Persistent session store (for confirmations, operation state)
- Pattern learning (successful interaction patterns)
- Memory versioning (track changes, corrections)
- Hierarchical memory (immediate, short-term, long-term, semantic)

This implementation uses the existing PostgreSQL infrastructure
while providing the same capabilities as AgentDB.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional, Protocol
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


# ============================================
# Protocols
# ============================================


class IAsyncDBPool(Protocol):
    """Protocol for async database pool."""

    async def acquire(self): ...
    async def execute(self, query: str, *args) -> str: ...
    async def fetch(self, query: str, *args) -> list[Any]: ...
    async def fetchrow(self, query: str, *args) -> Optional[Any]: ...
    async def fetchval(self, query: str, *args) -> Any: ...


class IEmbeddingProvider(Protocol):
    """Protocol for embedding generation."""

    async def embed(self, text: str) -> tuple[list[float], str, int]: ...


# ============================================
# Data Classes
# ============================================


class SessionType(str, Enum):
    """Types of session data."""

    CONFIRMATION = "confirmation"  # Pending operation confirmations
    OPERATION = "operation"        # In-flight operation state
    CONTEXT = "context"            # Conversation context
    CACHE = "cache"                # Temporary cached data


class PatternType(str, Enum):
    """Types of learned patterns."""

    TOOL_SUCCESS = "tool_success"       # Successful tool executions
    QUERY_RESPONSE = "query_response"   # Question-answer patterns
    ERROR_RECOVERY = "error_recovery"   # Error handling patterns
    WORKFLOW = "workflow"               # Multi-step workflow patterns


class MemoryVersion(str, Enum):
    """Memory version states."""

    CURRENT = "current"
    SUPERSEDED = "superseded"
    CORRECTED = "corrected"
    MERGED = "merged"


@dataclass
class SessionData:
    """Persistent session data.

    Stores operation state, pending confirmations, and context
    that survives server restarts.
    """

    id: UUID
    tenant_id: str
    user_id: str
    session_type: SessionType
    key: str  # Unique key within session type
    data: dict[str, Any]
    ttl_seconds: Optional[int] = None
    expires_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        if self.ttl_seconds and not self.expires_at:
            self.expires_at = datetime.utcnow() + timedelta(seconds=self.ttl_seconds)


@dataclass
class LearnedPattern:
    """A learned interaction pattern.

    Captures successful patterns for future use.
    """

    id: UUID
    tenant_id: str
    pattern_type: PatternType
    trigger: str  # What triggers this pattern
    response: str  # Expected response/action
    trigger_embedding: Optional[list[float]] = None
    context: dict[str, Any] = field(default_factory=dict)
    success_count: int = 1
    failure_count: int = 0
    last_used_at: Optional[datetime] = None
    confidence: float = 1.0
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0


@dataclass
class MemoryRevision:
    """A versioned memory revision.

    Tracks changes to memories over time for correction and audit.
    """

    id: UUID
    memory_id: UUID  # Original memory ID
    tenant_id: str
    user_id: str
    version: int
    version_state: MemoryVersion
    content: str
    previous_content: Optional[str] = None
    change_reason: Optional[str] = None
    changed_by: Optional[str] = None  # User who made the change
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


# ============================================
# Persistent Session Store
# ============================================


class PersistentSessionStore:
    """Persistent session storage for operation state.

    Replaces in-memory `_pending_confirmations` with PostgreSQL-backed
    storage that survives server restarts and supports multi-instance.

    Features:
    - TTL-based expiration
    - Atomic get-and-delete for confirmations
    - Multi-instance safe (uses SELECT FOR UPDATE)

    Usage:
        store = PersistentSessionStore(db_pool)

        # Store a pending confirmation
        await store.set(
            tenant_id="tenant-123",
            user_id="user-456",
            session_type=SessionType.CONFIRMATION,
            key="conv-abc:op-123",
            data={"operation_id": "op-123", "tool_call": {...}},
            ttl_seconds=3600,
        )

        # Get and delete (atomic)
        data = await store.get_and_delete("tenant-123", "user-456", SessionType.CONFIRMATION, "conv-abc:op-123")
    """

    def __init__(self, db_pool: IAsyncDBPool):
        """Initialize the session store.

        Args:
            db_pool: Async database connection pool
        """
        self.db = db_pool

    async def _set_tenant_context(self, conn, tenant_id: str) -> None:
        """Set the tenant context for RLS policies."""
        # SET LOCAL doesn't support parameterized queries, escape manually
        safe_tenant_id = tenant_id.replace("'", "''")
        await conn.execute(f"SET LOCAL app.tenant_id = '{safe_tenant_id}'")

    async def set(
        self,
        tenant_id: str,
        user_id: str,
        session_type: SessionType,
        key: str,
        data: dict[str, Any],
        ttl_seconds: Optional[int] = None,
    ) -> SessionData:
        """Store session data.

        Args:
            tenant_id: Tenant identifier
            user_id: User identifier
            session_type: Type of session data
            key: Unique key within session type
            data: Data to store
            ttl_seconds: Optional TTL in seconds

        Returns:
            Stored session data
        """
        session = SessionData(
            id=uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            session_type=session_type,
            key=key,
            data=data,
            ttl_seconds=ttl_seconds,
        )

        async with self.db.acquire() as conn:
            async with conn.transaction():
                await self._set_tenant_context(conn, tenant_id)

                await conn.execute(
                    """
                    INSERT INTO agent_sessions (
                        id, tenant_id, user_id, session_type, key,
                        data, expires_at, created_at, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (tenant_id, user_id, session_type, key)
                    DO UPDATE SET
                        data = EXCLUDED.data,
                        expires_at = EXCLUDED.expires_at,
                        updated_at = NOW()
                    """,
                    session.id,
                    session.tenant_id,
                    session.user_id,
                    session.session_type.value,
                    session.key,
                    json.dumps(session.data),
                    session.expires_at,
                    session.created_at,
                    session.updated_at,
                )

        logger.debug(f"Stored session {session_type.value}:{key}")
        return session

    async def get(
        self,
        tenant_id: str,
        user_id: str,
        session_type: SessionType,
        key: str,
    ) -> Optional[SessionData]:
        """Get session data.

        Args:
            tenant_id: Tenant identifier
            user_id: User identifier
            session_type: Type of session data
            key: Session key

        Returns:
            Session data if found and not expired
        """
        async with self.db.acquire() as conn:
            async with conn.transaction():
                await self._set_tenant_context(conn, tenant_id)

                row = await conn.fetchrow(
                    """
                    SELECT id, tenant_id, user_id, session_type, key,
                           data, expires_at, created_at, updated_at
                    FROM agent_sessions
                    WHERE tenant_id = $1 AND user_id = $2
                      AND session_type = $3 AND key = $4
                      AND (expires_at IS NULL OR expires_at > NOW())
                    """,
                    tenant_id,
                    user_id,
                    session_type.value,
                    key,
                )

                if not row:
                    return None

                return SessionData(
                    id=row["id"],
                    tenant_id=row["tenant_id"],
                    user_id=row["user_id"],
                    session_type=SessionType(row["session_type"]),
                    key=row["key"],
                    data=json.loads(row["data"]) if row["data"] else {},
                    expires_at=row["expires_at"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )

    async def get_and_delete(
        self,
        tenant_id: str,
        user_id: str,
        session_type: SessionType,
        key: str,
    ) -> Optional[SessionData]:
        """Atomically get and delete session data.

        Used for single-use data like confirmation tokens.

        Args:
            tenant_id: Tenant identifier
            user_id: User identifier
            session_type: Type of session data
            key: Session key

        Returns:
            Session data if found
        """
        async with self.db.acquire() as conn:
            async with conn.transaction():
                await self._set_tenant_context(conn, tenant_id)

                # Use FOR UPDATE to lock the row
                row = await conn.fetchrow(
                    """
                    DELETE FROM agent_sessions
                    WHERE tenant_id = $1 AND user_id = $2
                      AND session_type = $3 AND key = $4
                      AND (expires_at IS NULL OR expires_at > NOW())
                    RETURNING id, tenant_id, user_id, session_type, key,
                              data, expires_at, created_at, updated_at
                    """,
                    tenant_id,
                    user_id,
                    session_type.value,
                    key,
                )

                if not row:
                    return None

                return SessionData(
                    id=row["id"],
                    tenant_id=row["tenant_id"],
                    user_id=row["user_id"],
                    session_type=SessionType(row["session_type"]),
                    key=row["key"],
                    data=json.loads(row["data"]) if row["data"] else {},
                    expires_at=row["expires_at"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )

    async def list_by_type(
        self,
        tenant_id: str,
        user_id: str,
        session_type: SessionType,
        prefix: Optional[str] = None,
    ) -> list[SessionData]:
        """List session data by type.

        Args:
            tenant_id: Tenant identifier
            user_id: User identifier
            session_type: Type of session data
            prefix: Optional key prefix filter

        Returns:
            List of session data
        """
        async with self.db.acquire() as conn:
            async with conn.transaction():
                await self._set_tenant_context(conn, tenant_id)

                if prefix:
                    rows = await conn.fetch(
                        """
                        SELECT id, tenant_id, user_id, session_type, key,
                               data, expires_at, created_at, updated_at
                        FROM agent_sessions
                        WHERE tenant_id = $1 AND user_id = $2
                          AND session_type = $3 AND key LIKE $4
                          AND (expires_at IS NULL OR expires_at > NOW())
                        ORDER BY created_at DESC
                        """,
                        tenant_id,
                        user_id,
                        session_type.value,
                        f"{prefix}%",
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT id, tenant_id, user_id, session_type, key,
                               data, expires_at, created_at, updated_at
                        FROM agent_sessions
                        WHERE tenant_id = $1 AND user_id = $2
                          AND session_type = $3
                          AND (expires_at IS NULL OR expires_at > NOW())
                        ORDER BY created_at DESC
                        """,
                        tenant_id,
                        user_id,
                        session_type.value,
                    )

                return [
                    SessionData(
                        id=row["id"],
                        tenant_id=row["tenant_id"],
                        user_id=row["user_id"],
                        session_type=SessionType(row["session_type"]),
                        key=row["key"],
                        data=json.loads(row["data"]) if row["data"] else {},
                        expires_at=row["expires_at"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                    for row in rows
                ]

    async def delete(
        self,
        tenant_id: str,
        user_id: str,
        session_type: SessionType,
        key: str,
    ) -> bool:
        """Delete session data.

        Args:
            tenant_id: Tenant identifier
            user_id: User identifier
            session_type: Type of session data
            key: Session key

        Returns:
            True if deleted
        """
        async with self.db.acquire() as conn:
            async with conn.transaction():
                await self._set_tenant_context(conn, tenant_id)

                result = await conn.execute(
                    """
                    DELETE FROM agent_sessions
                    WHERE tenant_id = $1 AND user_id = $2
                      AND session_type = $3 AND key = $4
                    """,
                    tenant_id,
                    user_id,
                    session_type.value,
                    key,
                )

                return result == "DELETE 1"

    async def cleanup_expired(self, tenant_id: Optional[str] = None) -> int:
        """Clean up expired sessions.

        Args:
            tenant_id: Optional tenant to clean

        Returns:
            Number of deleted sessions
        """
        async with self.db.acquire() as conn:
            if tenant_id:
                await self._set_tenant_context(conn, tenant_id)
                result = await conn.execute(
                    """
                    DELETE FROM agent_sessions
                    WHERE tenant_id = $1 AND expires_at < NOW()
                    """,
                    tenant_id,
                )
            else:
                result = await conn.execute(
                    "DELETE FROM agent_sessions WHERE expires_at < NOW()"
                )

            count = int(result.split()[-1]) if result else 0
            logger.info(f"Cleaned up {count} expired sessions")
            return count


# ============================================
# Pattern Learning Store
# ============================================


class PatternLearningStore:
    """Store for learned interaction patterns.

    Captures successful patterns for future retrieval and application.
    Uses semantic search to find similar patterns.

    Usage:
        store = PatternLearningStore(db_pool, embedding_provider)

        # Learn a successful pattern
        await store.learn(
            tenant_id="tenant-123",
            pattern_type=PatternType.TOOL_SUCCESS,
            trigger="List all devices in us-west region",
            response="search_devices",
            context={"region": "us-west", "success": True},
        )

        # Find similar patterns
        patterns = await store.find_similar(
            tenant_id="tenant-123",
            query="Show me devices in the western region",
            pattern_type=PatternType.TOOL_SUCCESS,
            limit=5,
        )
    """

    def __init__(
        self,
        db_pool: IAsyncDBPool,
        embedding_provider: Optional[IEmbeddingProvider] = None,
    ):
        """Initialize the pattern store.

        Args:
            db_pool: Async database connection pool
            embedding_provider: Provider for generating embeddings
        """
        self.db = db_pool
        self.embedding_provider = embedding_provider

    async def _set_tenant_context(self, conn, tenant_id: str) -> None:
        """Set the tenant context for RLS policies."""
        # SET LOCAL doesn't support parameterized queries, escape manually
        safe_tenant_id = tenant_id.replace("'", "''")
        await conn.execute(f"SET LOCAL app.tenant_id = '{safe_tenant_id}'")

    def _compute_trigger_hash(self, trigger: str, pattern_type: PatternType) -> str:
        """Compute hash for deduplication."""
        content = f"{pattern_type.value}:{trigger.lower().strip()}"
        return hashlib.sha256(content.encode()).hexdigest()

    async def learn(
        self,
        tenant_id: str,
        pattern_type: PatternType,
        trigger: str,
        response: str,
        context: Optional[dict[str, Any]] = None,
        success: bool = True,
    ) -> LearnedPattern:
        """Learn a new pattern or reinforce existing one.

        Args:
            tenant_id: Tenant identifier
            pattern_type: Type of pattern
            trigger: What triggers this pattern
            response: Expected response/action
            context: Additional context
            success: Whether this was a successful execution

        Returns:
            Created or updated pattern
        """
        trigger_hash = self._compute_trigger_hash(trigger, pattern_type)

        # Generate embedding if provider available
        embedding = None
        embedding_model = None
        embedding_dimension = None

        if self.embedding_provider:
            try:
                embedding, embedding_model, embedding_dimension = await self.embedding_provider.embed(trigger)
            except Exception as e:
                logger.warning(f"Failed to generate pattern embedding: {e}")

        async with self.db.acquire() as conn:
            async with conn.transaction():
                await self._set_tenant_context(conn, tenant_id)

                # Upsert pattern
                row = await conn.fetchrow(
                    """
                    INSERT INTO agent_patterns (
                        id, tenant_id, pattern_type, trigger_text, trigger_hash,
                        trigger_embedding, embedding_model, embedding_dimension,
                        response, context, success_count, failure_count,
                        confidence, created_at, updated_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                        CASE WHEN $11 THEN 1 ELSE 0 END,
                        CASE WHEN $11 THEN 0 ELSE 1 END,
                        1.0, NOW(), NOW()
                    )
                    ON CONFLICT (tenant_id, trigger_hash)
                    DO UPDATE SET
                        success_count = agent_patterns.success_count + CASE WHEN $11 THEN 1 ELSE 0 END,
                        failure_count = agent_patterns.failure_count + CASE WHEN $11 THEN 0 ELSE 1 END,
                        confidence = (agent_patterns.success_count + CASE WHEN $11 THEN 1 ELSE 0 END)::float /
                                    (agent_patterns.success_count + agent_patterns.failure_count + 1)::float,
                        last_used_at = NOW(),
                        updated_at = NOW(),
                        context = COALESCE($10, agent_patterns.context),
                        trigger_embedding = COALESCE($6, agent_patterns.trigger_embedding),
                        embedding_model = COALESCE($7, agent_patterns.embedding_model),
                        embedding_dimension = COALESCE($8, agent_patterns.embedding_dimension)
                    RETURNING id, tenant_id, pattern_type, trigger_text, response, context,
                              success_count, failure_count, confidence, last_used_at,
                              is_active, created_at, updated_at
                    """,
                    uuid4(),
                    tenant_id,
                    pattern_type.value,
                    trigger,
                    trigger_hash,
                    embedding,
                    embedding_model,
                    embedding_dimension,
                    response,
                    json.dumps(context) if context else None,
                    success,
                )

                return LearnedPattern(
                    id=row["id"],
                    tenant_id=row["tenant_id"],
                    pattern_type=PatternType(row["pattern_type"]),
                    trigger=row["trigger_text"],
                    response=row["response"],
                    context=json.loads(row["context"]) if row["context"] else {},
                    success_count=row["success_count"],
                    failure_count=row["failure_count"],
                    confidence=row["confidence"],
                    last_used_at=row["last_used_at"],
                    is_active=row["is_active"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )

    async def find_similar(
        self,
        tenant_id: str,
        query: str,
        pattern_type: Optional[PatternType] = None,
        limit: int = 5,
        min_confidence: float = 0.5,
    ) -> list[tuple[LearnedPattern, float]]:
        """Find similar patterns using semantic search.

        Args:
            tenant_id: Tenant identifier
            query: Query text
            pattern_type: Optional type filter
            limit: Maximum results
            min_confidence: Minimum confidence threshold

        Returns:
            List of (pattern, similarity_score) tuples
        """
        if not self.embedding_provider:
            return []

        # Generate query embedding
        query_embedding, embedding_model, _ = await self.embedding_provider.embed(query)

        async with self.db.acquire() as conn:
            async with conn.transaction():
                await self._set_tenant_context(conn, tenant_id)

                params = [query_embedding, embedding_model, min_confidence, limit]
                type_filter = ""

                if pattern_type:
                    type_filter = "AND pattern_type = $5"
                    params.append(pattern_type.value)

                rows = await conn.fetch(
                    f"""
                    SELECT id, tenant_id, pattern_type, trigger_text, response, context,
                           success_count, failure_count, confidence, last_used_at,
                           is_active, created_at, updated_at,
                           1 - (trigger_embedding <=> $1::vector) AS similarity
                    FROM agent_patterns
                    WHERE is_active = TRUE
                      AND embedding_model = $2
                      AND confidence >= $3
                      AND trigger_embedding IS NOT NULL
                      {type_filter}
                    ORDER BY similarity DESC
                    LIMIT $4
                    """,
                    *params,
                )

                results = []
                for row in rows:
                    pattern = LearnedPattern(
                        id=row["id"],
                        tenant_id=row["tenant_id"],
                        pattern_type=PatternType(row["pattern_type"]),
                        trigger=row["trigger_text"],
                        response=row["response"],
                        context=json.loads(row["context"]) if row["context"] else {},
                        success_count=row["success_count"],
                        failure_count=row["failure_count"],
                        confidence=row["confidence"],
                        last_used_at=row["last_used_at"],
                        is_active=row["is_active"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                    results.append((pattern, row["similarity"]))

                return results

    async def get_by_type(
        self,
        tenant_id: str,
        pattern_type: PatternType,
        limit: int = 20,
    ) -> list[LearnedPattern]:
        """Get patterns by type, sorted by confidence.

        Args:
            tenant_id: Tenant identifier
            pattern_type: Pattern type
            limit: Maximum results

        Returns:
            List of patterns
        """
        async with self.db.acquire() as conn:
            async with conn.transaction():
                await self._set_tenant_context(conn, tenant_id)

                rows = await conn.fetch(
                    """
                    SELECT id, tenant_id, pattern_type, trigger_text, response, context,
                           success_count, failure_count, confidence, last_used_at,
                           is_active, created_at, updated_at
                    FROM agent_patterns
                    WHERE pattern_type = $1 AND is_active = TRUE
                    ORDER BY confidence DESC, success_count DESC
                    LIMIT $2
                    """,
                    pattern_type.value,
                    limit,
                )

                return [
                    LearnedPattern(
                        id=row["id"],
                        tenant_id=row["tenant_id"],
                        pattern_type=PatternType(row["pattern_type"]),
                        trigger=row["trigger_text"],
                        response=row["response"],
                        context=json.loads(row["context"]) if row["context"] else {},
                        success_count=row["success_count"],
                        failure_count=row["failure_count"],
                        confidence=row["confidence"],
                        last_used_at=row["last_used_at"],
                        is_active=row["is_active"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                    for row in rows
                ]

    async def deactivate(self, tenant_id: str, pattern_id: UUID) -> bool:
        """Deactivate a pattern (soft delete).

        Args:
            tenant_id: Tenant identifier
            pattern_id: Pattern ID

        Returns:
            True if deactivated
        """
        async with self.db.acquire() as conn:
            async with conn.transaction():
                await self._set_tenant_context(conn, tenant_id)

                result = await conn.execute(
                    """
                    UPDATE agent_patterns
                    SET is_active = FALSE, updated_at = NOW()
                    WHERE id = $1 AND is_active = TRUE
                    """,
                    pattern_id,
                )

                return result == "UPDATE 1"


# ============================================
# Memory Versioning Store
# ============================================


class MemoryVersioningStore:
    """Store for versioned memory revisions.

    Tracks changes to memories over time, enabling:
    - Correction workflows
    - Audit trails
    - Rollback capabilities

    Usage:
        store = MemoryVersioningStore(db_pool)

        # Create a revision when correcting memory
        await store.create_revision(
            memory_id=uuid,
            tenant_id="tenant-123",
            user_id="user-456",
            content="Corrected: User prefers metric units",
            previous_content="User prefers imperial units",
            change_reason="User correction via chat",
        )

        # Get revision history
        revisions = await store.get_history(memory_id=uuid, context=user_context)
    """

    def __init__(self, db_pool: IAsyncDBPool):
        """Initialize the versioning store.

        Args:
            db_pool: Async database connection pool
        """
        self.db = db_pool

    async def _set_tenant_context(self, conn, tenant_id: str) -> None:
        """Set the tenant context for RLS policies."""
        # SET LOCAL doesn't support parameterized queries, escape manually
        safe_tenant_id = tenant_id.replace("'", "''")
        await conn.execute(f"SET LOCAL app.tenant_id = '{safe_tenant_id}'")

    async def create_revision(
        self,
        memory_id: UUID,
        tenant_id: str,
        user_id: str,
        content: str,
        previous_content: Optional[str] = None,
        change_reason: Optional[str] = None,
        changed_by: Optional[str] = None,
        version_state: MemoryVersion = MemoryVersion.CURRENT,
        confidence: float = 1.0,
        metadata: Optional[dict[str, Any]] = None,
    ) -> MemoryRevision:
        """Create a new memory revision.

        Args:
            memory_id: ID of the memory being revised
            tenant_id: Tenant identifier
            user_id: User identifier
            content: New content
            previous_content: Previous content (for diff)
            change_reason: Why the change was made
            changed_by: Who made the change
            version_state: State of this version
            confidence: Confidence in this revision
            metadata: Additional metadata

        Returns:
            Created revision
        """
        async with self.db.acquire() as conn:
            async with conn.transaction():
                await self._set_tenant_context(conn, tenant_id)

                # Get next version number
                current_version = await conn.fetchval(
                    """
                    SELECT COALESCE(MAX(version), 0) + 1
                    FROM agent_memory_revisions
                    WHERE memory_id = $1
                    """,
                    memory_id,
                )

                # Mark previous current version as superseded
                if version_state == MemoryVersion.CURRENT:
                    await conn.execute(
                        """
                        UPDATE agent_memory_revisions
                        SET version_state = $1
                        WHERE memory_id = $2 AND version_state = $3
                        """,
                        MemoryVersion.SUPERSEDED.value,
                        memory_id,
                        MemoryVersion.CURRENT.value,
                    )

                revision_id = uuid4()

                await conn.execute(
                    """
                    INSERT INTO agent_memory_revisions (
                        id, memory_id, tenant_id, user_id, version, version_state,
                        content, previous_content, change_reason, changed_by,
                        confidence, metadata, created_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
                    """,
                    revision_id,
                    memory_id,
                    tenant_id,
                    user_id,
                    current_version,
                    version_state.value,
                    content,
                    previous_content,
                    change_reason,
                    changed_by,
                    confidence,
                    json.dumps(metadata) if metadata else None,
                )

                return MemoryRevision(
                    id=revision_id,
                    memory_id=memory_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    version=current_version,
                    version_state=version_state,
                    content=content,
                    previous_content=previous_content,
                    change_reason=change_reason,
                    changed_by=changed_by,
                    confidence=confidence,
                    metadata=metadata or {},
                )

    async def get_history(
        self,
        memory_id: UUID,
        tenant_id: str,
        user_id: str,
        limit: int = 20,
    ) -> list[MemoryRevision]:
        """Get revision history for a memory.

        Args:
            memory_id: Memory ID
            tenant_id: Tenant identifier
            user_id: User identifier
            limit: Maximum revisions

        Returns:
            List of revisions, newest first
        """
        async with self.db.acquire() as conn:
            async with conn.transaction():
                await self._set_tenant_context(conn, tenant_id)

                rows = await conn.fetch(
                    """
                    SELECT id, memory_id, tenant_id, user_id, version, version_state,
                           content, previous_content, change_reason, changed_by,
                           confidence, metadata, created_at
                    FROM agent_memory_revisions
                    WHERE memory_id = $1 AND user_id = $2
                    ORDER BY version DESC
                    LIMIT $3
                    """,
                    memory_id,
                    user_id,
                    limit,
                )

                return [
                    MemoryRevision(
                        id=row["id"],
                        memory_id=row["memory_id"],
                        tenant_id=row["tenant_id"],
                        user_id=row["user_id"],
                        version=row["version"],
                        version_state=MemoryVersion(row["version_state"]),
                        content=row["content"],
                        previous_content=row["previous_content"],
                        change_reason=row["change_reason"],
                        changed_by=row["changed_by"],
                        confidence=row["confidence"],
                        metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                        created_at=row["created_at"],
                    )
                    for row in rows
                ]

    async def get_current(
        self,
        memory_id: UUID,
        tenant_id: str,
        user_id: str,
    ) -> Optional[MemoryRevision]:
        """Get the current revision of a memory.

        Args:
            memory_id: Memory ID
            tenant_id: Tenant identifier
            user_id: User identifier

        Returns:
            Current revision or None
        """
        async with self.db.acquire() as conn:
            async with conn.transaction():
                await self._set_tenant_context(conn, tenant_id)

                row = await conn.fetchrow(
                    """
                    SELECT id, memory_id, tenant_id, user_id, version, version_state,
                           content, previous_content, change_reason, changed_by,
                           confidence, metadata, created_at
                    FROM agent_memory_revisions
                    WHERE memory_id = $1 AND user_id = $2 AND version_state = $3
                    ORDER BY version DESC
                    LIMIT 1
                    """,
                    memory_id,
                    user_id,
                    MemoryVersion.CURRENT.value,
                )

                if not row:
                    return None

                return MemoryRevision(
                    id=row["id"],
                    memory_id=row["memory_id"],
                    tenant_id=row["tenant_id"],
                    user_id=row["user_id"],
                    version=row["version"],
                    version_state=MemoryVersion(row["version_state"]),
                    content=row["content"],
                    previous_content=row["previous_content"],
                    change_reason=row["change_reason"],
                    changed_by=row["changed_by"],
                    confidence=row["confidence"],
                    metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                    created_at=row["created_at"],
                )

    async def rollback(
        self,
        memory_id: UUID,
        target_version: int,
        tenant_id: str,
        user_id: str,
        reason: str,
    ) -> Optional[MemoryRevision]:
        """Rollback to a previous version.

        Creates a new revision based on an older version.

        Args:
            memory_id: Memory ID
            target_version: Version to rollback to
            tenant_id: Tenant identifier
            user_id: User identifier
            reason: Reason for rollback

        Returns:
            New revision or None if target not found
        """
        async with self.db.acquire() as conn:
            async with conn.transaction():
                await self._set_tenant_context(conn, tenant_id)

                # Get target revision
                target = await conn.fetchrow(
                    """
                    SELECT content, confidence, metadata
                    FROM agent_memory_revisions
                    WHERE memory_id = $1 AND user_id = $2 AND version = $3
                    """,
                    memory_id,
                    user_id,
                    target_version,
                )

                if not target:
                    return None

                # Get current content for diff
                current = await conn.fetchval(
                    """
                    SELECT content
                    FROM agent_memory_revisions
                    WHERE memory_id = $1 AND user_id = $2 AND version_state = $3
                    ORDER BY version DESC
                    LIMIT 1
                    """,
                    memory_id,
                    user_id,
                    MemoryVersion.CURRENT.value,
                )

                # Create rollback revision
                return await self.create_revision(
                    memory_id=memory_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    content=target["content"],
                    previous_content=current,
                    change_reason=f"Rollback to v{target_version}: {reason}",
                    changed_by=user_id,
                    version_state=MemoryVersion.CURRENT,
                    confidence=target["confidence"],
                    metadata={"rollback_from_version": target_version},
                )


# ============================================
# Unified AgentDB Adapter
# ============================================


class AgentDBAdapter:
    """Unified adapter combining all AgentDB memory patterns.

    Provides a single interface for:
    - Session management (persistent confirmations, operation state)
    - Pattern learning (successful interaction patterns)
    - Memory versioning (corrections, audit trail)

    Usage:
        adapter = AgentDBAdapter(db_pool, embedding_provider)

        # Session operations
        await adapter.sessions.set(...)
        data = await adapter.sessions.get_and_delete(...)

        # Pattern learning
        await adapter.patterns.learn(...)
        similar = await adapter.patterns.find_similar(...)

        # Memory versioning
        await adapter.versions.create_revision(...)
        history = await adapter.versions.get_history(...)
    """

    def __init__(
        self,
        db_pool: IAsyncDBPool,
        embedding_provider: Optional[IEmbeddingProvider] = None,
    ):
        """Initialize the AgentDB adapter.

        Args:
            db_pool: Async database connection pool
            embedding_provider: Provider for generating embeddings
        """
        self.sessions = PersistentSessionStore(db_pool)
        self.patterns = PatternLearningStore(db_pool, embedding_provider)
        self.versions = MemoryVersioningStore(db_pool)
        self._db = db_pool
        self._embedding_provider = embedding_provider

    async def cleanup(self, tenant_id: Optional[str] = None) -> dict[str, int]:
        """Run cleanup on all stores.

        Args:
            tenant_id: Optional tenant to clean

        Returns:
            Cleanup statistics
        """
        expired_sessions = await self.sessions.cleanup_expired(tenant_id)

        return {
            "expired_sessions": expired_sessions,
        }
