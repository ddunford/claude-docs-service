"""Tests for document service."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import uuid
from datetime import datetime

from app.services.document_service import DocumentService
from app.models.document import DocumentCreate, DocumentStatus, UploadStatus


class TestDocumentService:
    """Test document service."""
    
    @pytest.fixture
    def document_service(self):
        """Create document service instance."""
        return DocumentService()
    
    @pytest.fixture
    def sample_document_create(self):
        """Create sample document creation request."""
        return DocumentCreate(
            filename="test.pdf",
            content_type="application/pdf",
            title="Test Document",
            description="A test document",
            tags=["test", "document"],
            attributes={"category": "test"},
        )
    
    @pytest.fixture
    def sample_file_data(self):
        """Create sample file data."""
        return b"Sample PDF content"
    
    @pytest.mark.asyncio
    async def test_upload_document_success(
        self,
        document_service,
        sample_document_create,
        sample_file_data,
    ):
        """Test successful document upload."""
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        
        # Mock storage backend
        with patch.object(document_service, 'storage') as mock_storage:
            mock_storage.upload_file = AsyncMock(return_value=Mock(
                backend="s3",
                bucket="test-bucket",
                key="test-key",
                region="us-east-1",
                endpoint_url=None,
            ))
            
            # Mock database operations  
            with patch('app.services.document_service.get_db') as mock_get_db:
                mock_db = AsyncMock()
                mock_db.add = Mock()
                mock_db.commit = AsyncMock()
                mock_context = AsyncMock()
                mock_context.__aenter__ = AsyncMock(return_value=mock_db)
                mock_context.__aexit__ = AsyncMock(return_value=None)
                mock_get_db.return_value = mock_context
                
                # Mock Redis client cleanup
                with patch('app.services.document_service.redis_client') as mock_redis:
                    mock_redis.delete_upload_session = AsyncMock(return_value=True)
                    
                    # Execute upload
                    result = await document_service.upload_document(
                        file_data=sample_file_data,
                        document_create=sample_document_create,
                        user_id=user_id,
                        tenant_id=tenant_id,
                    )
                
                # Verify result
                assert result.status == UploadStatus.COMPLETED
                assert result.size_bytes == len(sample_file_data)
                assert result.document_id is not None
                assert result.checksum is not None
                
                # Verify storage was called
                mock_storage.upload_file.assert_called_once()
                
                # Verify database operations
                assert mock_db.add.call_count >= 3  # Document, Storage, Version records
                mock_db.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_upload_document_storage_failure(
        self,
        document_service,
        sample_document_create,
        sample_file_data,
    ):
        """Test document upload with storage failure."""
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        
        # Mock storage backend failure
        with patch.object(document_service, 'storage') as mock_storage:
            mock_storage.upload_file = AsyncMock(side_effect=Exception("Storage failed"))
            
            # Mock database operations
            with patch('app.services.document_service.get_db') as mock_get_db:
                mock_db = AsyncMock()
                mock_get_db.return_value.__aenter__.return_value = mock_db
                
                # Execute upload and expect failure
                with pytest.raises(Exception) as exc_info:
                    await document_service.upload_document(
                        file_data=sample_file_data,
                        document_create=sample_document_create,
                        user_id=user_id,
                        tenant_id=tenant_id,
                    )
                
                assert "Storage failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_get_document_success(
        self,
        document_service,
    ):
        """Test successful document retrieval."""
        document_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        
        # Mock database document
        mock_document = Mock()
        mock_document.id = document_id
        mock_document.filename = "test.pdf"
        mock_document.content_type = "application/pdf"
        mock_document.size_bytes = 1024
        mock_document.owner_id = user_id
        mock_document.tenant_id = tenant_id
        mock_document.tags = ["test"]
        mock_document.title = "Test Document"
        mock_document.description = "A test document"
        mock_document.created_at = datetime.utcnow()
        mock_document.updated_at = datetime.utcnow()
        mock_document.version = 1
        mock_document.status = DocumentStatus.ACTIVE
        mock_document.checksum = "abc123"
        mock_document.attributes = {}
        
        # Mock storage location
        mock_storage_location = Mock()
        mock_storage_location.backend = "s3"
        mock_storage_location.bucket = "test-bucket"
        mock_storage_location.key = "test-key"
        mock_storage_location.region = "us-east-1"
        mock_storage_location.endpoint_url = None
        mock_storage_location.is_primary = True
        
        mock_document.storage_locations = [mock_storage_location]
        mock_document.versions = []
        
        # Mock database operations
        with patch('app.services.document_service.get_db') as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value.__aenter__.return_value = mock_db
            
            # Mock query result
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_document
            mock_db.execute.return_value = mock_result
            
            # Execute get
            result = await document_service.get_document(
                document_id=document_id,
                user_id=user_id,
                tenant_id=tenant_id,
            )
            
            # Verify result
            assert result.metadata.document_id == document_id
            assert result.metadata.filename == "test.pdf"
            assert result.metadata.owner_id == user_id
            assert result.location.backend == "s3"
    
    @pytest.mark.asyncio
    async def test_get_document_not_found(
        self,
        document_service,
    ):
        """Test document retrieval when document not found."""
        document_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        
        # Mock database operations
        with patch('app.services.document_service.get_db') as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value.__aenter__.return_value = mock_db
            
            # Mock query result - no document found
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute.return_value = mock_result
            
            # Execute get and expect failure
            with pytest.raises(ValueError) as exc_info:
                await document_service.get_document(
                    document_id=document_id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                )
            
            assert "Document not found" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_get_document_permission_denied(
        self,
        document_service,
    ):
        """Test document retrieval with permission denied."""
        document_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        other_user_id = str(uuid.uuid4())
        
        # Mock database document owned by different user
        mock_document = Mock()
        mock_document.id = document_id
        mock_document.owner_id = other_user_id  # Different user
        mock_document.tenant_id = tenant_id
        mock_document.status = DocumentStatus.ACTIVE
        
        # Mock database operations
        with patch('app.services.document_service.get_db') as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value.__aenter__.return_value = mock_db
            
            # Mock query result
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_document
            mock_db.execute.return_value = mock_result
            
            # Execute get and expect permission error
            with pytest.raises(PermissionError) as exc_info:
                await document_service.get_document(
                    document_id=document_id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                )
            
            assert "Access denied" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_delete_document_success(
        self,
        document_service,
    ):
        """Test successful document deletion."""
        document_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        
        # Mock database document
        mock_document = Mock()
        mock_document.id = document_id
        mock_document.owner_id = user_id
        mock_document.tenant_id = tenant_id
        mock_document.status = DocumentStatus.ACTIVE
        
        # Mock database operations
        with patch('app.services.document_service.get_db') as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value.__aenter__.return_value = mock_db
            
            # Mock query result
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_document
            mock_db.execute.return_value = mock_result
            
            # Execute delete
            result = await document_service.delete_document(
                document_id=document_id,
                user_id=user_id,
                tenant_id=tenant_id,
            )
            
            # Verify result
            assert result is True
            
            # Verify document was marked as deleted
            assert mock_document.status == DocumentStatus.DELETED
            
            # Verify database operations
            mock_db.add.assert_called_once()  # Audit log
            mock_db.commit.assert_called_once()