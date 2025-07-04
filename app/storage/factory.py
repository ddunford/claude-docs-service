"""Storage backend factory."""

from typing import Dict, Type, List
from functools import lru_cache

from app.config import settings
from app.storage.base import StorageBackend, StorageError
from app.storage.s3_backend import S3StorageBackend
from app.utils.logging import get_logger

logger = get_logger(__name__)


class StorageFactory:
    """Factory for creating storage backend instances."""
    
    _backends: Dict[str, Type[StorageBackend]] = {
        "s3": S3StorageBackend,
        "minio": S3StorageBackend,  # MinIO uses S3 API
        # "gcs": GCSStorageBackend,  # TODO: Implement GCS backend
        # "azure": AzureStorageBackend,  # TODO: Implement Azure backend
    }
    
    @classmethod
    def create_backend(self, backend_type: str = None) -> StorageBackend:
        """Create a storage backend instance."""
        if backend_type is None:
            backend_type = settings.STORAGE_BACKEND
        
        backend_type = backend_type.lower()
        
        if backend_type not in self._backends:
            available_backends = ", ".join(self._backends.keys())
            raise StorageError(
                f"Unsupported storage backend: {backend_type}. "
                f"Available backends: {available_backends}"
            )
        
        backend_class = self._backends[backend_type]
        backend_instance = backend_class()
        
        logger.info(f"Created storage backend: {backend_type}")
        return backend_instance
    
    @classmethod
    def register_backend(cls, name: str, backend_class: Type[StorageBackend]) -> None:
        """Register a new storage backend."""
        if not issubclass(backend_class, StorageBackend):
            raise ValueError("Backend class must inherit from StorageBackend")
        
        cls._backends[name.lower()] = backend_class
        logger.info(f"Registered storage backend: {name}")
    
    @classmethod
    def get_available_backends(cls) -> List[str]:
        """Get list of available storage backends."""
        return list(cls._backends.keys())


@lru_cache(maxsize=1)
def get_storage_backend() -> StorageBackend:
    """Get the configured storage backend instance (cached)."""
    return StorageFactory.create_backend()


# Storage service instance
storage_service = get_storage_backend()