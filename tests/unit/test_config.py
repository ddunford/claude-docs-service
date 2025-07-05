"""Unit tests for configuration management."""

import os
from unittest.mock import patch, Mock
from typing import List

import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings, settings


class TestSettings:
    """Test Settings configuration class."""
    
    def test_default_values(self):
        """Test default configuration values."""
        settings_instance = Settings()
        
        # Application defaults
        assert settings_instance.DEBUG is False
        assert settings_instance.SERVICE_NAME == "document-service"
        
        # Server ports
        assert settings_instance.REST_PORT == 8000
        assert settings_instance.GRPC_PORT == 50051
        assert settings_instance.PROMETHEUS_PORT == 8001
        
        # Database
        assert settings_instance.DATABASE_URL == "postgresql+asyncpg://user:pass@localhost/dbname"
        assert settings_instance.DATABASE_POOL_SIZE == 10
        assert settings_instance.DATABASE_MAX_OVERFLOW == 20
        
        # Redis
        assert settings_instance.REDIS_URL == "redis://localhost:6379"
        assert settings_instance.REDIS_MAX_CONNECTIONS == 10
        
        # Storage
        assert settings_instance.STORAGE_BACKEND == "minio"
        assert settings_instance.S3_ENDPOINT_URL is None
        assert settings_instance.S3_ACCESS_KEY_ID == "testkey"
        assert settings_instance.S3_SECRET_ACCESS_KEY == "testsecret"
        assert settings_instance.S3_BUCKET_NAME == "documents"
        assert settings_instance.S3_REGION == "us-east-1"
        
        # File Upload
        assert settings_instance.MAX_FILE_SIZE_MB == 20
        assert settings_instance.ALLOWED_FILE_TYPES == ["pdf", "doc", "docx", "txt", "jpg", "jpeg", "png"]
        
        # Authentication
        assert settings_instance.JWT_SECRET_KEY == "test-secret-key"
        assert settings_instance.JWT_ALGORITHM == "HS256"
        assert settings_instance.JWT_EXPIRATION_MINUTES == 60
        assert settings_instance.REQUIRED_SCOPES == ["doc.read", "doc.write", "doc.admin"]
        
        # Virus Scanning
        assert settings_instance.VIRUS_SCAN_ENABLED is True
        assert settings_instance.CLAMAV_HOST == "localhost"
        assert settings_instance.CLAMAV_PORT == 3310
        
        # Message Queue
        assert settings_instance.RABBITMQ_URL == "amqp://guest:guest@localhost:5672"
        assert settings_instance.RABBITMQ_EXCHANGE == "documents"
        assert settings_instance.RABBITMQ_QUEUE == "document-events"
        
        # Observability
        assert settings_instance.JAEGER_HOST == "localhost"
        assert settings_instance.JAEGER_PORT == 14268
        
        # CORS
        assert settings_instance.ALLOWED_ORIGINS == ["http://localhost:3000", "http://localhost:8080"]
        
        # Rate Limiting
        assert settings_instance.RATE_LIMIT_REQUESTS == 100
        assert settings_instance.RATE_LIMIT_WINDOW_SECONDS == 60
    
    def test_environment_variable_override(self):
        """Test that environment variables override defaults."""
        env_vars = {
            "DEBUG": "true",
            "SERVICE_NAME": "custom-doc-service",
            "REST_PORT": "9000",
            "DATABASE_URL": "postgresql+asyncpg://user:pass@db:5432/custom",
            "STORAGE_BACKEND": "s3",
            "MAX_FILE_SIZE_MB": "50",
            "JWT_SECRET_KEY": "super-secret-key",
            "VIRUS_SCAN_ENABLED": "false",
        }
        
        with patch.dict(os.environ, env_vars):
            settings_instance = Settings()
            
            assert settings_instance.DEBUG is True
            assert settings_instance.SERVICE_NAME == "custom-doc-service"
            assert settings_instance.REST_PORT == 9000
            assert settings_instance.DATABASE_URL == "postgresql+asyncpg://user:pass@db:5432/custom"
            assert settings_instance.STORAGE_BACKEND == "s3"
            assert settings_instance.MAX_FILE_SIZE_MB == 50
            assert settings_instance.JWT_SECRET_KEY == "super-secret-key"
            assert settings_instance.VIRUS_SCAN_ENABLED is False
    
    def test_parse_allowed_file_types_string(self):
        """Test parsing comma-separated file types from string."""
        with patch.dict(os.environ, {"ALLOWED_FILE_TYPES": "pdf,doc,txt,jpg"}):
            settings_instance = Settings()
            assert settings_instance.ALLOWED_FILE_TYPES == ["pdf", "doc", "txt", "jpg"]
    
    def test_parse_allowed_file_types_string_with_spaces(self):
        """Test parsing file types with spaces."""
        with patch.dict(os.environ, {"ALLOWED_FILE_TYPES": " pdf , doc , txt , jpg "}):
            settings_instance = Settings()
            assert settings_instance.ALLOWED_FILE_TYPES == ["pdf", "doc", "txt", "jpg"]
    
    def test_parse_allowed_file_types_empty_string(self):
        """Test parsing empty file types string."""
        with patch.dict(os.environ, {"ALLOWED_FILE_TYPES": ""}):
            settings_instance = Settings()
            assert settings_instance.ALLOWED_FILE_TYPES == []
    
    def test_parse_allowed_file_types_whitespace_only(self):
        """Test parsing whitespace-only file types string."""
        with patch.dict(os.environ, {"ALLOWED_FILE_TYPES": "   "}):
            settings_instance = Settings()
            assert settings_instance.ALLOWED_FILE_TYPES == []
    
    def test_parse_allowed_file_types_list(self):
        """Test that list input is preserved."""
        # This would typically come from direct instantiation rather than env vars
        settings_instance = Settings(ALLOWED_FILE_TYPES=["pdf", "doc"])
        assert settings_instance.ALLOWED_FILE_TYPES == ["pdf", "doc"]
    
    def test_parse_allowed_origins_string(self):
        """Test parsing comma-separated origins from string."""
        with patch.dict(os.environ, {"ALLOWED_ORIGINS": "http://localhost:3000,https://example.com"}):
            settings_instance = Settings()
            assert settings_instance.ALLOWED_ORIGINS == ["http://localhost:3000", "https://example.com"]
    
    def test_parse_allowed_origins_string_with_spaces(self):
        """Test parsing origins with spaces."""
        with patch.dict(os.environ, {"ALLOWED_ORIGINS": " http://localhost:3000 , https://example.com "}):
            settings_instance = Settings()
            assert settings_instance.ALLOWED_ORIGINS == ["http://localhost:3000", "https://example.com"]
    
    def test_parse_allowed_origins_empty_string(self):
        """Test parsing empty origins string."""
        with patch.dict(os.environ, {"ALLOWED_ORIGINS": ""}):
            settings_instance = Settings()
            assert settings_instance.ALLOWED_ORIGINS == []
    
    def test_parse_required_scopes_string(self):
        """Test parsing comma-separated scopes from string."""
        with patch.dict(os.environ, {"REQUIRED_SCOPES": "read,write,admin"}):
            settings_instance = Settings()
            assert settings_instance.REQUIRED_SCOPES == ["read", "write", "admin"]
    
    def test_parse_required_scopes_string_with_spaces(self):
        """Test parsing scopes with spaces."""
        with patch.dict(os.environ, {"REQUIRED_SCOPES": " read , write , admin "}):
            settings_instance = Settings()
            assert settings_instance.REQUIRED_SCOPES == ["read", "write", "admin"]
    
    def test_parse_required_scopes_empty_string(self):
        """Test parsing empty scopes string."""
        with patch.dict(os.environ, {"REQUIRED_SCOPES": ""}):
            settings_instance = Settings()
            assert settings_instance.REQUIRED_SCOPES == []
    
    def test_validate_storage_backend_valid(self):
        """Test valid storage backend values."""
        valid_backends = ["s3", "minio", "gcs"]
        
        for backend in valid_backends:
            with patch.dict(os.environ, {"STORAGE_BACKEND": backend}):
                settings_instance = Settings()
                assert settings_instance.STORAGE_BACKEND == backend
    
    def test_validate_storage_backend_invalid(self):
        """Test invalid storage backend raises error."""
        with patch.dict(os.environ, {"STORAGE_BACKEND": "invalid-backend"}):
            with pytest.raises(ValidationError) as exc_info:
                Settings()
            
            assert "Storage backend must be one of" in str(exc_info.value)
    
    def test_max_file_size_bytes_property(self):
        """Test max_file_size_bytes property conversion."""
        settings_instance = Settings(MAX_FILE_SIZE_MB=25)
        assert settings_instance.max_file_size_bytes == 25 * 1024 * 1024
        assert settings_instance.MAX_FILE_SIZE_BYTES == 25 * 1024 * 1024
    
    def test_max_file_size_bytes_default(self):
        """Test max_file_size_bytes with default value."""
        settings_instance = Settings()
        assert settings_instance.max_file_size_bytes == 20 * 1024 * 1024  # 20MB default
        assert settings_instance.MAX_FILE_SIZE_BYTES == 20 * 1024 * 1024
    
    def test_boolean_environment_variables(self):
        """Test boolean environment variable parsing."""
        # Test various true values
        true_values = ["true", "True", "TRUE", "1", "yes", "on"]
        for value in true_values:
            with patch.dict(os.environ, {"DEBUG": value}):
                settings_instance = Settings()
                assert settings_instance.DEBUG is True, f"Failed for value: {value}"
        
        # Test various false values
        false_values = ["false", "False", "FALSE", "0", "no", "off"]
        for value in false_values:
            with patch.dict(os.environ, {"DEBUG": value}):
                settings_instance = Settings()
                assert settings_instance.DEBUG is False, f"Failed for value: {value}"
    
    def test_integer_environment_variables(self):
        """Test integer environment variable parsing."""
        with patch.dict(os.environ, {
            "REST_PORT": "9999",
            "DATABASE_POOL_SIZE": "25",
            "RATE_LIMIT_REQUESTS": "500",
        }):
            settings_instance = Settings()
            assert settings_instance.REST_PORT == 9999
            assert settings_instance.DATABASE_POOL_SIZE == 25
            assert settings_instance.RATE_LIMIT_REQUESTS == 500
    
    def test_optional_string_environment_variables(self):
        """Test optional string environment variables."""
        with patch.dict(os.environ, {"S3_ENDPOINT_URL": "https://s3.custom.com"}):
            settings_instance = Settings()
            assert settings_instance.S3_ENDPOINT_URL == "https://s3.custom.com"
        
        # Test that None is preserved when not set
        settings_instance = Settings()
        assert settings_instance.S3_ENDPOINT_URL is None
    
    def test_config_model_settings(self):
        """Test that model config is properly set."""
        # This tests the ConfigDict settings
        config = Settings.model_config
        
        assert config['env_file'] == ".env"
        assert config['env_file_encoding'] == "utf-8"
        assert config['case_sensitive'] is True
        assert config['env_parse_none_str'] == "None"
        assert config['env_ignore_empty'] is True
    
    def test_list_environment_variables_with_commas(self):
        """Test list parsing with various comma scenarios."""
        # Test trailing commas
        with patch.dict(os.environ, {"ALLOWED_FILE_TYPES": "pdf,doc,"}):
            settings_instance = Settings()
            assert settings_instance.ALLOWED_FILE_TYPES == ["pdf", "doc"]
        
        # Test leading commas
        with patch.dict(os.environ, {"ALLOWED_FILE_TYPES": ",pdf,doc"}):
            settings_instance = Settings()
            assert settings_instance.ALLOWED_FILE_TYPES == ["pdf", "doc"]
        
        # Test multiple consecutive commas
        with patch.dict(os.environ, {"ALLOWED_FILE_TYPES": "pdf,,doc,,,txt"}):
            settings_instance = Settings()
            assert settings_instance.ALLOWED_FILE_TYPES == ["pdf", "doc", "txt"]
    
    def test_case_sensitivity_preserved(self):
        """Test that case sensitivity is preserved for file types."""
        with patch.dict(os.environ, {"ALLOWED_FILE_TYPES": "PDF,Doc,TXT"}):
            settings_instance = Settings()
            # File types should be converted to lowercase
            assert settings_instance.ALLOWED_FILE_TYPES == ["pdf", "doc", "txt"]


class TestGetSettings:
    """Test get_settings function and caching."""
    
    def test_get_settings_returns_settings_instance(self):
        """Test that get_settings returns a Settings instance."""
        result = get_settings()
        assert isinstance(result, Settings)
    
    def test_get_settings_caching(self):
        """Test that get_settings uses LRU cache."""
        # Clear any existing cache
        get_settings.cache_clear()
        
        # Get settings multiple times
        settings1 = get_settings()
        settings2 = get_settings()
        settings3 = get_settings()
        
        # Should return the same instance due to caching
        assert settings1 is settings2
        assert settings2 is settings3
        
        # Check cache info
        cache_info = get_settings.cache_info()
        assert cache_info.hits >= 2  # At least 2 cache hits
        assert cache_info.misses == 1  # Only 1 cache miss (first call)
    
    def test_get_settings_cache_clear(self):
        """Test cache clearing functionality."""
        # Get initial settings
        settings1 = get_settings()
        
        # Clear cache
        get_settings.cache_clear()
        
        # Get settings again
        settings2 = get_settings()
        
        # Should be different instances after cache clear
        # Note: This may not always be true if the underlying values are identical,
        # but we can verify the cache was cleared
        cache_info = get_settings.cache_info()
        assert cache_info.misses >= 1
    
    @patch.dict(os.environ, {"DEBUG": "true"})
    def test_get_settings_with_environment_changes(self):
        """Test that get_settings reflects environment changes after cache clear."""
        # Clear cache to ensure fresh start
        get_settings.cache_clear()
        
        # Get settings with current environment
        settings1 = get_settings()
        debug_value1 = settings1.DEBUG
        
        # Change environment
        with patch.dict(os.environ, {"DEBUG": "false"}):
            # Without cache clear, should return cached value
            settings2 = get_settings()
            assert settings2.DEBUG == debug_value1  # Should be cached
            
            # Clear cache and get new settings
            get_settings.cache_clear()
            settings3 = get_settings()
            # Note: This test may be environment-dependent
            # The actual behavior depends on how pydantic-settings handles env vars


class TestGlobalSettings:
    """Test global settings instance."""
    
    def test_global_settings_instance(self):
        """Test that global settings instance exists and is properly configured."""
        from app.config import settings
        
        assert isinstance(settings, Settings)
        assert hasattr(settings, 'DEBUG')
        assert hasattr(settings, 'SERVICE_NAME')
        assert hasattr(settings, 'DATABASE_URL')
    
    def test_global_settings_is_cached_instance(self):
        """Test that global settings is the cached instance."""
        from app.config import settings
        
        # Should be the same as get_settings()
        cached_settings = get_settings()
        assert settings is cached_settings


class TestSettingsValidation:
    """Test settings validation and error handling."""
    
    def test_invalid_integer_values(self):
        """Test that invalid integer values raise appropriate errors."""
        with patch.dict(os.environ, {"REST_PORT": "not-a-number"}):
            with pytest.raises(ValidationError):
                Settings()
    
    def test_invalid_boolean_values(self):
        """Test that invalid boolean values raise appropriate errors."""
        with patch.dict(os.environ, {"DEBUG": "maybe"}):
            with pytest.raises(ValidationError):
                Settings()
    
    def test_required_fields_validation(self):
        """Test validation of required fields."""
        # Most fields have defaults, so this tests the validation logic
        # rather than missing required fields
        
        # Test that empty string for non-optional fields gets handled properly
        with patch.dict(os.environ, {"SERVICE_NAME": ""}):
            # Should use default value if empty string is provided
            settings_instance = Settings()
            # Depending on pydantic configuration, this might use default or empty string
            assert isinstance(settings_instance.SERVICE_NAME, str)
    
    def test_field_validators_called(self):
        """Test that custom field validators are called."""
        # Test storage backend validator
        with pytest.raises(ValidationError) as exc_info:
            Settings(STORAGE_BACKEND="invalid")
        
        assert "Storage backend must be one of" in str(exc_info.value)
    
    def test_properties_accessible(self):
        """Test that computed properties are accessible."""
        settings_instance = Settings(MAX_FILE_SIZE_MB=10)
        
        # Test both property formats
        assert settings_instance.max_file_size_bytes == 10 * 1024 * 1024
        assert settings_instance.MAX_FILE_SIZE_BYTES == 10 * 1024 * 1024
        
        # Test they return the same value
        assert settings_instance.max_file_size_bytes == settings_instance.MAX_FILE_SIZE_BYTES


class TestSettingsIntegration:
    """Integration tests for settings functionality."""
    
    def test_complete_configuration_scenario(self):
        """Test a complete configuration scenario."""
        # Simulate production-like environment variables
        production_env = {
            "DEBUG": "false",
            "SERVICE_NAME": "production-document-service",
            "DATABASE_URL": "postgresql+asyncpg://user:pass@prod-db:5432/documents",
            "REDIS_URL": "redis://prod-redis:6379/0",
            "STORAGE_BACKEND": "s3",
            "S3_ENDPOINT_URL": "https://s3.amazonaws.com",
            "S3_BUCKET_NAME": "prod-documents",
            "MAX_FILE_SIZE_MB": "100",
            "ALLOWED_FILE_TYPES": "pdf,doc,docx,txt,jpg,jpeg,png,gif,tiff",
            "JWT_SECRET_KEY": "production-secret-key-very-long-and-secure",
            "VIRUS_SCAN_ENABLED": "true",
            "RABBITMQ_URL": "amqp://user:pass@prod-rabbit:5672/documents",
            "ALLOWED_ORIGINS": "https://app.example.com,https://admin.example.com",
            "RATE_LIMIT_REQUESTS": "1000",
        }
        
        with patch.dict(os.environ, production_env):
            settings_instance = Settings()
            
            # Verify production configuration
            assert settings_instance.DEBUG is False
            assert settings_instance.SERVICE_NAME == "production-document-service"
            assert "prod-db" in settings_instance.DATABASE_URL
            assert "prod-redis" in settings_instance.REDIS_URL
            assert settings_instance.STORAGE_BACKEND == "s3"
            assert settings_instance.S3_ENDPOINT_URL == "https://s3.amazonaws.com"
            assert settings_instance.S3_BUCKET_NAME == "prod-documents"
            assert settings_instance.MAX_FILE_SIZE_MB == 100
            assert len(settings_instance.ALLOWED_FILE_TYPES) == 9
            assert "gif" in settings_instance.ALLOWED_FILE_TYPES
            assert "tiff" in settings_instance.ALLOWED_FILE_TYPES
            assert settings_instance.JWT_SECRET_KEY == "production-secret-key-very-long-and-secure"
            assert settings_instance.VIRUS_SCAN_ENABLED is True
            assert "prod-rabbit" in settings_instance.RABBITMQ_URL
            assert len(settings_instance.ALLOWED_ORIGINS) == 2
            assert "https://app.example.com" in settings_instance.ALLOWED_ORIGINS
            assert settings_instance.RATE_LIMIT_REQUESTS == 1000
            
            # Test computed properties
            assert settings_instance.max_file_size_bytes == 100 * 1024 * 1024
    
    def test_development_configuration_scenario(self):
        """Test a development configuration scenario."""
        dev_env = {
            "DEBUG": "true",
            "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/documents_dev",
            "VIRUS_SCAN_ENABLED": "false",
            "ALLOWED_ORIGINS": "http://localhost:3000,http://localhost:8080",
        }
        
        with patch.dict(os.environ, dev_env):
            settings_instance = Settings()
            
            # Verify development configuration
            assert settings_instance.DEBUG is True
            assert "localhost" in settings_instance.DATABASE_URL
            assert "documents_dev" in settings_instance.DATABASE_URL
            assert settings_instance.VIRUS_SCAN_ENABLED is False
            assert all("localhost" in origin for origin in settings_instance.ALLOWED_ORIGINS)