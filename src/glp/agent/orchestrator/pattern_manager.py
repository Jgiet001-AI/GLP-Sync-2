"""
Pattern Manager for Agent Orchestrator.

Encapsulates pattern learning and matching operations:
- Learning successful interaction patterns
- Finding similar patterns for context
- Building pattern-based context for prompts
- Managing pattern confidence and statistics

Extracted from AgentOrchestrator to improve modularity and testability.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..domain.entities import UserContext
from ..memory.agentdb import (
    AgentDBAdapter,
    LearnedPattern,
    PatternType,
)

logger = logging.getLogger(__name__)


class PatternManager:
    """Manages pattern learning and matching operations for the agent.

    Responsibilities:
    - Learn from successful tool executions and workflows
    - Find similar patterns for context enrichment
    - Build pattern context for system prompts
    - Manage pattern confidence and statistics

    Usage:
        pattern_manager = PatternManager(
            agentdb=agentdb_adapter,
            match_limit=3,
            min_confidence=0.6,
        )

        # Learn from successful interaction
        await pattern_manager.learn_pattern(
            tenant_id="tenant-123",
            pattern_type=PatternType.TOOL_SUCCESS,
            trigger="Find all switches in us-west",
            response="search_devices",
            context={"region": "us-west"},
            success=True,
        )

        # Find similar patterns
        patterns = await pattern_manager.find_similar_patterns(
            query="Show me devices in western region",
            context=user_context,
            pattern_type=PatternType.TOOL_SUCCESS,
        )

        # Build context for prompt
        context_text = pattern_manager.build_pattern_context(patterns)
    """

    def __init__(
        self,
        agentdb: Optional[AgentDBAdapter] = None,
        match_limit: int = 3,
        min_confidence: float = 0.6,
        enable_learning: bool = True,
        enable_matching: bool = True,
    ):
        """Initialize the pattern manager.

        Args:
            agentdb: AgentDB adapter for pattern storage
            match_limit: Maximum patterns to retrieve per search
            min_confidence: Minimum confidence threshold for matches
            enable_learning: Whether pattern learning is enabled
            enable_matching: Whether pattern matching is enabled
        """
        self.agentdb = agentdb
        self.match_limit = match_limit
        self.min_confidence = min_confidence
        self.enable_learning = enable_learning
        self.enable_matching = enable_matching

    async def learn_pattern(
        self,
        tenant_id: str,
        pattern_type: PatternType,
        trigger: str,
        response: str,
        context: Optional[dict[str, Any]] = None,
        success: bool = True,
    ) -> Optional[LearnedPattern]:
        """Learn a pattern from an interaction.

        Stores or reinforces a pattern based on an interaction outcome.
        If the pattern already exists, updates its confidence and counts.

        Args:
            tenant_id: Tenant identifier
            pattern_type: Type of pattern (tool success, error recovery, etc.)
            trigger: What triggered this pattern (user query, error message, etc.)
            response: The response/action taken
            context: Additional context (arguments, results, metadata)
            success: Whether this was a successful execution

        Returns:
            Learned pattern with updated stats, or None if learning disabled
        """
        if not self.enable_learning or not self.agentdb:
            logger.debug("Pattern learning disabled or AgentDB unavailable")
            return None

        try:
            pattern = await self.agentdb.patterns.learn(
                tenant_id=tenant_id,
                pattern_type=pattern_type,
                trigger=trigger,
                response=response,
                context=context or {},
                success=success,
            )

            logger.debug(
                f"Learned pattern {pattern_type.value}: "
                f"trigger='{trigger[:50]}...', "
                f"response='{response}', "
                f"confidence={pattern.confidence:.2f}, "
                f"success_rate={pattern.success_rate:.2f}"
            )

            return pattern

        except Exception as e:
            logger.warning(f"Failed to learn pattern: {e}")
            return None

    async def find_similar_patterns(
        self,
        query: str,
        context: UserContext,
        pattern_type: Optional[PatternType] = None,
    ) -> list[tuple[LearnedPattern, float]]:
        """Find similar patterns using semantic search.

        Searches for patterns that match the query semantically,
        useful for providing context from previous successful interactions.

        Args:
            query: Query text to match against
            context: User context for tenant isolation
            pattern_type: Optional filter by pattern type

        Returns:
            List of (pattern, similarity_score) tuples sorted by similarity
        """
        if not self.enable_matching or not self.agentdb:
            logger.debug("Pattern matching disabled or AgentDB unavailable")
            return []

        try:
            patterns = await self.agentdb.patterns.find_similar(
                tenant_id=context.tenant_id,
                query=query,
                pattern_type=pattern_type,
                limit=self.match_limit,
                min_confidence=self.min_confidence,
            )

            if patterns:
                logger.debug(
                    f"Found {len(patterns)} similar patterns for query: {query[:50]}..."
                )

            return patterns

        except Exception as e:
            logger.warning(f"Pattern search failed: {e}")
            return []

    async def get_patterns_by_type(
        self,
        tenant_id: str,
        pattern_type: PatternType,
        limit: int = 20,
    ) -> list[LearnedPattern]:
        """Get patterns by type, sorted by confidence.

        Retrieves patterns of a specific type, useful for analyzing
        what the agent has learned in a particular category.

        Args:
            tenant_id: Tenant identifier
            pattern_type: Type of patterns to retrieve
            limit: Maximum patterns to return

        Returns:
            List of patterns sorted by confidence
        """
        if not self.agentdb:
            logger.debug("AgentDB unavailable")
            return []

        try:
            patterns = await self.agentdb.patterns.get_by_type(
                tenant_id=tenant_id,
                pattern_type=pattern_type,
                limit=limit,
            )

            logger.debug(f"Retrieved {len(patterns)} patterns of type {pattern_type.value}")
            return patterns

        except Exception as e:
            logger.warning(f"Failed to get patterns by type: {e}")
            return []

    async def deactivate_pattern(
        self,
        tenant_id: str,
        pattern_id: Any,
    ) -> bool:
        """Deactivate a pattern (soft delete).

        Marks a pattern as inactive so it won't be matched in future searches.
        Useful for removing incorrect or outdated patterns.

        Args:
            tenant_id: Tenant identifier
            pattern_id: Pattern ID to deactivate

        Returns:
            True if deactivated successfully, False otherwise
        """
        if not self.agentdb:
            logger.debug("AgentDB unavailable")
            return False

        try:
            result = await self.agentdb.patterns.deactivate(
                tenant_id=tenant_id,
                pattern_id=pattern_id,
            )

            if result:
                logger.info(f"Deactivated pattern {pattern_id}")

            return result

        except Exception as e:
            logger.warning(f"Failed to deactivate pattern {pattern_id}: {e}")
            return False

    def build_pattern_context(
        self,
        patterns: list[tuple[LearnedPattern, float]],
        similarity_threshold: float = 0.7,
    ) -> str:
        """Build context string from patterns for system prompt.

        Creates a formatted context string highlighting successful patterns
        that are highly similar to the current query.

        Args:
            patterns: List of (pattern, similarity_score) tuples
            similarity_threshold: Minimum similarity to include in context

        Returns:
            Formatted context string (empty if no highly similar patterns)
        """
        if not patterns:
            return ""

        # Filter to highly similar patterns
        relevant_patterns = [
            (pattern, sim)
            for pattern, sim in patterns
            if sim >= similarity_threshold
        ]

        if not relevant_patterns:
            return ""

        context = "\n\nSuccessful patterns from previous interactions:\n"
        for pattern, similarity in relevant_patterns:
            # Truncate trigger for readability
            trigger_preview = pattern.trigger[:50]
            if len(pattern.trigger) > 50:
                trigger_preview += "..."

            context += (
                f"- When asked similar to '{trigger_preview}', "
                f"used '{pattern.response}' "
                f"(confidence: {pattern.confidence:.0%}, similarity: {similarity:.0%})\n"
            )

        return context

    async def learn_tool_success(
        self,
        tenant_id: str,
        trigger: str,
        tool_name: str,
        arguments: dict[str, Any],
        result_preview: str,
    ) -> Optional[LearnedPattern]:
        """Convenience method for learning successful tool executions.

        Args:
            tenant_id: Tenant identifier
            trigger: User message that triggered the tool
            tool_name: Name of the tool that was executed
            arguments: Tool arguments
            result_preview: Brief preview of the result

        Returns:
            Learned pattern or None
        """
        return await self.learn_pattern(
            tenant_id=tenant_id,
            pattern_type=PatternType.TOOL_SUCCESS,
            trigger=trigger,
            response=tool_name,
            context={
                "arguments": arguments,
                "result_preview": result_preview,
            },
            success=True,
        )

    async def learn_error_recovery(
        self,
        tenant_id: str,
        error_trigger: str,
        recovery_action: str,
        error_details: str,
        tool_name: str,
    ) -> Optional[LearnedPattern]:
        """Convenience method for learning error recovery patterns.

        Args:
            tenant_id: Tenant identifier
            error_trigger: What caused the error
            recovery_action: How to recover from this error
            error_details: Error message or details
            tool_name: Tool that failed

        Returns:
            Learned pattern or None
        """
        return await self.learn_pattern(
            tenant_id=tenant_id,
            pattern_type=PatternType.ERROR_RECOVERY,
            trigger=error_trigger,
            response=recovery_action,
            context={
                "error": error_details,
                "tool": tool_name,
            },
            success=False,
        )

    async def learn_query_response(
        self,
        tenant_id: str,
        question: str,
        answer: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[LearnedPattern]:
        """Convenience method for learning question-answer patterns.

        Args:
            tenant_id: Tenant identifier
            question: User's question
            answer: Agent's answer
            metadata: Additional metadata

        Returns:
            Learned pattern or None
        """
        return await self.learn_pattern(
            tenant_id=tenant_id,
            pattern_type=PatternType.QUERY_RESPONSE,
            trigger=question,
            response=answer,
            context=metadata or {},
            success=True,
        )

    async def learn_workflow(
        self,
        tenant_id: str,
        workflow_trigger: str,
        workflow_steps: list[str],
        outcome: str,
        success: bool = True,
    ) -> Optional[LearnedPattern]:
        """Convenience method for learning multi-step workflows.

        Args:
            tenant_id: Tenant identifier
            workflow_trigger: What triggered the workflow
            workflow_steps: List of steps executed
            outcome: Final outcome
            success: Whether workflow succeeded

        Returns:
            Learned pattern or None
        """
        return await self.learn_pattern(
            tenant_id=tenant_id,
            pattern_type=PatternType.WORKFLOW,
            trigger=workflow_trigger,
            response=" -> ".join(workflow_steps),
            context={
                "steps": workflow_steps,
                "outcome": outcome,
            },
            success=success,
        )

    async def get_pattern_stats(
        self,
        tenant_id: str,
    ) -> dict[str, Any]:
        """Get pattern statistics for a tenant.

        Provides insights into learned patterns across all types.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Statistics dict with counts and metrics by pattern type
        """
        if not self.agentdb:
            return {
                "by_type": {},
                "total": 0,
                "avg_confidence": 0.0,
            }

        try:
            stats = {
                "by_type": {},
                "total": 0,
                "avg_confidence": 0.0,
            }

            total_patterns = 0
            total_confidence = 0.0

            # Get stats for each pattern type
            for pattern_type in PatternType:
                patterns = await self.get_patterns_by_type(
                    tenant_id=tenant_id,
                    pattern_type=pattern_type,
                    limit=100,  # Get more for stats
                )

                count = len(patterns)
                avg_conf = sum(p.confidence for p in patterns) / count if count > 0 else 0.0

                stats["by_type"][pattern_type.value] = {
                    "count": count,
                    "avg_confidence": avg_conf,
                }

                total_patterns += count
                total_confidence += sum(p.confidence for p in patterns)

            stats["total"] = total_patterns
            stats["avg_confidence"] = (
                total_confidence / total_patterns if total_patterns > 0 else 0.0
            )

            return stats

        except Exception as e:
            logger.warning(f"Failed to get pattern stats: {e}")
            return {
                "by_type": {},
                "total": 0,
                "avg_confidence": 0.0,
            }
