"""
FastAPI Task Runner Application
Main application entry point for the RL Gym Harness task execution system.
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Add parent directory to path to import from the main package
sys.path.append(str(Path(__file__).parent.parent))

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.database import init_db
from app.core.logging_config import setup_logging, build_uvicorn_log_config

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Global task manager instance
task_manager = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global task_manager
    
    # Startup
    logger.info("🚀 Starting FastAPI Task Runner Application")
    
    # Initialize database
    await init_db()
    logger.info("✅ Database initialized")
    
    # Task manager removed - using new database-driven approach
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down FastAPI Task Runner Application")
    
    if task_manager:
        await task_manager.cleanup()

# Create FastAPI application
app = FastAPI(
    title="RL Gym Harness Task Runner",
    description="FastAPI backend for executing and managing AI task automation",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(api_router, prefix="/api/v1")

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "RL Gym Harness Task Runner API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": "2025-01-27T00:00:00Z",
        "services": {
            "database": "connected",
            "task_manager": "initialized" if task_manager else "not_initialized",
        }
    }

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc),
            "type": type(exc).__name__
        }
    )

# Task manager dependency removed - using new database-driven approach


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info",
        log_config=build_uvicorn_log_config(),
    )
