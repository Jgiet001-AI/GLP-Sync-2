"""
Prompt Builder for Agent Orchestrator.

Encapsulates system prompt construction:
- Building prompts from base configuration
- Adding memory context to prompts
- Adding pattern context to prompts
- Formatting context sections

Extracted from AgentOrchestrator to improve modularity and testability.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..domain.entities import Memory

logger = logging.getLogger(__name__)


class PromptBuilder:
    """Manages system prompt construction for the agent.

    Responsibilities:
    - Build complete system prompts from base templates
    - Add relevant memory context to prompts
    - Add learned pattern context to prompts
    - Format context sections consistently

    Usage:
        prompt_builder = PromptBuilder(
            pattern_similarity_threshold=0.7,
        )

        # Build complete prompt with context
        system_prompt = prompt_builder.build(
            base_prompt=config.system_prompt,
            memories=relevant_memories,
            patterns=matching_patterns,
        )
    """

    def __init__(
        self,
        pattern_similarity_threshold: float = 0.7,
    ):
        """Initialize the prompt builder.

        Args:
            pattern_similarity_threshold: Minimum similarity for including patterns
        """
        self.pattern_similarity_threshold = pattern_similarity_threshold

    def build(
        self,
        base_prompt: str,
        memories: Optional[list[Memory]] = None,
        patterns: Optional[list[tuple[Any, float]]] = None,
    ) -> str:
        """Build system prompt with memory and pattern context.

        Constructs a complete system prompt by:
        1. Starting with the base prompt from config
        2. Appending relevant memory context if available
        3. Appending learned pattern context if available

        Args:
            base_prompt: Base system prompt template
            memories: Relevant memories to include as context
            patterns: Relevant learned patterns to include (pattern, similarity score)

        Returns:
            Complete system prompt with all context sections
        """
        prompt = base_prompt

        # Add memory context if available
        if memories:
            memory_context = "\n\nRelevant context from previous conversations:\n"
            for mem in memories:
                memory_context += f"- [{mem.memory_type.value}] {mem.content}\n"
            prompt += memory_context

        # Add pattern context if available
        if patterns:
            pattern_context = "\n\nSuccessful patterns from previous interactions:\n"
            for pattern, similarity in patterns:
                # Only include highly similar patterns
                if similarity > self.pattern_similarity_threshold:
                    pattern_context += f"- When asked similar to '{pattern.trigger[:50]}...', used '{pattern.response}' (confidence: {pattern.confidence:.0%})\n"

            # Only append if we actually added patterns
            if pattern_context != "\n\nSuccessful patterns from previous interactions:\n":
                prompt += pattern_context

        return prompt
