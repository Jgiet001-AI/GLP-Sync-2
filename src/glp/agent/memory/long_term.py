"""
Long-Term Memory Extraction.

Uses LLM to extract facts, preferences, and entities from
conversation responses for long-term memory storage.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from ..domain.entities import Memory, MemoryType, Message, UserContext

if TYPE_CHECKING:
    from ..domain.ports import ILLMProvider

logger = logging.getLogger(__name__)


@dataclass
class ExtractedFact:
    """A fact extracted from conversation content.

    Attributes:
        content: The extracted fact text
        memory_type: Type of memory (fact, preference, entity, procedure)
        confidence: Confidence score 0-1
        reasoning: Why this was extracted (for debugging)
    """

    content: str
    memory_type: MemoryType
    confidence: float
    reasoning: Optional[str] = None

    def to_memory(
        self,
        tenant_id: str,
        user_id: str,
        source_conversation_id: Optional[UUID] = None,
        source_message_id: Optional[UUID] = None,
    ) -> Memory:
        """Convert to a Memory object for storage."""
        return Memory(
            tenant_id=tenant_id,
            user_id=user_id,
            memory_type=self.memory_type,
            content=self.content,
            confidence=self.confidence,
            source_conversation_id=source_conversation_id,
            source_message_id=source_message_id,
            metadata={"reasoning": self.reasoning} if self.reasoning else {},
        )


class FactExtractor:
    """Extracts facts from conversation content using LLM.

    Uses structured prompting to identify:
    - Facts: Objective information mentioned
    - Preferences: User preferences expressed
    - Entities: Named entities (devices, locations, etc.)
    - Procedures: How-to knowledge

    Usage:
        extractor = FactExtractor(llm_provider)
        facts = await extractor.extract(message.content)

        for fact in facts:
            memory = fact.to_memory(tenant_id, user_id, conv_id, msg_id)
            await memory_store.store(memory)
    """

    # Prompt for fact extraction
    EXTRACTION_PROMPT = """Analyze the following text and extract important information that should be remembered for future conversations.

Extract the following types of information:
1. FACT: Objective information (e.g., "Device X has serial number Y", "The us-west region has 50 switches")
2. PREFERENCE: User preferences (e.g., "User prefers detailed explanations", "User wants notifications for expiring subscriptions")
3. ENTITY: Named entities worth remembering (e.g., "San Jose data center", "Switch model 6200F")
4. PROCEDURE: How-to knowledge (e.g., "To add a device, use the add_device command")

For each extracted item, provide:
- type: FACT, PREFERENCE, ENTITY, or PROCEDURE
- content: The extracted information (clear, standalone statement)
- confidence: 0.0-1.0 (how confident you are this is worth remembering)
- reasoning: Brief explanation of why this is worth remembering

Only extract information that would be useful in future conversations. Skip trivial or obvious information.

Return a JSON array of extracted items. If nothing worth extracting, return an empty array [].

TEXT TO ANALYZE:
{text}

EXTRACTED INFORMATION (JSON array):"""

    # Minimum confidence to accept
    MIN_CONFIDENCE = 0.5

    # Maximum facts per extraction
    MAX_FACTS = 10

    def __init__(
        self,
        llm_provider: Optional["ILLMProvider"] = None,
        min_confidence: float = MIN_CONFIDENCE,
        max_facts: int = MAX_FACTS,
    ):
        """Initialize the fact extractor.

        Args:
            llm_provider: LLM provider for extraction (can be set later)
            min_confidence: Minimum confidence threshold
            max_facts: Maximum facts to extract per call
        """
        self.llm: Optional["ILLMProvider"] = llm_provider
        self.min_confidence = min_confidence
        self.max_facts = max_facts

    def set_llm_provider(self, llm_provider: "ILLMProvider") -> None:
        """Set the LLM provider."""
        self.llm = llm_provider

    async def extract(
        self,
        content: str,
        context: Optional[str] = None,
    ) -> list[ExtractedFact]:
        """Extract facts from content.

        Args:
            content: Text content to analyze
            context: Optional additional context

        Returns:
            List of extracted facts above confidence threshold
        """
        if not self.llm:
            logger.warning("No LLM provider configured for fact extraction")
            return []

        if not content or len(content) < 20:
            return []  # Too short to extract meaningful facts

        # Build prompt
        text_to_analyze = content
        if context:
            text_to_analyze = f"Context: {context}\n\nContent: {content}"

        prompt = self.EXTRACTION_PROMPT.format(text=text_to_analyze)

        try:
            response = await self.llm.complete(
                prompt=prompt,
                max_tokens=1000,
                temperature=0.3,  # Lower temperature for more consistent extraction
            )
            facts = self._parse_response(response)

            # Filter by confidence
            facts = [f for f in facts if f.confidence >= self.min_confidence]

            # Limit count
            facts = facts[: self.max_facts]

            logger.debug(f"Extracted {len(facts)} facts from content")
            return facts

        except Exception as e:
            logger.error(f"Fact extraction failed: {e}")
            return []

    def _parse_response(self, response: str) -> list[ExtractedFact]:
        """Parse LLM response into ExtractedFact objects."""
        facts = []

        # Clean up response - handle markdown code blocks
        response = response.strip()
        if response.startswith("```"):
            lines = response.split("\n")
            # Remove first and last lines (code block markers)
            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            response = "\n".join(lines)

        try:
            data = json.loads(response)
            if not isinstance(data, list):
                data = [data]

            for item in data:
                if not isinstance(item, dict):
                    continue

                # Parse memory type
                type_str = item.get("type", "FACT").upper()
                try:
                    memory_type = MemoryType(type_str.lower())
                except ValueError:
                    memory_type = MemoryType.FACT

                # Parse confidence
                confidence = item.get("confidence", 0.7)
                if isinstance(confidence, str):
                    try:
                        confidence = float(confidence)
                    except ValueError:
                        confidence = 0.7
                confidence = max(0.0, min(1.0, confidence))

                # Get content
                content = item.get("content", "")
                if not content:
                    continue

                facts.append(ExtractedFact(
                    content=content,
                    memory_type=memory_type,
                    confidence=confidence,
                    reasoning=item.get("reasoning"),
                ))

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse fact extraction response: {e}")
            # Try to extract any useful information from non-JSON response
            facts.extend(self._fallback_parse(response))

        return facts

    def _fallback_parse(self, response: str) -> list[ExtractedFact]:
        """Fallback parsing for non-JSON responses."""
        facts = []

        # Look for bullet points or numbered items
        lines = response.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Skip if looks like a header or explanation
            if line.endswith(":") or len(line) < 10:
                continue

            # Remove bullet/number prefix
            for prefix in ["- ", "* ", "• "]:
                if line.startswith(prefix):
                    line = line[len(prefix):]
                    break

            # Check for numbered list
            if line[0].isdigit() and ". " in line[:4]:
                line = line.split(". ", 1)[1]

            if len(line) > 10:
                facts.append(ExtractedFact(
                    content=line,
                    memory_type=MemoryType.FACT,
                    confidence=0.6,  # Lower confidence for fallback
                    reasoning="Extracted via fallback parser",
                ))

        return facts[:5]  # Limit fallback extractions

    async def extract_from_message(
        self,
        message: Message,
        context: UserContext,
        conversation_context: Optional[str] = None,
    ) -> list[Memory]:
        """Extract facts from a message and convert to Memory objects.

        Convenience method that combines extraction and memory creation.

        Args:
            message: Message to extract from
            context: User context
            conversation_context: Optional conversation summary for context

        Returns:
            List of Memory objects ready for storage
        """
        facts = await self.extract(message.content, conversation_context)

        return [
            fact.to_memory(
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                source_conversation_id=message.conversation_id,
                source_message_id=message.id,
            )
            for fact in facts
        ]

    async def should_extract(self, message: Message) -> bool:
        """Determine if a message is worth extracting from.

        Args:
            message: Message to check

        Returns:
            True if message should be processed for extraction
        """
        # Only extract from assistant messages (contains generated info)
        if message.role.value != "assistant":
            return False

        # Skip very short messages
        if len(message.content) < 50:
            return False

        # Skip if message is just a question
        if message.content.strip().endswith("?"):
            return False

        # Skip tool-only responses
        if message.tool_calls and not message.content.strip():
            return False

        return True


class ConversationSummarizer:
    """Summarizes conversations for context and memory.

    Creates concise summaries of long conversations for:
    - Context window management
    - Conversation titles
    - Memory metadata
    """

    SUMMARY_PROMPT = """Summarize the following conversation in 2-3 sentences.
Focus on the main topic, any decisions made, and key information exchanged.

CONVERSATION:
{conversation}

SUMMARY:"""

    TITLE_PROMPT = """Generate a short title (3-6 words) for this conversation.
The title should capture the main topic or purpose.

CONVERSATION:
{conversation}

TITLE:"""

    def __init__(self, llm_provider: Optional["ILLMProvider"] = None):
        """Initialize the summarizer.

        Args:
            llm_provider: LLM provider for summarization
        """
        self.llm: Optional["ILLMProvider"] = llm_provider

    def set_llm_provider(self, llm_provider: "ILLMProvider") -> None:
        """Set the LLM provider."""
        self.llm = llm_provider

    async def summarize(
        self,
        messages: list[Message],
        max_length: int = 500,
    ) -> str:
        """Summarize a conversation.

        Args:
            messages: Messages to summarize
            max_length: Maximum summary length

        Returns:
            Conversation summary
        """
        if not self.llm:
            return self._simple_summarize(messages)

        # Build conversation text
        conversation = self._format_conversation(messages)

        prompt = self.SUMMARY_PROMPT.format(conversation=conversation)

        try:
            summary = await self.llm.complete(
                prompt=prompt,
                max_tokens=200,
                temperature=0.5,
            )
            return summary.strip()[:max_length]
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            return self._simple_summarize(messages)

    async def generate_title(self, messages: list[Message]) -> str:
        """Generate a title for a conversation.

        Args:
            messages: Messages to title

        Returns:
            Conversation title
        """
        if not self.llm:
            return self._simple_title(messages)

        # Use first few messages for title
        conversation = self._format_conversation(messages[:5])

        prompt = self.TITLE_PROMPT.format(conversation=conversation)

        try:
            title = await self.llm.complete(
                prompt=prompt,
                max_tokens=20,
                temperature=0.5,
            )
            return title.strip()[:50]
        except Exception as e:
            logger.error(f"Title generation failed: {e}")
            return self._simple_title(messages)

    def _format_conversation(self, messages: list[Message]) -> str:
        """Format messages for prompting."""
        lines = []
        for msg in messages:
            role = msg.role.value.upper()
            content = msg.content[:500]  # Truncate long messages
            lines.append(f"{role}: {content}")
        return "\n\n".join(lines)

    def _simple_summarize(self, messages: list[Message]) -> str:
        """Simple summarization without LLM."""
        if not messages:
            return "Empty conversation"

        # Get first user message as summary
        for msg in messages:
            if msg.role.value == "user":
                content = msg.content[:200]
                return f"Conversation about: {content}"

        return f"Conversation with {len(messages)} messages"

    def _simple_title(self, messages: list[Message]) -> str:
        """Simple title without LLM."""
        if not messages:
            return "New Conversation"

        # Get first user message
        for msg in messages:
            if msg.role.value == "user":
                words = msg.content.split()[:5]
                return " ".join(words)

        return "Conversation"
