"""Base storage backend interface."""

from abc import ABC, abstractmethod
from typing import Optional, AsyncIterator, Dict, Any, List
from datetime import datetime
import io

from app.models.document import StorageLocation


class StorageBackend(ABC):
    """Abstract base class for storage backends."""
    
    @abstractmethod
    async def upload_file(
        self,
        file_data: bytes,
        key: str,
        content_type: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> StorageLocation:
        """Upload a file to storage."""
        pass
    
    @abstractmethod
    async def download_file(self, location: StorageLocation) -> bytes:
        """Download a file from storage."""
        pass
    
    @abstractmethod
    async def download_file_stream(self, location: StorageLocation) -> AsyncIterator[bytes]:
        """Download a file from storage as a stream."""
        pass
    
    @abstractmethod
    async def delete_file(self, location: StorageLocation) -> bool:
        """Delete a file from storage."""
        pass
    
    @abstractmethod
    async def file_exists(self, location: StorageLocation) -> bool:
        """Check if a file exists in storage."""
        pass
    
    @abstractmethod
    async def get_file_metadata(self, location: StorageLocation) -> Dict[str, Any]:
        """Get file metadata from storage."""
        pass
    
    @abstractmethod
    async def generate_presigned_url(
        self,
        location: StorageLocation,
        expiration_seconds: int = 3600,
        operation: str = "get",
    ) -> str:
        """Generate a presigned URL for file access."""
        pass
    
    @abstractmethod
    async def list_files(
        self,
        prefix: str = "",
        limit: int = 1000,
        continuation_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List files in storage."""
        pass
    
    @abstractmethod
    async def copy_file(
        self,
        source_location: StorageLocation,
        destination_location: StorageLocation,
    ) -> bool:
        """Copy a file within storage."""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the storage backend is healthy."""
        pass


class StorageError(Exception):
    """Base exception for storage operations."""
    pass


class FileNotFoundError(StorageError):
    """Exception raised when a file is not found."""
    pass


class StorageConnectionError(StorageError):
    """Exception raised when storage connection fails."""
    pass


class StoragePermissionError(StorageError):
    """Exception raised when storage permission is denied."""
    pass


class StorageQuotaError(StorageError):
    """Exception raised when storage quota is exceeded."""
    pass