"""Unit tests for logging utilities."""

import logging
import sys
import uuid
from unittest.mock import Mock, patch, call
from typing import Any, Dict

import pytest
import structlog

from app.utils.logging import setup_logging, get_logger, log_document_event, log_error


class TestLoggingSetup:
    """Test logging setup functionality."""
    
    @patch('app.utils.logging.settings')
    @patch('app.utils.logging.structlog.configure')
    @patch('app.utils.logging.logging.basicConfig')
    @patch('app.utils.logging.logging.getLogger')
    def test_setup_logging_debug_mode(self, mock_get_logger, mock_basic_config, mock_structlog_config, mock_settings):
        """Test logging setup in debug mode."""
        mock_settings.DEBUG = True
        
        # Mock logger instances
        mock_uvicorn_logger = Mock()
        mock_grpc_logger = Mock()
        mock_boto3_logger = Mock()
        mock_botocore_logger = Mock()
        mock_urllib3_logger = Mock()
        
        def mock_logger_factory(name):
            if name == "uvicorn":
                return mock_uvicorn_logger
            elif name == "grpc":
                return mock_grpc_logger
            elif name == "boto3":
                return mock_boto3_logger
            elif name == "botocore":
                return mock_botocore_logger
            elif name == "urllib3":
                return mock_urllib3_logger
            return Mock()
        
        mock_get_logger.side_effect = mock_logger_factory
        
        setup_logging()
        
        # Verify structlog configuration
        mock_structlog_config.assert_called_once()
        config_kwargs = mock_structlog_config.call_args[1]
        
        assert len(config_kwargs['processors']) == 6
        assert config_kwargs['context_class'] == dict
        assert config_kwargs['wrapper_class'] == structlog.stdlib.BoundLogger
        assert config_kwargs['cache_logger_on_first_use'] is True
        
        # Verify basic logging configuration
        mock_basic_config.assert_called_once_with(
            format="%(message)s",
            stream=sys.stdout,
            level=logging.DEBUG,
        )
        
        # Verify third-party logger levels
        mock_uvicorn_logger.setLevel.assert_called_once_with(logging.INFO)
        mock_grpc_logger.setLevel.assert_called_once_with(logging.WARNING)
        mock_boto3_logger.setLevel.assert_called_once_with(logging.WARNING)
        mock_botocore_logger.setLevel.assert_called_once_with(logging.WARNING)
        mock_urllib3_logger.setLevel.assert_called_once_with(logging.WARNING)
    
    @patch('app.utils.logging.settings')
    @patch('app.utils.logging.structlog.configure')
    @patch('app.utils.logging.logging.basicConfig')
    @patch('app.utils.logging.logging.getLogger')
    def test_setup_logging_production_mode(self, mock_get_logger, mock_basic_config, mock_structlog_config, mock_settings):
        """Test logging setup in production mode."""
        mock_settings.DEBUG = False
        mock_get_logger.return_value = Mock()
        
        setup_logging()
        
        # Verify production log level
        mock_basic_config.assert_called_once_with(
            format="%(message)s",
            stream=sys.stdout,
            level=logging.INFO,
        )
    
    def test_setup_logging_processors(self):
        """Test that setup_logging configures the correct processors."""
        with patch('app.utils.logging.settings') as mock_settings:
            mock_settings.DEBUG = False
            
            with patch('app.utils.logging.structlog.configure') as mock_config:
                with patch('app.utils.logging.logging.basicConfig'):
                    with patch('app.utils.logging.logging.getLogger'):
                        setup_logging()
                
                # Get the processors list
                processors = mock_config.call_args[1]['processors']
                
                # Verify specific processors are included
                processor_names = [proc.__name__ if hasattr(proc, '__name__') else str(proc) for proc in processors]
                
                # Check for key processors (some may be instances rather than function references)
                assert len(processors) == 6
                # The processors should include JSON renderer as the last one
                assert hasattr(processors[-1], '__class__')


class TestGetLogger:
    """Test get_logger functionality."""
    
    @patch('app.utils.logging.structlog.get_logger')
    def test_get_logger(self, mock_structlog_get_logger):
        """Test getting a logger instance."""
        mock_logger = Mock()
        mock_structlog_get_logger.return_value = mock_logger
        
        logger_name = "test_service"
        result = get_logger(logger_name)
        
        mock_structlog_get_logger.assert_called_once_with(logger_name)
        assert result == mock_logger
    
    def test_get_logger_returns_bound_logger(self):
        """Test that get_logger returns a proper bound logger."""
        logger_name = "test_logger"
        
        # Mock structlog to return a bound logger
        with patch('app.utils.logging.structlog.get_logger') as mock_get_logger:
            mock_bound_logger = Mock(spec=structlog.stdlib.BoundLogger)
            mock_get_logger.return_value = mock_bound_logger
            
            result = get_logger(logger_name)
            
            assert result == mock_bound_logger
            mock_get_logger.assert_called_once_with(logger_name)


class TestLogDocumentEvent:
    """Test log_document_event functionality."""
    
    def test_log_document_event_basic(self):
        """Test basic document event logging."""
        mock_logger = Mock()
        
        event_name = "document_uploaded"
        document_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        
        log_document_event(mock_logger, event_name, document_id, tenant_id, user_id)
        
        mock_logger.info.assert_called_once_with(
            "Document event",
            event_type=event_name,
            document_id=document_id,
            tenant_id=tenant_id,
            user_id=user_id,
            service="document-service",
        )
    
    def test_log_document_event_with_trace_id(self):
        """Test document event logging with trace ID."""
        mock_logger = Mock()
        
        event_name = "document_deleted"
        document_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        trace_id = str(uuid.uuid4())
        
        log_document_event(
            mock_logger, 
            event_name, 
            document_id, 
            tenant_id, 
            user_id, 
            trace_id=trace_id
        )
        
        mock_logger.info.assert_called_once_with(
            "Document event",
            event_type=event_name,
            document_id=document_id,
            tenant_id=tenant_id,
            user_id=user_id,
            service="document-service",
            trace_id=trace_id,
        )
    
    def test_log_document_event_with_kwargs(self):
        """Test document event logging with additional kwargs."""
        mock_logger = Mock()
        
        event_name = "document_scanned"
        document_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        
        additional_data = {
            "scan_id": str(uuid.uuid4()),
            "result": "clean",
            "duration_ms": 1500,
            "filename": "test.pdf",
        }
        
        log_document_event(
            mock_logger, 
            event_name, 
            document_id, 
            tenant_id, 
            user_id,
            **additional_data
        )
        
        expected_call_kwargs = {
            "event_type": event_name,
            "document_id": document_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "service": "document-service",
            **additional_data,
        }
        
        mock_logger.info.assert_called_once_with("Document event", **expected_call_kwargs)
    
    def test_log_document_event_with_trace_id_and_kwargs(self):
        """Test document event logging with both trace ID and additional kwargs."""
        mock_logger = Mock()
        
        event_name = "document_updated"
        document_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        trace_id = str(uuid.uuid4())
        
        additional_data = {
            "old_version": 1,
            "new_version": 2,
            "changes": ["title", "description"],
        }
        
        log_document_event(
            mock_logger, 
            event_name, 
            document_id, 
            tenant_id, 
            user_id,
            trace_id=trace_id,
            **additional_data
        )
        
        expected_call_kwargs = {
            "event_type": event_name,
            "document_id": document_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "service": "document-service",
            "trace_id": trace_id,
            **additional_data,
        }
        
        mock_logger.info.assert_called_once_with("Document event", **expected_call_kwargs)
    
    def test_log_document_event_none_trace_id(self):
        """Test document event logging with None trace ID."""
        mock_logger = Mock()
        
        event_name = "document_accessed"
        document_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        
        log_document_event(
            mock_logger, 
            event_name, 
            document_id, 
            tenant_id, 
            user_id,
            trace_id=None
        )
        
        # trace_id should not be included when None
        mock_logger.info.assert_called_once_with(
            "Document event",
            event_type=event_name,
            document_id=document_id,
            tenant_id=tenant_id,
            user_id=user_id,
            service="document-service",
        )


class TestLogError:
    """Test log_error functionality."""
    
    def test_log_error_basic(self):
        """Test basic error logging."""
        mock_logger = Mock()
        
        error = ValueError("Test error message")
        
        log_error(mock_logger, error)
        
        mock_logger.error.assert_called_once_with(
            "Error occurred",
            error_type="ValueError",
            error_message="Test error message",
            service="document-service",
            exc_info=True,
        )
    
    def test_log_error_with_context(self):
        """Test error logging with context."""
        mock_logger = Mock()
        
        error = ConnectionError("Database connection failed")
        context = {
            "database_url": "postgresql://localhost:5432/testdb",
            "operation": "fetch_document",
            "retry_count": 3,
        }
        
        log_error(mock_logger, error, context=context)
        
        expected_kwargs = {
            "error_type": "ConnectionError",
            "error_message": "Database connection failed",
            "service": "document-service",
            "database_url": "postgresql://localhost:5432/testdb",
            "operation": "fetch_document",
            "retry_count": 3,
            "exc_info": True,
        }
        
        mock_logger.error.assert_called_once_with("Error occurred", **expected_kwargs)
    
    def test_log_error_with_trace_id(self):
        """Test error logging with trace ID."""
        mock_logger = Mock()
        
        error = RuntimeError("Unexpected runtime error")
        trace_id = str(uuid.uuid4())
        
        log_error(mock_logger, error, trace_id=trace_id)
        
        mock_logger.error.assert_called_once_with(
            "Error occurred",
            error_type="RuntimeError",
            error_message="Unexpected runtime error",
            service="document-service",
            trace_id=trace_id,
            exc_info=True,
        )
    
    def test_log_error_with_context_and_trace_id(self):
        """Test error logging with both context and trace ID."""
        mock_logger = Mock()
        
        error = FileNotFoundError("Document file not found")
        context = {
            "document_id": str(uuid.uuid4()),
            "storage_backend": "s3",
            "bucket": "documents",
            "key": "path/to/file.pdf",
        }
        trace_id = str(uuid.uuid4())
        
        log_error(mock_logger, error, context=context, trace_id=trace_id)
        
        expected_kwargs = {
            "error_type": "FileNotFoundError",
            "error_message": "Document file not found",
            "service": "document-service",
            "trace_id": trace_id,
            "exc_info": True,
            **context,
        }
        
        mock_logger.error.assert_called_once_with("Error occurred", **expected_kwargs)
    
    def test_log_error_none_context(self):
        """Test error logging with None context."""
        mock_logger = Mock()
        
        error = KeyError("Missing required key")
        
        log_error(mock_logger, error, context=None)
        
        mock_logger.error.assert_called_once_with(
            "Error occurred",
            error_type="KeyError",
            error_message="Missing required key",
            service="document-service",
            exc_info=True,
        )
    
    def test_log_error_none_trace_id(self):
        """Test error logging with None trace ID."""
        mock_logger = Mock()
        
        error = TimeoutError("Request timeout")
        
        log_error(mock_logger, error, trace_id=None)
        
        # trace_id should not be included when None
        mock_logger.error.assert_called_once_with(
            "Error occurred",
            error_type="TimeoutError",
            error_message="Request timeout",
            service="document-service",
            exc_info=True,
        )
    
    def test_log_error_custom_exception(self):
        """Test error logging with custom exception class."""
        mock_logger = Mock()
        
        class CustomServiceError(Exception):
            """Custom service error for testing."""
            pass
        
        error = CustomServiceError("Custom error occurred")
        
        log_error(mock_logger, error)
        
        mock_logger.error.assert_called_once_with(
            "Error occurred",
            error_type="CustomServiceError",
            error_message="Custom error occurred",
            service="document-service",
            exc_info=True,
        )
    
    def test_log_error_empty_context(self):
        """Test error logging with empty context dictionary."""
        mock_logger = Mock()
        
        error = IndexError("List index out of range")
        context = {}
        
        log_error(mock_logger, error, context=context)
        
        mock_logger.error.assert_called_once_with(
            "Error occurred",
            error_type="IndexError",
            error_message="List index out of range",
            service="document-service",
            exc_info=True,
        )
    
    def test_log_error_context_overwrites_defaults(self):
        """Test that context can overwrite default fields."""
        mock_logger = Mock()
        
        error = Exception("Test error")
        context = {
            "service": "custom-service",  # Overwrite default service name
            "error_type": "CustomType",   # Overwrite default error type
        }
        
        log_error(mock_logger, error, context=context)
        
        # Context should overwrite the defaults
        expected_kwargs = {
            "error_message": "Test error",
            "service": "custom-service",      # From context
            "error_type": "CustomType",       # From context
            "exc_info": True,
        }
        
        mock_logger.error.assert_called_once_with("Error occurred", **expected_kwargs)


class TestLoggingIntegration:
    """Integration tests for logging functionality."""
    
    def test_logging_workflow(self):
        """Test complete logging workflow."""
        # Setup logging
        with patch('app.utils.logging.settings') as mock_settings:
            mock_settings.DEBUG = True
            
            with patch('app.utils.logging.structlog.configure'):
                with patch('app.utils.logging.logging.basicConfig'):
                    with patch('app.utils.logging.logging.getLogger'):
                        setup_logging()
        
        # Get logger
        with patch('app.utils.logging.structlog.get_logger') as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger
            
            logger = get_logger("test_service")
            
            # Log document event
            document_id = str(uuid.uuid4())
            tenant_id = str(uuid.uuid4())
            user_id = str(uuid.uuid4())
            
            log_document_event(logger, "test_event", document_id, tenant_id, user_id)
            
            # Log error
            error = Exception("Test error")
            log_error(logger, error)
            
            # Verify calls
            assert mock_logger.info.call_count == 1
            assert mock_logger.error.call_count == 1
    
    def test_logger_reuse(self):
        """Test that loggers can be reused properly."""
        with patch('app.utils.logging.structlog.get_logger') as mock_get_logger:
            mock_logger1 = Mock()
            mock_logger2 = Mock()
            
            # Different loggers for different services
            mock_get_logger.side_effect = [mock_logger1, mock_logger2]
            
            logger1 = get_logger("service1")
            logger2 = get_logger("service2")
            
            assert logger1 == mock_logger1
            assert logger2 == mock_logger2
            assert logger1 != logger2
            
            # Verify both were called with correct names
            assert mock_get_logger.call_args_list == [
                call("service1"),
                call("service2"),
            ]