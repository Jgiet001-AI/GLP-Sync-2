"""
Agent Orchestrator.

Main orchestration logic for the agent chatbot. Coordinates:
- LLM calls with streaming
- Tool execution and result handling
- Memory retrieval and storage
- Conversation management
- Event streaming to clients
- Pattern learning (AgentDB integration)
- Persistent session management
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional
from uuid import UUID

from ..domain.entities import (
    ChatEvent,
    ChatEventType,
    Conversation,
    ErrorType,
    Memory,
    Message,
    MessageRole,
    ToolCall,
    UserContext,
)
from ..domain.ports import (
    IConversationStore,
    ILLMProvider,
    IMemoryStore,
)
from ..memory.long_term import ConversationSummarizer, FactExtractor
from ..memory.agentdb import (
    AgentDBAdapter,
    PatternType,
    SessionType,
)
from ..security.cot_redactor import get_redactor
from ..tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for the agent orchestrator.

    Attributes:
        system_prompt: System prompt for the LLM
        max_turns: Maximum conversation turns before forcing stop
        max_tool_calls_per_turn: Maximum tool calls per LLM turn
        memory_search_limit: Number of memories to retrieve
        memory_min_confidence: Minimum confidence for memory results
        enable_fact_extraction: Whether to extract facts from responses
        enable_memory_search: Whether to search memory for context
        enable_pattern_learning: Whether to learn from successful interactions
        enable_pattern_matching: Whether to match patterns for context
        pattern_min_confidence: Minimum confidence for pattern matching
        confirmation_ttl_seconds: TTL for pending confirmations (default 1 hour)
        temperature: LLM temperature
        max_tokens: Maximum tokens per response
    """

    system_prompt: str = """You are a specialized AI assistant for the HPE GreenLake Device Inventory System.

## GUARDRAILS - IMPORTANT
You ONLY handle requests related to:
1. **Data queries** - Devices, subscriptions, tags, sync history from PostgreSQL
2. **Device operations** - Assignments, tag updates, application linking via GreenLake API
3. **System status** - Sync progress, workflow status, operation results

For ANY other request (general knowledge, coding help, unrelated topics), respond:
"I'm the GreenLake Inventory Assistant. I can only help with:
- Querying devices and subscriptions
- Device assignments and tag management
- Sync status and workflow updates

Please ask me about your GreenLake inventory!"

## Data Retrieval (READ operations)
For ALL data queries (devices, subscriptions, counts, lists, searches, etc.):
- Use the `run_query` tool with SQL queries DIRECTLY - do not try other approaches first
- Database tables: devices, subscriptions, device_subscriptions, device_tags, subscription_tags, sync_history
- Common queries:
  - Expired subscriptions: SELECT * FROM subscriptions WHERE end_time < NOW() AND subscription_status = 'STARTED'
  - Device counts: SELECT device_type, COUNT(*) FROM devices WHERE NOT archived GROUP BY device_type
  - Search devices: SELECT * FROM devices WHERE serial_number ILIKE '%pattern%' OR device_name ILIKE '%pattern%'
  - Sync status: SELECT * FROM sync_history ORDER BY started_at DESC LIMIT 10

## Write Operations (via GreenLake API)
For modifications (POST, PATCH, DELETE):
- Adding devices, updating tags, assigning applications/subscriptions
- Always confirm with the user before proceeding

## Response Format
- Present data in clean bullet points or numbered lists
- Summarize key information rather than showing raw tables
- Be concise and helpful"""

    max_turns: int = 10
    max_tool_calls_per_turn: int = 5
    memory_search_limit: int = 5
    memory_min_confidence: float = 0.5
    enable_fact_extraction: bool = True
    enable_memory_search: bool = True
    enable_pattern_learning: bool = True
    enable_pattern_matching: bool = True
    pattern_min_confidence: float = 0.6
    confirmation_ttl_seconds: int = 3600  # 1 hour
    temperature: float = 0.7
    max_tokens: Optional[int] = None


class AgentOrchestrator:
    """Main agent orchestration logic.

    Manages the conversation loop:
    1. Receive user message
    2. Search memory for relevant context
    3. Call LLM with context and tools
    4. Execute tool calls if any
    5. Loop back to LLM with results
    6. Extract facts from final response
    7. Store conversation and memories

    Produces streaming events for real-time UI updates.

    Usage:
        orchestrator = AgentOrchestrator(
            llm_provider=anthropic_provider,
            tool_registry=registry,
            conversation_store=conv_store,
            memory_store=memory_store,
        )

        async for event in orchestrator.chat(
            user_message="Find all switches in us-west",
            context=user_context,
            conversation_id=conv_id,
        ):
            await websocket.send_json(event.to_dict())
    """

    def __init__(
        self,
        llm_provider: ILLMProvider,
        tool_registry: ToolRegistry,
        conversation_store: Optional[IConversationStore] = None,
        memory_store: Optional[IMemoryStore] = None,
        fact_extractor: Optional[FactExtractor] = None,
        summarizer: Optional[ConversationSummarizer] = None,
        agentdb: Optional[AgentDBAdapter] = None,
        config: Optional[AgentConfig] = None,
    ):
        """Initialize the agent orchestrator.

        Args:
            llm_provider: LLM provider for response generation
            tool_registry: Tool registry for read/write operations
            conversation_store: Store for conversation history
            memory_store: Store for semantic memory
            fact_extractor: Extractor for long-term facts
            summarizer: Conversation summarizer
            agentdb: AgentDB adapter for persistent sessions and pattern learning
            config: Agent configuration
        """
        self.llm = llm_provider
        self.tools = tool_registry
        self.conversations = conversation_store
        self.memory = memory_store
        self.fact_extractor = fact_extractor
        self.summarizer = summarizer
        self.agentdb = agentdb
        self.config = config or AgentConfig()

        # Fallback in-memory store for confirmations (when AgentDB not available)
        # Structure: {conversation_id: {operation_id: {...}}}
        self._pending_confirmations: dict[UUID, dict[str, dict[str, Any]]] = {}

    async def chat(
        self,
        user_message: str,
        context: UserContext,
        conversation_id: Optional[UUID] = None,
    ) -> AsyncIterator[ChatEvent]:
        """Process a user message and stream responses.

        Main entry point for the agent. Handles the full conversation loop.

        Args:
            user_message: User's input message
            context: User context (tenant, user, session)
            conversation_id: Existing conversation ID (creates new if None)

        Yields:
            ChatEvent objects for streaming to client
        """
        turn = 0
        sequence = 0

        def next_event(event_type: ChatEventType, **kwargs) -> ChatEvent:
            nonlocal sequence
            sequence += 1
            return ChatEvent(
                type=event_type,
                sequence=sequence,
                correlation_id=context.session_id,
                **kwargs,
            )

        try:
            # Get or create conversation
            conversation = await self._get_or_create_conversation(
                conversation_id, context
            )

            # Store user message
            user_msg = Message(
                role=MessageRole.USER,
                content=user_message,
                conversation_id=conversation.id,
            )
            if self.conversations:
                await self.conversations.add_message(conversation.id, user_msg, context)
            conversation.messages.append(user_msg)

            # Search memory for context
            memory_context = await self._get_memory_context(user_message, context)

            # Get pattern context (similar successful interactions)
            pattern_context = await self._get_pattern_context(user_message, context)

            # Get available tools
            available_tools = await self.tools.get_all_tools()

            # Build system prompt with memory and patterns
            system_prompt = self._build_system_prompt(memory_context, pattern_context)

            # Main conversation loop
            while turn < self.config.max_turns:
                turn += 1

                # Accumulate response
                response_text = ""
                thinking_text = ""
                tool_calls: list[ToolCall] = []
                current_tool_call: Optional[dict[str, Any]] = None

                # Call LLM with streaming
                async for event in self.llm.chat(
                    messages=conversation.messages,
                    tools=available_tools,
                    system_prompt=system_prompt,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                ):
                    # Forward events to client
                    if event.type == ChatEventType.TEXT_DELTA:
                        response_text += event.content or ""
                        yield next_event(
                            ChatEventType.TEXT_DELTA,
                            content=event.content,
                        )

                    elif event.type == ChatEventType.THINKING_DELTA:
                        thinking_text += event.content or ""
                        # Redact sensitive data before streaming to client
                        redacted_chunk = get_redactor().redact(event.content or "").summary
                        yield next_event(
                            ChatEventType.THINKING_DELTA,
                            content=redacted_chunk,
                        )

                    elif event.type == ChatEventType.TOOL_CALL_START:
                        current_tool_call = {
                            "id": event.tool_call_id,
                            "name": event.tool_name,
                            "arguments": {},
                        }
                        yield next_event(
                            ChatEventType.TOOL_CALL_START,
                            tool_call_id=event.tool_call_id,
                            tool_name=event.tool_name,
                        )

                    elif event.type == ChatEventType.TOOL_CALL_END:
                        if current_tool_call:
                            current_tool_call["arguments"] = event.tool_arguments or {}
                            tool_calls.append(
                                ToolCall(
                                    id=current_tool_call["id"],
                                    name=current_tool_call["name"],
                                    arguments=current_tool_call["arguments"],
                                )
                            )
                            yield next_event(
                                ChatEventType.TOOL_CALL_END,
                                tool_call_id=event.tool_call_id,
                                tool_arguments=event.tool_arguments,
                            )
                            current_tool_call = None

                    elif event.type == ChatEventType.ERROR:
                        yield next_event(
                            ChatEventType.ERROR,
                            content=event.content,
                            error_type=event.error_type,
                        )
                        return

                    elif event.type == ChatEventType.DONE:
                        break

                # Redact thinking BEFORE truncation to prevent sensitive data leak
                redacted_thinking = None
                if thinking_text:
                    try:
                        redaction_result = get_redactor().redact(thinking_text)
                        redacted_thinking = redaction_result.summary[:500]
                        if redaction_result.was_redacted:
                            logger.info(
                                f"Redacted {redaction_result.redaction_count} "
                                "sensitive items from CoT before storage"
                            )
                    except Exception as e:
                        # Fallback to safe placeholder on redactor failure
                        logger.warning(f"CoT redaction failed: {e}, using placeholder")
                        redacted_thinking = "[CoT redacted due to processing error]"

                # Create assistant message with REDACTED thinking (never raw)
                assistant_msg = Message(
                    role=MessageRole.ASSISTANT,
                    content=response_text,
                    thinking_summary=redacted_thinking,
                    tool_calls=tool_calls if tool_calls else None,
                    conversation_id=conversation.id,
                )

                # Store assistant message
                if self.conversations:
                    await self.conversations.add_message(
                        conversation.id, assistant_msg, context
                    )
                conversation.messages.append(assistant_msg)

                # If no tool calls, we're done
                if not tool_calls:
                    break

                # Execute tool calls
                for tc in tool_calls[:self.config.max_tool_calls_per_turn]:
                    result = await self._execute_tool_call(tc, context, conversation.id)

                    # Check if confirmation is required
                    if isinstance(result.result, dict) and result.result.get("status") == "confirmation_required":
                        # Store pending confirmation (supports multiple per conversation)
                        operation_id = result.result.get("operation_id")
                        confirmation_data = {
                            "operation_id": operation_id,
                            "tool_call": {
                                "id": tc.id,
                                "name": tc.name,
                                "arguments": tc.arguments,
                            },
                        }

                        # Use AgentDB persistent session store if available
                        if self.agentdb:
                            session_key = f"{conversation.id}:{operation_id}"
                            await self.agentdb.sessions.set(
                                tenant_id=context.tenant_id,
                                user_id=context.user_id,
                                session_type=SessionType.CONFIRMATION,
                                key=session_key,
                                data=confirmation_data,
                                ttl_seconds=self.config.confirmation_ttl_seconds,
                            )
                            logger.debug(f"Stored confirmation in AgentDB: {session_key}")
                        else:
                            # Fallback to in-memory store
                            if conversation.id not in self._pending_confirmations:
                                self._pending_confirmations[conversation.id] = {}
                            self._pending_confirmations[conversation.id][operation_id] = confirmation_data

                        yield next_event(
                            ChatEventType.CONFIRMATION_REQUIRED,
                            tool_call_id=tc.id,
                            content=result.result.get("message"),
                            metadata={
                                "operation_id": result.result.get("operation_id"),
                                "risk_level": result.result.get("risk_level"),
                            },
                        )
                        # Don't continue loop - wait for confirmation
                        return

                    # Send tool result
                    yield next_event(
                        ChatEventType.TOOL_RESULT,
                        tool_call_id=tc.id,
                        content=str(result.result)[:1000],  # Truncate for event
                    )

                    # Learn from successful tool execution (async, non-blocking)
                    if (
                        self.agentdb
                        and self.config.enable_pattern_learning
                        and not result.error
                    ):
                        asyncio.create_task(
                            self._learn_pattern(
                                tenant_id=context.tenant_id,
                                pattern_type=PatternType.TOOL_SUCCESS,
                                trigger=user_message,
                                response=tc.name,
                                context={
                                    "arguments": tc.arguments,
                                    "result_preview": str(result.result)[:100],
                                },
                                success=True,
                            )
                        )

                    # Add tool result as message
                    tool_msg = Message(
                        role=MessageRole.TOOL,
                        content=str(result.result),
                        tool_calls=[result],
                        conversation_id=conversation.id,
                    )
                    if self.conversations:
                        await self.conversations.add_message(
                            conversation.id, tool_msg, context
                        )
                    conversation.messages.append(tool_msg)

            # Extract facts from response (async, don't block)
            if self.config.enable_fact_extraction and response_text:
                asyncio.create_task(
                    self._extract_and_store_facts(
                        response_text, conversation.id, assistant_msg.id, context
                    )
                )

            # Done
            yield next_event(
                ChatEventType.DONE,
                metadata={
                    "conversation_id": str(conversation.id),
                    "turns": turn,
                },
            )

        except Exception as e:
            logger.exception(f"Chat error: {e}")
            yield next_event(
                ChatEventType.ERROR,
                content=f"An error occurred: {str(e)}",
                error_type=ErrorType.FATAL,
            )

    async def confirm_operation(
        self,
        conversation_id: UUID,
        confirmed: bool,
        context: UserContext,
        operation_id: Optional[str] = None,
    ) -> AsyncIterator[ChatEvent]:
        """Handle user confirmation for a pending operation.

        Args:
            conversation_id: Conversation with pending operation
            confirmed: Whether user confirmed
            context: User context
            operation_id: Specific operation to confirm (optional, uses first if not provided)

        Yields:
            ChatEvent objects
        """
        sequence = 0

        def next_event(event_type: ChatEventType, **kwargs) -> ChatEvent:
            nonlocal sequence
            sequence += 1
            return ChatEvent(
                type=event_type,
                sequence=sequence,
                correlation_id=context.session_id,
                **kwargs,
            )

        pending = None

        # Try AgentDB persistent session store first
        if self.agentdb:
            if operation_id:
                session_key = f"{conversation_id}:{operation_id}"
                session = await self.agentdb.sessions.get_and_delete(
                    tenant_id=context.tenant_id,
                    user_id=context.user_id,
                    session_type=SessionType.CONFIRMATION,
                    key=session_key,
                )
                if session:
                    pending = session.data
                    logger.debug(f"Retrieved confirmation from AgentDB: {session_key}")
            else:
                # List all confirmations for this conversation and get first
                sessions = await self.agentdb.sessions.list_by_type(
                    tenant_id=context.tenant_id,
                    user_id=context.user_id,
                    session_type=SessionType.CONFIRMATION,
                    prefix=f"{conversation_id}:",
                )
                if sessions:
                    first_session = sessions[0]
                    pending = first_session.data
                    operation_id = pending.get("operation_id")
                    # Delete it
                    await self.agentdb.sessions.delete(
                        tenant_id=context.tenant_id,
                        user_id=context.user_id,
                        session_type=SessionType.CONFIRMATION,
                        key=first_session.key,
                    )
                    logger.debug(f"Retrieved first confirmation from AgentDB: {first_session.key}")

        # Fallback to in-memory store
        if not pending:
            conv_confirmations = self._pending_confirmations.get(conversation_id, {})

            if not conv_confirmations:
                yield next_event(
                    ChatEventType.ERROR,
                    content="No pending operation to confirm",
                    error_type=ErrorType.RECOVERABLE,
                )
                return

            # Get the specific operation or the first one
            if operation_id and operation_id in conv_confirmations:
                pending = conv_confirmations.pop(operation_id)
            elif conv_confirmations:
                # Use first available operation for backward compatibility
                first_op_id = next(iter(conv_confirmations))
                pending = conv_confirmations.pop(first_op_id)
                operation_id = pending.get("operation_id")
            else:
                yield next_event(
                    ChatEventType.ERROR,
                    content="No pending operation to confirm",
                    error_type=ErrorType.RECOVERABLE,
                )
                return

            # Clean up empty conversation entry
            if not conv_confirmations:
                self._pending_confirmations.pop(conversation_id, None)

        if not pending:
            yield next_event(
                ChatEventType.ERROR,
                content="No pending operation to confirm",
                error_type=ErrorType.RECOVERABLE,
            )
            return

        yield next_event(
            ChatEventType.CONFIRMATION_RESPONSE,
            metadata={"confirmed": confirmed, "operation_id": operation_id},
        )

        if not confirmed:
            yield next_event(
                ChatEventType.TEXT_DELTA,
                content="Operation cancelled.",
            )
            yield next_event(ChatEventType.DONE)
            return

        # Execute the confirmed operation
        tool_call_data = pending.get("tool_call", {})

        # Reconstruct ToolCall if stored as dict (from AgentDB)
        if isinstance(tool_call_data, dict):
            tool_call = ToolCall(
                id=tool_call_data.get("id", "unknown"),
                name=tool_call_data.get("name", "unknown"),
                arguments=tool_call_data.get("arguments", {}),
            )
        else:
            tool_call = tool_call_data

        if self.tools.write_executor:
            try:
                from uuid import UUID as UUID_Type
                op_id = UUID_Type(operation_id)
                operation = await self.tools.write_executor.confirm_operation(
                    op_id, context
                )

                if operation.error:
                    yield next_event(
                        ChatEventType.ERROR,
                        content=f"Operation failed: {operation.error}",
                        error_type=ErrorType.RECOVERABLE,
                    )
                    # Learn from failure (if pattern learning enabled)
                    if self.agentdb and self.config.enable_pattern_learning and tool_call:
                        asyncio.create_task(
                            self._learn_pattern(
                                tenant_id=context.tenant_id,
                                pattern_type=PatternType.ERROR_RECOVERY,
                                trigger=f"Tool '{tool_call.name}' failed: {operation.error}",
                                response=f"Retry or escalate: {tool_call.name}",
                                context={"error": operation.error, "tool": tool_call.name},
                                success=False,
                            )
                        )
                else:
                    yield next_event(
                        ChatEventType.TOOL_RESULT,
                        tool_call_id=tool_call.id if tool_call else "unknown",
                        content=f"Operation completed successfully: {operation.result}",
                    )
                    yield next_event(
                        ChatEventType.TEXT_DELTA,
                        content="Done! The operation completed successfully.",
                    )
                    # Learn from success (if pattern learning enabled)
                    if self.agentdb and self.config.enable_pattern_learning and tool_call:
                        asyncio.create_task(
                            self._learn_pattern(
                                tenant_id=context.tenant_id,
                                pattern_type=PatternType.TOOL_SUCCESS,
                                trigger=f"User requested: {tool_call.name} with {tool_call.arguments}",
                                response=tool_call.name,
                                context={"arguments": tool_call.arguments, "result": str(operation.result)[:200]},
                                success=True,
                            )
                        )

            except Exception as e:
                logger.exception(f"Confirmation execution failed: {e}")
                yield next_event(
                    ChatEventType.ERROR,
                    content=f"Failed to execute operation: {e}",
                    error_type=ErrorType.RECOVERABLE,
                )

        yield next_event(ChatEventType.DONE)

    async def cancel_chat(
        self,
        conversation_id: UUID,
        context: UserContext,
    ) -> None:
        """Cancel an ongoing chat and cleanup.

        Args:
            conversation_id: Conversation to cancel
            context: User context
        """
        # Remove pending confirmations from AgentDB if available
        if self.agentdb:
            sessions = await self.agentdb.sessions.list_by_type(
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                session_type=SessionType.CONFIRMATION,
                prefix=f"{conversation_id}:",
            )
            for session in sessions:
                await self.agentdb.sessions.delete(
                    tenant_id=context.tenant_id,
                    user_id=context.user_id,
                    session_type=SessionType.CONFIRMATION,
                    key=session.key,
                )
            if sessions:
                logger.debug(f"Cleaned up {len(sessions)} AgentDB sessions for conversation {conversation_id}")

        # Also clean up in-memory store
        self._pending_confirmations.pop(conversation_id, None)

        logger.info(f"Cancelled chat for conversation {conversation_id}")

    async def _learn_pattern(
        self,
        tenant_id: str,
        pattern_type: PatternType,
        trigger: str,
        response: str,
        context: dict[str, Any],
        success: bool,
    ) -> None:
        """Learn a pattern from an interaction.

        Called asynchronously after tool executions to capture successful patterns.

        Args:
            tenant_id: Tenant identifier
            pattern_type: Type of pattern
            trigger: What triggered this pattern
            response: The response/action taken
            context: Additional context
            success: Whether this was successful
        """
        if not self.agentdb:
            return

        try:
            pattern = await self.agentdb.patterns.learn(
                tenant_id=tenant_id,
                pattern_type=pattern_type,
                trigger=trigger,
                response=response,
                context=context,
                success=success,
            )
            logger.debug(
                f"Learned pattern {pattern_type.value}: "
                f"confidence={pattern.confidence:.2f}, "
                f"success_rate={pattern.success_rate:.2f}"
            )
        except Exception as e:
            logger.warning(f"Failed to learn pattern: {e}")

    async def _get_pattern_context(
        self,
        query: str,
        context: UserContext,
    ) -> list[tuple[Any, float]]:
        """Get relevant patterns for context.

        Searches for similar successful patterns to inform the response.

        Args:
            query: User's query
            context: User context

        Returns:
            List of (pattern, similarity) tuples
        """
        if not self.agentdb or not self.config.enable_pattern_matching:
            return []

        try:
            patterns = await self.agentdb.patterns.find_similar(
                tenant_id=context.tenant_id,
                query=query,
                limit=3,
                min_confidence=self.config.pattern_min_confidence,
            )
            return patterns
        except Exception as e:
            logger.warning(f"Pattern search failed: {e}")
            return []

    async def _get_or_create_conversation(
        self,
        conversation_id: Optional[UUID],
        context: UserContext,
    ) -> Conversation:
        """Get existing or create new conversation.

        Args:
            conversation_id: Existing ID or None
            context: User context

        Returns:
            Conversation object
        """
        if conversation_id and self.conversations:
            conversation = await self.conversations.get(conversation_id, context)
            if conversation:
                return conversation

        # Create new conversation
        conversation = Conversation(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
        )

        if self.conversations:
            conversation = await self.conversations.create(conversation)

        return conversation

    async def _get_memory_context(
        self,
        query: str,
        context: UserContext,
    ) -> list[Memory]:
        """Search memory for relevant context.

        Args:
            query: User's query
            context: User context

        Returns:
            List of relevant memories
        """
        if not self.config.enable_memory_search or not self.memory:
            return []

        try:
            results = await self.memory.search(
                query=query,
                context=context,
                embedding_model=self.llm.embedding_model if hasattr(self.llm, 'embedding_model') else "text-embedding-3-large",
                limit=self.config.memory_search_limit,
                min_confidence=self.config.memory_min_confidence,
            )
            return [memory for memory, _ in results]

        except Exception as e:
            logger.warning(f"Memory search failed: {e}")
            return []

    def _build_system_prompt(
        self,
        memories: list[Memory],
        patterns: Optional[list[tuple[Any, float]]] = None,
    ) -> str:
        """Build system prompt with memory and pattern context.

        Args:
            memories: Relevant memories to include
            patterns: Relevant learned patterns to include

        Returns:
            Complete system prompt
        """
        prompt = self.config.system_prompt

        if memories:
            memory_context = "\n\nRelevant context from previous conversations:\n"
            for mem in memories:
                memory_context += f"- [{mem.memory_type.value}] {mem.content}\n"
            prompt += memory_context

        if patterns:
            pattern_context = "\n\nSuccessful patterns from previous interactions:\n"
            for pattern, similarity in patterns:
                if similarity > 0.7:  # Only include highly similar patterns
                    pattern_context += f"- When asked similar to '{pattern.trigger[:50]}...', used '{pattern.response}' (confidence: {pattern.confidence:.0%})\n"
            if pattern_context != "\n\nSuccessful patterns from previous interactions:\n":
                prompt += pattern_context

        return prompt

    async def _execute_tool_call(
        self,
        tool_call: ToolCall,
        context: UserContext,
        conversation_id: UUID,
    ) -> ToolCall:
        """Execute a tool call.

        Args:
            tool_call: Tool call to execute
            context: User context
            conversation_id: Current conversation

        Returns:
            Tool call with result
        """
        logger.info(f"Executing tool: {tool_call.name}")

        try:
            result = await self.tools.execute_tool_call(tool_call, context)
            logger.debug(f"Tool {tool_call.name} result: {result.result}")
            return result

        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            tool_call.result = {
                "error": str(e),
                "recoverable": True,
            }
            return tool_call

    async def _extract_and_store_facts(
        self,
        content: str,
        conversation_id: UUID,
        message_id: UUID,
        context: UserContext,
    ) -> None:
        """Extract facts from content and store in memory.

        Args:
            content: Text to extract from
            conversation_id: Source conversation
            message_id: Source message
            context: User context
        """
        if not self.fact_extractor or not self.memory:
            return

        try:
            facts = await self.fact_extractor.extract(content)

            for fact in facts:
                memory = fact.to_memory(
                    tenant_id=context.tenant_id,
                    user_id=context.user_id,
                    source_conversation_id=conversation_id,
                    source_message_id=message_id,
                )
                await self.memory.store(memory)

            if facts:
                logger.info(f"Extracted and stored {len(facts)} facts")

        except Exception as e:
            logger.warning(f"Fact extraction failed: {e}")

    async def get_conversation_history(
        self,
        conversation_id: UUID,
        context: UserContext,
        limit: int = 50,
    ) -> Optional[Conversation]:
        """Get conversation history.

        Args:
            conversation_id: Conversation ID
            context: User context
            limit: Max messages to return

        Returns:
            Conversation with messages
        """
        if not self.conversations:
            return None

        return await self.conversations.get(conversation_id, context)

    async def list_conversations(
        self,
        context: UserContext,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Conversation]:
        """List user's conversations.

        Args:
            context: User context
            limit: Max conversations
            offset: Pagination offset

        Returns:
            List of conversations
        """
        if not self.conversations:
            return []

        return await self.conversations.list(context, limit, offset)
