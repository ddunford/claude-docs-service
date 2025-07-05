"""Main application entry point for the document service."""

import asyncio
import logging
import signal
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import start_http_server

from app.api.grpc_server import create_grpc_server
from app.api.rest_routes import router as rest_router
from app.auth.middleware import JWTAuthenticationMiddleware, RateLimitMiddleware
from app.config import settings
from app.database import init_db, close_db
from app.services.event_publisher import event_publisher
from app.services.redis_client import redis_client
from app.utils.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting document service", extra={"service": "document-service"})
    
    # Setup OpenTelemetry
    setup_tracing()
    
    # Start Prometheus metrics server
    start_http_server(settings.PROMETHEUS_PORT)
    logger.info(f"Prometheus metrics server started on port {settings.PROMETHEUS_PORT}")
    
    # Initialize database
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    
    # Initialize Redis client
    try:
        await redis_client.connect()
        logger.info("Redis client connected")
    except Exception as e:
        logger.error(f"Failed to connect Redis client: {e}")
        # Continue without Redis in development
    
    # Initialize event publisher (temporarily disabled for testing)
    try:
        # await event_publisher.connect()
        logger.info("Event publisher connection skipped for testing")
    except Exception as e:
        logger.error(f"Failed to connect event publisher: {e}")
        # Continue without event publisher in development
    
    # Start gRPC server (temporarily disabled for testing)
    # grpc_server = create_grpc_server()
    # grpc_server.add_insecure_port(f"[::]:{settings.GRPC_PORT}")
    # await grpc_server.start()
    logger.info("gRPC server startup skipped for testing")
    
    # Register shutdown handler
    def shutdown_handler(signum, frame):
        logger.info("Received shutdown signal", extra={"signal": signum})
        # asyncio.create_task(grpc_server.stop(grace=30))
        asyncio.create_task(event_publisher.disconnect())
        asyncio.create_task(redis_client.disconnect())
        asyncio.create_task(close_db())
    
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    
    yield
    
    # Shutdown
    logger.info("Shutting down document service")
    # await grpc_server.stop(grace=30)
    await event_publisher.disconnect()
    await redis_client.disconnect()
    await close_db()


def setup_tracing():
    """Setup OpenTelemetry tracing."""
    resource = Resource(attributes={SERVICE_NAME: "document-service"})
    
    jaeger_exporter = JaegerExporter(
        agent_host_name=settings.JAEGER_HOST,
        agent_port=settings.JAEGER_PORT,
    )
    
    provider = TracerProvider(resource=resource)
    processor = BatchSpanProcessor(jaeger_exporter)
    provider.add_span_processor(processor)
    
    trace.set_tracer_provider(provider)


def create_app() -> FastAPI:
    """Create FastAPI application."""
    app = FastAPI(
        title="Document Service",
        description="Document storage microservice with gRPC and REST APIs",
        version="0.1.0",
        lifespan=lifespan,
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add rate limiting middleware
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=settings.RATE_LIMIT_REQUESTS,
    )
    
    # Add JWT authentication middleware (temporarily disabled for testing)
    # app.add_middleware(
    #     JWTAuthenticationMiddleware,
    #     exempt_paths=[
    #         "/api/v1/health",
    #         "/api/v1/metrics",
    #         "/health",
    #         "/metrics",
    #         "/docs",
    #         "/redoc",
    #         "/openapi.json",
    #         "/static",
    #         "/test",
    #     ],
    # )
    
    # Include REST API routes
    app.include_router(rest_router, prefix="/api/v1")
    
    # Mount static files
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    
    # Add a route to serve the test UI at /test
    @app.get("/test", response_class=HTMLResponse)
    async def test_ui():
        """Serve the test UI."""
        with open("app/static/index.html", "r") as f:
            return HTMLResponse(content=f.read())
    
    # Instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)
    
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.REST_PORT,
        reload=settings.DEBUG,
        log_level="info",
    )