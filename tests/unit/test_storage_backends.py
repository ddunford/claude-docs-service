"""Tests for storage backends."""

import pytest
import uuid
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime
from botocore.exceptions import ClientError

from app.storage.s3_backend import S3StorageBackend
from app.storage.factory import StorageFactory
from app.storage.base import (
    StorageError,
    FileNotFoundError,
    StorageConnectionError,
    StoragePermissionError,
    StorageQuotaError,
)
from app.models.document import StorageLocation, StorageBackend


class TestS3StorageBackend:
    """Test S3 storage backend."""

    @pytest.fixture
    def storage_backend(self):
        """Create S3 storage backend instance."""
        with patch('app.storage.s3_backend.settings') as mock_settings:
            mock_settings.S3_BUCKET_NAME = "test-bucket"
            mock_settings.S3_REGION = "us-east-1"
            mock_settings.S3_ENDPOINT_URL = None
            mock_settings.S3_ACCESS_KEY_ID = "test-key"
            mock_settings.S3_SECRET_ACCESS_KEY = "test-secret"
            return S3StorageBackend()

    @pytest.fixture
    def sample_storage_location(self):
        """Create sample storage location."""
        return StorageLocation(
            backend=StorageBackend.S3,
            bucket="test-bucket",
            key="test/file.pdf",
            region="us-east-1",
            endpoint_url=None,
        )

    @pytest.fixture
    def sample_file_data(self):
        """Create sample file data."""
        return b"Sample file content for testing"

    @pytest.mark.asyncio
    async def test_upload_file_success(self, storage_backend, sample_file_data):
        """Test successful file upload."""
        mock_client = AsyncMock()
        mock_session = AsyncMock()
        mock_session.client.return_value.__aenter__.return_value = mock_client
        
        with patch.object(storage_backend, 'session', mock_session):
            result = await storage_backend.upload_file(
                file_data=sample_file_data,
                key="test/file.pdf",
                content_type="application/pdf",
                metadata={"test": "value"},
            )
            
            # Verify upload was called with correct parameters
            mock_client.put_object.assert_called_once_with(
                Bucket="test-bucket",
                Key="test/file.pdf",
                Body=sample_file_data,
                ContentType="application/pdf",
                Metadata={"test": "value"},
            )
            
            # Verify return value
            assert result.backend == StorageBackend.S3
            assert result.bucket == "test-bucket"
            assert result.key == "test/file.pdf"
            assert result.region == "us-east-1"
            assert result.endpoint_url is None

    @pytest.mark.asyncio
    async def test_upload_file_minio_backend(self, sample_file_data):
        """Test file upload with MinIO backend."""
        with patch('app.storage.s3_backend.settings') as mock_settings:
            mock_settings.S3_BUCKET_NAME = "test-bucket"
            mock_settings.S3_REGION = "us-east-1"
            mock_settings.S3_ENDPOINT_URL = "http://localhost:9000"
            mock_settings.S3_ACCESS_KEY_ID = "test-key"
            mock_settings.S3_SECRET_ACCESS_KEY = "test-secret"
            
            storage_backend = S3StorageBackend()
            
            mock_client = AsyncMock()
            mock_session = AsyncMock()
            mock_session.client.return_value.__aenter__.return_value = mock_client
            
            with patch.object(storage_backend, 'session', mock_session):
                result = await storage_backend.upload_file(
                    file_data=sample_file_data,
                    key="test/file.pdf",
                    content_type="application/pdf",
                )
                
                # Verify return value indicates MinIO
                assert result.backend == StorageBackend.MINIO
                assert result.endpoint_url == "http://localhost:9000"

    @pytest.mark.asyncio
    async def test_upload_file_client_error(self, storage_backend, sample_file_data):
        """Test file upload with client error."""
        mock_client = AsyncMock()
        mock_client.put_object.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
            "put_object"
        )
        
        mock_session = AsyncMock()
        mock_session.client.return_value.__aenter__.return_value = mock_client
        
        with patch.object(storage_backend, 'session', mock_session):
            with pytest.raises(StoragePermissionError) as exc_info:
                await storage_backend.upload_file(
                    file_data=sample_file_data,
                    key="test/file.pdf",
                    content_type="application/pdf",
                )
            
            assert "Access denied" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_download_file_success(self, storage_backend, sample_storage_location, sample_file_data):
        """Test successful file download."""
        mock_response = {
            "Body": AsyncMock()
        }
        mock_response["Body"].read.return_value = sample_file_data
        
        mock_client = AsyncMock()
        mock_client.get_object.return_value = mock_response
        
        mock_session = AsyncMock()
        mock_session.client.return_value.__aenter__.return_value = mock_client
        
        with patch.object(storage_backend, 'session', mock_session):
            result = await storage_backend.download_file(sample_storage_location)
            
            # Verify download was called with correct parameters
            mock_client.get_object.assert_called_once_with(
                Bucket=sample_storage_location.bucket,
                Key=sample_storage_location.key,
            )
            
            # Verify return value
            assert result == sample_file_data

    @pytest.mark.asyncio
    async def test_download_file_not_found(self, storage_backend, sample_storage_location):
        """Test file download when file not found."""
        mock_client = AsyncMock()
        mock_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Key not found"}},
            "get_object"
        )
        
        mock_session = AsyncMock()
        mock_session.client.return_value.__aenter__.return_value = mock_client
        
        with patch.object(storage_backend, 'session', mock_session):
            with pytest.raises(FileNotFoundError) as exc_info:
                await storage_backend.download_file(sample_storage_location)
            
            assert "File not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_download_file_stream_success(self, storage_backend, sample_storage_location):
        """Test successful file download as stream."""
        mock_body = AsyncMock()
        mock_body.iter_chunks.return_value = [b"chunk1", b"chunk2", b"chunk3"]
        
        mock_response = {
            "Body": mock_body
        }
        
        mock_client = AsyncMock()
        mock_client.get_object.return_value = mock_response
        
        mock_session = AsyncMock()
        mock_session.client.return_value.__aenter__.return_value = mock_client
        
        with patch.object(storage_backend, 'session', mock_session):
            chunks = []
            async for chunk in storage_backend.download_file_stream(sample_storage_location):
                chunks.append(chunk)
            
            # Verify download was called with correct parameters
            mock_client.get_object.assert_called_once_with(
                Bucket=sample_storage_location.bucket,
                Key=sample_storage_location.key,
            )
            
            # Verify chunks
            assert chunks == [b"chunk1", b"chunk2", b"chunk3"]

    @pytest.mark.asyncio
    async def test_delete_file_success(self, storage_backend, sample_storage_location):
        """Test successful file deletion."""
        mock_client = AsyncMock()
        mock_session = AsyncMock()
        mock_session.client.return_value.__aenter__.return_value = mock_client
        
        with patch.object(storage_backend, 'session', mock_session):
            result = await storage_backend.delete_file(sample_storage_location)
            
            # Verify delete was called with correct parameters
            mock_client.delete_object.assert_called_once_with(
                Bucket=sample_storage_location.bucket,
                Key=sample_storage_location.key,
            )
            
            # Verify return value
            assert result is True

    @pytest.mark.asyncio
    async def test_file_exists_true(self, storage_backend, sample_storage_location):
        """Test file existence check when file exists."""
        mock_client = AsyncMock()
        mock_session = AsyncMock()
        mock_session.client.return_value.__aenter__.return_value = mock_client
        
        with patch.object(storage_backend, 'session', mock_session):
            result = await storage_backend.file_exists(sample_storage_location)
            
            # Verify head_object was called with correct parameters
            mock_client.head_object.assert_called_once_with(
                Bucket=sample_storage_location.bucket,
                Key=sample_storage_location.key,
            )
            
            # Verify return value
            assert result is True

    @pytest.mark.asyncio
    async def test_file_exists_false(self, storage_backend, sample_storage_location):
        """Test file existence check when file doesn't exist."""
        mock_client = AsyncMock()
        mock_client.head_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Key not found"}},
            "head_object"
        )
        
        mock_session = AsyncMock()
        mock_session.client.return_value.__aenter__.return_value = mock_client
        
        with patch.object(storage_backend, 'session', mock_session):
            result = await storage_backend.file_exists(sample_storage_location)
            
            # Verify return value
            assert result is False

    @pytest.mark.asyncio
    async def test_get_file_metadata_success(self, storage_backend, sample_storage_location):
        """Test successful file metadata retrieval."""
        mock_response = {
            "ContentLength": 1024,
            "ContentType": "application/pdf",
            "LastModified": datetime.utcnow(),
            "ETag": '"abc123"',
            "Metadata": {"test": "value"},
        }
        
        mock_client = AsyncMock()
        mock_client.head_object.return_value = mock_response
        
        mock_session = AsyncMock()
        mock_session.client.return_value.__aenter__.return_value = mock_client
        
        with patch.object(storage_backend, 'session', mock_session):
            result = await storage_backend.get_file_metadata(sample_storage_location)
            
            # Verify head_object was called with correct parameters
            mock_client.head_object.assert_called_once_with(
                Bucket=sample_storage_location.bucket,
                Key=sample_storage_location.key,
            )
            
            # Verify return value
            assert result["size"] == 1024
            assert result["content_type"] == "application/pdf"
            assert result["etag"] == "abc123"
            assert result["metadata"] == {"test": "value"}

    @pytest.mark.asyncio
    async def test_generate_presigned_url_success(self, storage_backend, sample_storage_location):
        """Test successful presigned URL generation."""
        mock_client = AsyncMock()
        mock_client.generate_presigned_url.return_value = "https://example.com/presigned-url"
        
        mock_session = AsyncMock()
        mock_session.client.return_value.__aenter__.return_value = mock_client
        
        with patch.object(storage_backend, 'session', mock_session):
            result = await storage_backend.generate_presigned_url(
                sample_storage_location,
                expiration_seconds=3600,
                operation="get",
            )
            
            # Verify generate_presigned_url was called with correct parameters
            mock_client.generate_presigned_url.assert_called_once_with(
                "get_object",
                Params={
                    "Bucket": sample_storage_location.bucket,
                    "Key": sample_storage_location.key,
                },
                ExpiresIn=3600,
            )
            
            # Verify return value
            assert result == "https://example.com/presigned-url"

    @pytest.mark.asyncio
    async def test_generate_presigned_url_invalid_operation(self, storage_backend, sample_storage_location):
        """Test presigned URL generation with invalid operation."""
        mock_client = AsyncMock()
        mock_session = AsyncMock()
        mock_session.client.return_value.__aenter__.return_value = mock_client
        
        with patch.object(storage_backend, 'session', mock_session):
            with pytest.raises(ValueError) as exc_info:
                await storage_backend.generate_presigned_url(
                    sample_storage_location,
                    operation="invalid",
                )
            
            assert "Unsupported operation" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_list_files_success(self, storage_backend):
        """Test successful file listing."""
        mock_response = {
            "Contents": [
                {
                    "Key": "test/file1.pdf",
                    "Size": 1024,
                    "LastModified": datetime.utcnow(),
                    "ETag": '"abc123"',
                },
                {
                    "Key": "test/file2.pdf",
                    "Size": 2048,
                    "LastModified": datetime.utcnow(),
                    "ETag": '"def456"',
                },
            ],
            "IsTruncated": False,
            "NextContinuationToken": None,
        }
        
        mock_client = AsyncMock()
        mock_client.list_objects_v2.return_value = mock_response
        
        mock_session = AsyncMock()
        mock_session.client.return_value.__aenter__.return_value = mock_client
        
        with patch.object(storage_backend, 'session', mock_session):
            result = await storage_backend.list_files(
                prefix="test/",
                limit=100,
                continuation_token=None,
            )
            
            # Verify list_objects_v2 was called with correct parameters
            mock_client.list_objects_v2.assert_called_once_with(
                Bucket="test-bucket",
                MaxKeys=100,
                Prefix="test/",
            )
            
            # Verify return value
            assert len(result["files"]) == 2
            assert result["files"][0]["key"] == "test/file1.pdf"
            assert result["files"][1]["key"] == "test/file2.pdf"
            assert result["is_truncated"] is False
            assert result["next_continuation_token"] is None

    @pytest.mark.asyncio
    async def test_copy_file_success(self, storage_backend):
        """Test successful file copy."""
        source_location = StorageLocation(
            backend=StorageBackend.S3,
            bucket="source-bucket",
            key="source/file.pdf",
            region="us-east-1",
            endpoint_url=None,
        )
        
        destination_location = StorageLocation(
            backend=StorageBackend.S3,
            bucket="dest-bucket",
            key="dest/file.pdf",
            region="us-east-1",
            endpoint_url=None,
        )
        
        mock_client = AsyncMock()
        mock_session = AsyncMock()
        mock_session.client.return_value.__aenter__.return_value = mock_client
        
        with patch.object(storage_backend, 'session', mock_session):
            result = await storage_backend.copy_file(source_location, destination_location)
            
            # Verify copy_object was called with correct parameters
            mock_client.copy_object.assert_called_once_with(
                CopySource={
                    "Bucket": source_location.bucket,
                    "Key": source_location.key,
                },
                Bucket=destination_location.bucket,
                Key=destination_location.key,
            )
            
            # Verify return value
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_success(self, storage_backend):
        """Test successful health check."""
        mock_client = AsyncMock()
        mock_session = AsyncMock()
        mock_session.client.return_value.__aenter__.return_value = mock_client
        
        with patch.object(storage_backend, 'session', mock_session):
            result = await storage_backend.health_check()
            
            # Verify head_bucket was called with correct parameters
            mock_client.head_bucket.assert_called_once_with(Bucket="test-bucket")
            
            # Verify return value
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, storage_backend):
        """Test health check failure."""
        mock_client = AsyncMock()
        mock_client.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "NoSuchBucket", "Message": "Bucket not found"}},
            "head_bucket"
        )
        
        mock_session = AsyncMock()
        mock_session.client.return_value.__aenter__.return_value = mock_client
        
        with patch.object(storage_backend, 'session', mock_session):
            result = await storage_backend.health_check()
            
            # Verify return value
            assert result is False

    def test_handle_client_error_mapping(self, storage_backend):
        """Test client error mapping to custom exceptions."""
        # Test NoSuchKey -> FileNotFoundError
        error = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Key not found"}},
            "get_object"
        )
        
        with pytest.raises(FileNotFoundError):
            import asyncio
            asyncio.run(storage_backend._handle_client_error(error, "test"))
        
        # Test AccessDenied -> StoragePermissionError
        error = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
            "get_object"
        )
        
        with pytest.raises(StoragePermissionError):
            import asyncio
            asyncio.run(storage_backend._handle_client_error(error, "test"))
        
        # Test QuotaExceeded -> StorageQuotaError
        error = ClientError(
            {"Error": {"Code": "QuotaExceeded", "Message": "Quota exceeded"}},
            "put_object"
        )
        
        with pytest.raises(StorageQuotaError):
            import asyncio
            asyncio.run(storage_backend._handle_client_error(error, "test"))
        
        # Test NoSuchBucket -> StorageConnectionError
        error = ClientError(
            {"Error": {"Code": "NoSuchBucket", "Message": "Bucket not found"}},
            "head_bucket"
        )
        
        with pytest.raises(StorageConnectionError):
            import asyncio
            asyncio.run(storage_backend._handle_client_error(error, "test"))


class TestStorageFactory:
    """Test storage factory."""

    def test_create_s3_backend(self):
        """Test creating S3 backend."""
        with patch('app.storage.factory.settings') as mock_settings:
            mock_settings.STORAGE_BACKEND = "s3"
            mock_settings.S3_BUCKET_NAME = "test-bucket"
            mock_settings.S3_REGION = "us-east-1"
            mock_settings.S3_ENDPOINT_URL = None
            mock_settings.S3_ACCESS_KEY_ID = "test-key"
            mock_settings.S3_SECRET_ACCESS_KEY = "test-secret"
            
            backend = StorageFactory.create_backend()
            assert isinstance(backend, S3StorageBackend)

    def test_create_minio_backend(self):
        """Test creating MinIO backend."""
        with patch('app.storage.factory.settings') as mock_settings:
            mock_settings.STORAGE_BACKEND = "minio"
            mock_settings.S3_BUCKET_NAME = "test-bucket"
            mock_settings.S3_REGION = "us-east-1"
            mock_settings.S3_ENDPOINT_URL = "http://localhost:9000"
            mock_settings.S3_ACCESS_KEY_ID = "test-key"
            mock_settings.S3_SECRET_ACCESS_KEY = "test-secret"
            
            backend = StorageFactory.create_backend()
            assert isinstance(backend, S3StorageBackend)

    def test_create_backend_with_explicit_type(self):
        """Test creating backend with explicit type."""
        with patch('app.storage.factory.settings') as mock_settings:
            mock_settings.S3_BUCKET_NAME = "test-bucket"
            mock_settings.S3_REGION = "us-east-1"
            mock_settings.S3_ENDPOINT_URL = None
            mock_settings.S3_ACCESS_KEY_ID = "test-key"
            mock_settings.S3_SECRET_ACCESS_KEY = "test-secret"
            
            backend = StorageFactory.create_backend("s3")
            assert isinstance(backend, S3StorageBackend)

    def test_create_backend_unsupported_type(self):
        """Test creating backend with unsupported type."""
        with pytest.raises(StorageError) as exc_info:
            StorageFactory.create_backend("unsupported")
        
        assert "Unsupported storage backend" in str(exc_info.value)

    def test_register_backend(self):
        """Test registering new backend."""
        class TestBackend(S3StorageBackend):
            pass
        
        StorageFactory.register_backend("test", TestBackend)
        assert "test" in StorageFactory.get_available_backends()

    def test_register_backend_invalid_class(self):
        """Test registering backend with invalid class."""
        class InvalidBackend:
            pass
        
        with pytest.raises(ValueError) as exc_info:
            StorageFactory.register_backend("invalid", InvalidBackend)
        
        assert "Backend class must inherit from StorageBackend" in str(exc_info.value)

    def test_get_available_backends(self):
        """Test getting available backends."""
        backends = StorageFactory.get_available_backends()
        assert "s3" in backends
        assert "minio" in backends

    def test_get_storage_backend_cached(self):
        """Test that get_storage_backend returns cached instance."""
        with patch('app.storage.factory.settings') as mock_settings:
            mock_settings.STORAGE_BACKEND = "s3"
            mock_settings.S3_BUCKET_NAME = "test-bucket"
            mock_settings.S3_REGION = "us-east-1"
            mock_settings.S3_ENDPOINT_URL = None
            mock_settings.S3_ACCESS_KEY_ID = "test-key"
            mock_settings.S3_SECRET_ACCESS_KEY = "test-secret"
            
            from app.storage.factory import get_storage_backend
            
            # Clear cache first
            get_storage_backend.cache_clear()
            
            backend1 = get_storage_backend()
            backend2 = get_storage_backend()
            
            # Should be the same instance due to LRU cache
            assert backend1 is backend2