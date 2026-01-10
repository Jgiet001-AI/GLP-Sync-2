"""FastAPI application for device assignment.

This is the main entry point for the assignment API server.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.dashboard_router import router as dashboard_router
from .api.dependencies import close_db_pool, init_db_pool
from .api.router import router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting Device Assignment API...")

    try:
        await init_db_pool()
        logger.info("Database pool initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database pool: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down Device Assignment API...")
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
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router)
app.include_router(dashboard_router)


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


# Entry point for running with uvicorn
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.glp.assignment.app:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=True,
    )
