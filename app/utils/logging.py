"""Structured logging configuration for the document service."""

import logging
import sys
from typing import Any, Dict

import structlog
from structlog.stdlib import LoggerFactory

from app.config import settings


def setup_logging():
    """Setup structured logging with structlog."""
    # Configure structlog
    structlog.configure(
        processors=[
            # Add log level and timestamp
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            # Add context processors
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            # JSON formatter for structured logging
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.DEBUG if settings.DEBUG else logging.INFO,
    )
    
    # Set log levels for third-party libraries
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("grpc").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


def log_document_event(
    logger: structlog.stdlib.BoundLogger,
    event: str,
    document_id: str,
    tenant_id: str,
    user_id: str,
    trace_id: str = None,
    **kwargs: Any,
) -> None:
    """Log a document-related event with standard fields."""
    log_data: Dict[str, Any] = {
        "event": event,
        "document_id": document_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "service": "document-service",
        **kwargs,
    }
    
    if trace_id:
        log_data["trace_id"] = trace_id
    
    logger.info(event, **log_data)


def log_error(
    logger: structlog.stdlib.BoundLogger,
    error: Exception,
    context: Dict[str, Any] = None,
    trace_id: str = None,
) -> None:
    """Log an error with context and trace information."""
    log_data = {
        "error_type": type(error).__name__,
        "error_message": str(error),
        "service": "document-service",
    }
    
    if context:
        log_data.update(context)
    
    if trace_id:
        log_data["trace_id"] = trace_id
    
    logger.error("Error occurred", **log_data, exc_info=True)