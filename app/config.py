"""Configuration management for the document service."""

import os
from functools import lru_cache
from typing import List, Optional

from pydantic import BaseSettings, Field, validator


class Settings(BaseSettings):
    """Application settings."""
    
    # Application
    DEBUG: bool = Field(default=False, env="DEBUG")
    SERVICE_NAME: str = Field(default="document-service", env="SERVICE_NAME")
    
    # Server ports
    REST_PORT: int = Field(default=8000, env="REST_PORT")
    GRPC_PORT: int = Field(default=50051, env="GRPC_PORT")
    PROMETHEUS_PORT: int = Field(default=8001, env="PROMETHEUS_PORT")
    
    # Database
    DATABASE_URL: str = Field(env="DATABASE_URL")
    DATABASE_POOL_SIZE: int = Field(default=10, env="DATABASE_POOL_SIZE")
    DATABASE_MAX_OVERFLOW: int = Field(default=20, env="DATABASE_MAX_OVERFLOW")
    
    # Redis
    REDIS_URL: str = Field(env="REDIS_URL")
    REDIS_MAX_CONNECTIONS: int = Field(default=10, env="REDIS_MAX_CONNECTIONS")
    
    # Storage
    STORAGE_BACKEND: str = Field(default="minio", env="STORAGE_BACKEND")
    
    # S3/MinIO Configuration
    S3_ENDPOINT_URL: Optional[str] = Field(default=None, env="S3_ENDPOINT_URL")
    S3_ACCESS_KEY_ID: str = Field(env="S3_ACCESS_KEY_ID")
    S3_SECRET_ACCESS_KEY: str = Field(env="S3_SECRET_ACCESS_KEY")
    S3_BUCKET_NAME: str = Field(default="documents", env="S3_BUCKET_NAME")
    S3_REGION: str = Field(default="us-east-1", env="S3_REGION")
    
    # File Upload
    MAX_FILE_SIZE_MB: int = Field(default=20, env="MAX_FILE_SIZE_MB")
    ALLOWED_FILE_TYPES: List[str] = Field(
        default=["pdf", "doc", "docx", "txt", "jpg", "jpeg", "png"],
        env="ALLOWED_FILE_TYPES"
    )
    
    # Authentication
    JWT_SECRET_KEY: str = Field(env="JWT_SECRET_KEY")
    JWT_ALGORITHM: str = Field(default="HS256", env="JWT_ALGORITHM")
    JWT_EXPIRATION_MINUTES: int = Field(default=60, env="JWT_EXPIRATION_MINUTES")
    
    # OAuth2 Scopes
    REQUIRED_SCOPES: List[str] = Field(
        default=["doc.read", "doc.write", "doc.admin"],
        env="REQUIRED_SCOPES"
    )
    
    # Virus Scanning
    VIRUS_SCAN_ENABLED: bool = Field(default=True, env="VIRUS_SCAN_ENABLED")
    CLAMAV_HOST: str = Field(default="localhost", env="CLAMAV_HOST")
    CLAMAV_PORT: int = Field(default=3310, env="CLAMAV_PORT")
    
    # Message Queue
    RABBITMQ_URL: str = Field(env="RABBITMQ_URL")
    RABBITMQ_EXCHANGE: str = Field(default="documents", env="RABBITMQ_EXCHANGE")
    RABBITMQ_QUEUE: str = Field(default="document-events", env="RABBITMQ_QUEUE")
    
    # Observability
    JAEGER_HOST: str = Field(default="localhost", env="JAEGER_HOST")
    JAEGER_PORT: int = Field(default=14268, env="JAEGER_PORT")
    
    # CORS
    ALLOWED_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        env="ALLOWED_ORIGINS"
    )
    
    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = Field(default=100, env="RATE_LIMIT_REQUESTS")
    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, env="RATE_LIMIT_WINDOW_SECONDS")
    
    @validator("ALLOWED_FILE_TYPES", pre=True)
    def parse_allowed_file_types(cls, v):
        """Parse comma-separated string into list."""
        if isinstance(v, str):
            return [ext.strip().lower() for ext in v.split(",")]
        return v
    
    @validator("ALLOWED_ORIGINS", pre=True)
    def parse_allowed_origins(cls, v):
        """Parse comma-separated string into list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    @validator("REQUIRED_SCOPES", pre=True)
    def parse_required_scopes(cls, v):
        """Parse comma-separated string into list."""
        if isinstance(v, str):
            return [scope.strip() for scope in v.split(",")]
        return v
    
    @validator("STORAGE_BACKEND")
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
    
    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()