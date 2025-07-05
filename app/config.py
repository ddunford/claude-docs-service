"""Configuration management for the document service."""

import os
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator, ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""
    
    # Application
    DEBUG: bool = Field(default=False)
    SERVICE_NAME: str = Field(default="document-service")
    
    # Server ports
    REST_PORT: int = Field(default=8000)
    GRPC_PORT: int = Field(default=50051)
    PROMETHEUS_PORT: int = Field(default=8001)
    
    # Database
    DATABASE_URL: str = Field(default="postgresql+asyncpg://user:pass@localhost/dbname")
    DATABASE_POOL_SIZE: int = Field(default=10)
    DATABASE_MAX_OVERFLOW: int = Field(default=20)
    
    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379")
    REDIS_MAX_CONNECTIONS: int = Field(default=10)
    
    # Storage
    STORAGE_BACKEND: str = Field(default="minio")
    
    # S3/MinIO Configuration
    S3_ENDPOINT_URL: Optional[str] = Field(default=None)
    S3_ACCESS_KEY_ID: str = Field(default="testkey")
    S3_SECRET_ACCESS_KEY: str = Field(default="testsecret")
    S3_BUCKET_NAME: str = Field(default="documents")
    S3_REGION: str = Field(default="us-east-1")
    
    # File Upload
    MAX_FILE_SIZE_MB: int = Field(default=20)
    ALLOWED_FILE_TYPES: List[str] = Field(
        default=["pdf", "doc", "docx", "txt", "jpg", "jpeg", "png"]
    )
    
    # Authentication
    JWT_SECRET_KEY: str = Field(default="test-secret-key")
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_EXPIRATION_MINUTES: int = Field(default=60)
    
    # OAuth2 Scopes
    REQUIRED_SCOPES: List[str] = Field(
        default=["doc.read", "doc.write", "doc.admin"]
    )
    
    # Virus Scanning
    VIRUS_SCAN_ENABLED: bool = Field(default=True)
    CLAMAV_HOST: str = Field(default="localhost")
    CLAMAV_PORT: int = Field(default=3310)
    
    # Message Queue
    RABBITMQ_URL: str = Field(default="amqp://guest:guest@localhost:5672")
    RABBITMQ_EXCHANGE: str = Field(default="documents")
    RABBITMQ_QUEUE: str = Field(default="document-events")
    
    # Observability
    JAEGER_HOST: str = Field(default="localhost")
    JAEGER_PORT: int = Field(default=14268)
    
    # CORS
    ALLOWED_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"]
    )
    
    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = Field(default=100)
    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60)
    
    @field_validator("ALLOWED_FILE_TYPES", mode="before")
    def parse_allowed_file_types(cls, v):
        """Parse comma-separated string into list."""
        if isinstance(v, str):
            if not v.strip():
                return []
            return [ext.strip().lower() for ext in v.split(",") if ext.strip()]
        return v
    
    @field_validator("ALLOWED_ORIGINS", mode="before")
    def parse_allowed_origins(cls, v):
        """Parse comma-separated string into list."""
        if isinstance(v, str):
            if not v.strip():
                return []
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v
    
    @field_validator("REQUIRED_SCOPES", mode="before")
    def parse_required_scopes(cls, v):
        """Parse comma-separated string into list."""
        if isinstance(v, str):
            if not v.strip():
                return []
            return [scope.strip() for scope in v.split(",") if scope.strip()]
        return v
    
    @field_validator("STORAGE_BACKEND")
    def validate_storage_backend(cls, v):
        """Validate storage backend choice."""
        allowed_backends = ["s3", "minio", "gcs"]
        if v not in allowed_backends:
            raise ValueError(f"Storage backend must be one of: {allowed_backends}")
        return v
    
    @property
    def max_file_size_bytes(self) -> int:
        """Convert MB to bytes."""
        return self.MAX_FILE_SIZE_MB * 1024 * 1024
    
    @property
    def MAX_FILE_SIZE_BYTES(self) -> int:
        """Convert MB to bytes for backwards compatibility."""
        return self.MAX_FILE_SIZE_MB * 1024 * 1024
    
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_parse_none_str="None",
        env_ignore_empty=True,
    )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()