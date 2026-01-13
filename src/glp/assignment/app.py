"""FastAPI application for device assignment.

This is the main entry point for the assignment API server.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.clients_router import router as clients_router
from .api.dashboard_router import router as dashboard_router
from .api.dependencies import (
    close_db_pool,
    close_glp_client,
    init_db_pool,
    init_glp_client,
)
from .api.router import router

# Import reports router
from ..reports.api import router as reports_router

# Import agent router and components (optional - only if agent module exists)
try:
    from ..agent import (
        AgentConfig,
        AgentOrchestrator,
        AnthropicProvider,
        OpenAIProvider,
        ToolRegistry,
    )
    from ..agent.api import create_agent_dependencies
    from ..agent.api import router as agent_router
    from ..agent.providers.base import LLMProviderConfig
    from ..agent.security import TicketAuth
    from ..agent.tools.mcp_client import MCPClient, MCPClientConfig
    from ..agent.background_worker import (
        init_background_worker,
        shutdown_background_worker,
    )
    AGENT_AVAILABLE = True
except ImportError:
    AGENT_AVAILABLE = False
    agent_router = None
    create_agent_dependencies = None
    TicketAuth = None
    MCPClient = None
    MCPClientConfig = None
    init_background_worker = None
    shutdown_background_worker = None

# Redis client (for WebSocket ticket auth)
_redis_client = None

# Chatbot availability flag (set during init)
_chatbot_enabled = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _init_agent_orchestrator(redis_client=None) -> None:
    """Initialize the agent orchestrator with LLM provider and tools.

    Args:
        redis_client: Optional Redis client for WebSocket ticket auth
    """
    if not AGENT_AVAILABLE or not create_agent_dependencies:
        logger.info("Agent module not available, skipping orchestrator init")
        return

    # Check for API keys
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if not anthropic_key and not openai_key:
        logger.warning("No LLM API keys configured (ANTHROPIC_API_KEY or OPENAI_API_KEY)")
        return

    llm_provider = None

    # Try Anthropic first
    if anthropic_key:
        try:
            config = LLMProviderConfig(
                api_key=anthropic_key,
                model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929"),
            )
            llm_provider = AnthropicProvider(config)
            logger.info(f"Using Anthropic provider with model: {config.model}")
        except Exception as e:
            logger.warning(f"Failed to initialize Anthropic provider: {e}")

    # Fall back to OpenAI if Anthropic failed
    if not llm_provider and openai_key:
        try:
            config = LLMProviderConfig(
                api_key=openai_key,
                model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            )
            llm_provider = OpenAIProvider(config)
            logger.info(f"Using OpenAI provider with model: {config.model}")
        except Exception as e:
            logger.warning(f"Failed to initialize OpenAI provider: {e}")

    if not llm_provider:
        logger.warning("No LLM provider could be initialized - chatbot will be unavailable")
        return

    # Create OpenAI embedding provider (needed for semantic memory even with Anthropic chat)
    embedding_provider = None
    if openai_key:
        try:
            embedding_config = LLMProviderConfig(
                api_key=openai_key,
                model="gpt-4o",  # Not used for embeddings
                embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"),
            )
            embedding_provider = OpenAIProvider(embedding_config)
            logger.info(f"Embedding provider configured: {embedding_config.embedding_model}")
        except Exception as e:
            logger.warning(f"Failed to initialize embedding provider: {e}")

    try:
        # Create MCP client for read-only database operations
        mcp_client = None
        mcp_server_url = os.getenv("MCP_SERVER_URL", "http://mcp-server:8000")
        if MCPClient and MCPClientConfig:
            try:
                mcp_config = MCPClientConfig(base_url=mcp_server_url)
                mcp_client = MCPClient(mcp_config)
                logger.info(f"MCP client configured for: {mcp_server_url}")
            except Exception as e:
                logger.warning(f"Failed to initialize MCP client: {e}")

        # Create tool registry with MCP client for database queries
        tool_registry = ToolRegistry(mcp_client=mcp_client)

        # Create orchestrator with embedding provider for semantic memory
        orchestrator = AgentOrchestrator(
            llm_provider=llm_provider,
            tool_registry=tool_registry,
            config=AgentConfig(),
            # embedding_provider is passed to memory store inside orchestrator if needed
        )

        # Initialize ticket auth if Redis is available
        ticket_auth = None
        if redis_client and TicketAuth:
            ticket_auth = TicketAuth(redis_client)
            logger.info("WebSocket ticket auth initialized with Redis")
        else:
            logger.warning("Redis not available - WebSocket ticket auth disabled")

        # Register with router
        create_agent_dependencies(orchestrator, ticket_auth)
        logger.info("Agent orchestrator initialized successfully")

        # Mark chatbot as enabled
        global _chatbot_enabled
        _chatbot_enabled = True

    except Exception as e:
        logger.error(f"Failed to initialize agent orchestrator: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager.

    Handles startup and shutdown events:
    - Startup: Initialize database pool, GLP client, and Redis
    - Shutdown: Close Redis, GLP client, and database pool
    """
    global _redis_client

    # Startup
    logger.info("Starting Device Assignment API...")

    try:
        await init_db_pool()
        logger.info("Database pool initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database pool: {e}")
        raise

    try:
        await init_glp_client()
        logger.info("GLP client initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize GLP client: {e}")
        # Don't fail startup - some endpoints work without GLP client
        # (e.g., upload, get_options from DB)

    # Initialize Redis for WebSocket ticket auth
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            import redis.asyncio as redis
            _redis_client = redis.from_url(redis_url, decode_responses=True)
            # Test connection
            await _redis_client.ping()
            logger.info(f"Redis connected: {redis_url}")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}")
            _redis_client = None
    else:
        logger.warning("REDIS_URL not configured - WebSocket ticket auth will be unavailable")

    # Initialize background worker for async tasks (pattern learning, fact extraction)
    if AGENT_AVAILABLE and init_background_worker:
        try:
            await init_background_worker(max_queue_size=100, max_concurrent=5)
            logger.info("Background worker initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize background worker: {e}")

    # Initialize agent orchestrator with Redis
    _init_agent_orchestrator(_redis_client)

    yield

    # Shutdown (reverse order of initialization)
    logger.info("Shutting down Device Assignment API...")

    # Shutdown background worker first (allow tasks to complete)
    if AGENT_AVAILABLE and shutdown_background_worker:
        try:
            await shutdown_background_worker(timeout=30.0)
            logger.info("Background worker stopped")
        except Exception as e:
            logger.warning(f"Error stopping background worker: {e}")

    # Close Redis
    if _redis_client:
        await _redis_client.aclose()
        logger.info("Redis connection closed")

    await close_glp_client()
    logger.info("GLP client closed")

    await close_db_pool()
    logger.info("Database pool closed")


# Create FastAPI application
app = FastAPI(
    title="HPE GreenLake Device Assignment API",
    description="""
    API for bulk device assignment operations.

    ## Features

    - **Upload Excel**: Upload an Excel file with device serial numbers and MAC addresses
    - **Get Options**: Retrieve available subscriptions, regions, and tags
    - **Apply Assignments**: Intelligently apply assignments to devices
    - **Sync & Report**: Resync with GreenLake and generate reports

    ## Workflow

    1. Upload an Excel file with device information
    2. Review the parsed devices and their current assignment status
    3. Select subscriptions, regions, and tags to assign
    4. Apply the assignments (only patches what's needed)
    5. Sync with GreenLake and download the report
    """,
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
)

# Include routers
app.include_router(router)
app.include_router(dashboard_router)
app.include_router(clients_router)
app.include_router(reports_router)

# Include agent router if available
if AGENT_AVAILABLE and agent_router:
    app.include_router(agent_router)
    logger.info("Agent chatbot router mounted at /api/agent")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "HPE GreenLake Device Assignment API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/assignment/health",
    }


@app.get("/health")
async def health():
    """Global health check."""
    return {"status": "healthy"}


@app.get("/api/config")
async def get_config():
    """Get frontend configuration.

    Returns feature flags and settings for the frontend.
    """
    return {
        "chatbot_enabled": _chatbot_enabled,
        "version": "1.0.0",
    }


# Entry point for running with uvicorn
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.glp.assignment.app:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=True,
    )
