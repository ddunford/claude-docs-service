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
    
    @pytest.mark.asyncio
    async def test_list_documents_success(self, document_service):
        """Test successful document listing."""
        from app.models.document import DocumentListRequest, SortOrder, DocumentStatus
        
        request = DocumentListRequest(
            user_id=str(uuid.uuid4()),
            tenant_id=str(uuid.uuid4()),
            offset=0,
            limit=10,
            sort_by="created_at",
            sort_order=SortOrder.DESC,
        )
        
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        
        # Mock database operations
        with patch('app.services.document_service.get_db') as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value.__aenter__.return_value = mock_db
            
            # Mock document results
            mock_document = Mock()
            mock_document.id = str(uuid.uuid4())
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
            
            # Mock query results
            mock_count_result = Mock()
            mock_count_result.scalar.return_value = 1
            
            mock_documents_result = Mock()
            mock_documents_result.scalars.return_value.all.return_value = [mock_document]
            
            mock_db.execute.side_effect = [mock_count_result, mock_documents_result]
            
            # Execute list
            result = await document_service.list_documents(request, user_id, tenant_id)
            
            # Verify result
            assert len(result.documents) == 1
            assert result.total_count == 1
            assert result.has_more is False
            assert result.next_token is None
            assert result.documents[0].document_id == mock_document.id
    
    @pytest.mark.asyncio
    async def test_list_documents_with_filters(self, document_service):
        """Test document listing with various filters."""
        from app.models.document import DocumentListRequest, SortOrder, DocumentStatus, DateRange
        
        # Test with all filters
        request = DocumentListRequest(
            user_id=str(uuid.uuid4()),
            tenant_id=str(uuid.uuid4()),
            tags=["test", "document"],
            status=DocumentStatus.ACTIVE,
            date_range=DateRange(
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31),
            ),
            offset=0,
            limit=5,
            sort_by="filename",
            sort_order=SortOrder.ASC,
        )
        
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        
        with patch('app.services.document_service.get_db') as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value.__aenter__.return_value = mock_db
            
            # Mock empty results
            mock_count_result = Mock()
            mock_count_result.scalar.return_value = 0
            
            mock_documents_result = Mock()
            mock_documents_result.scalars.return_value.all.return_value = []
            
            mock_db.execute.side_effect = [mock_count_result, mock_documents_result]
            
            # Execute list
            result = await document_service.list_documents(request, user_id, tenant_id)
            
            # Verify result
            assert len(result.documents) == 0
            assert result.total_count == 0
            assert result.has_more is False
    
    @pytest.mark.asyncio
    async def test_list_documents_with_pagination(self, document_service):
        """Test document listing with pagination."""
        from app.models.document import DocumentListRequest, SortOrder
        
        request = DocumentListRequest(
            user_id=str(uuid.uuid4()),
            tenant_id=str(uuid.uuid4()),
            offset=10,
            limit=5,
            sort_by="created_at",
            sort_order=SortOrder.DESC,
        )
        
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        
        with patch('app.services.document_service.get_db') as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value.__aenter__.return_value = mock_db
            
            # Mock pagination results - total 20, returning 5, has more
            mock_count_result = Mock()
            mock_count_result.scalar.return_value = 20
            
            mock_documents_result = Mock()
            mock_documents_result.scalars.return_value.all.return_value = [Mock() for _ in range(5)]
            
            # Set up each mock document
            for i, doc in enumerate(mock_documents_result.scalars.return_value.all.return_value):
                doc.id = str(uuid.uuid4())
                doc.filename = f"test{i}.pdf"
                doc.content_type = "application/pdf"
                doc.size_bytes = 1024 + i
                doc.owner_id = user_id
                doc.tenant_id = tenant_id
                doc.tags = ["test"]
                doc.title = f"Test Document {i}"
                doc.description = "A test document"
                doc.created_at = datetime.utcnow()
                doc.updated_at = datetime.utcnow()
                doc.version = 1
                doc.status = "active"
                doc.checksum = f"abc{i}"
                doc.attributes = {}
            
            mock_db.execute.side_effect = [mock_count_result, mock_documents_result]
            
            # Execute list
            result = await document_service.list_documents(request, user_id, tenant_id)
            
            # Verify pagination
            assert len(result.documents) == 5
            assert result.total_count == 20
            assert result.has_more is True
            assert result.next_token == "15"  # 10 + 5
    
    @pytest.mark.asyncio
    async def test_upload_document_database_failure(self, document_service, sample_document_create, sample_file_data):
        """Test document upload with database failure."""
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        
        # Mock storage backend success
        with patch.object(document_service, 'storage') as mock_storage:
            mock_storage.upload_file = AsyncMock(return_value=Mock(
                backend="s3",
                bucket="test-bucket",
                key="test-key",
                region="us-east-1",
                endpoint_url=None,
            ))
            
            # Mock database failure
            with patch('app.services.document_service.get_db') as mock_get_db:
                mock_db = AsyncMock()
                mock_db.add = Mock()
                mock_db.commit = AsyncMock(side_effect=Exception("Database commit failed"))
                mock_context = AsyncMock()
                mock_context.__aenter__ = AsyncMock(return_value=mock_db)
                mock_context.__aexit__ = AsyncMock(return_value=None)
                mock_get_db.return_value = mock_context
                
                # Execute upload and expect failure
                with pytest.raises(Exception) as exc_info:
                    await document_service.upload_document(
                        file_data=sample_file_data,
                        document_create=sample_document_create,
                        user_id=user_id,
                        tenant_id=tenant_id,
                    )
                
                assert "Database commit failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_upload_document_with_session_id(self, document_service, sample_document_create, sample_file_data):
        """Test document upload with session ID for cleanup."""
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        
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
                
                # Mock Redis cleanup
                with patch('app.services.document_service.redis_client') as mock_redis:
                    mock_redis.delete_upload_session = AsyncMock(return_value=True)
                    
                    # Execute upload
                    result = await document_service.upload_document(
                        file_data=sample_file_data,
                        document_create=sample_document_create,
                        user_id=user_id,
                        tenant_id=tenant_id,
                        session_id=session_id,
                    )
                    
                    # Verify session cleanup
                    mock_redis.delete_upload_session.assert_called_once_with(session_id)
    
    @pytest.mark.asyncio
    async def test_get_document_with_versions_and_scan_results(self, document_service):
        """Test document retrieval with versions and scan results."""
        document_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        
        # Mock document with versions and scan results
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
        mock_document.version = 2
        mock_document.status = "active"
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
        
        # Mock versions
        mock_version1 = Mock()
        mock_version1.version = 1
        mock_version1.created_at = datetime.utcnow()
        mock_version1.created_by = user_id
        mock_version1.description = "Initial version"
        mock_version1.size_bytes = 512
        mock_version1.checksum = "def456"
        mock_version1.backend = "s3"
        mock_version1.bucket = "test-bucket"
        mock_version1.key = "test-key-v1"
        mock_version1.region = "us-east-1"
        mock_version1.endpoint_url = None
        
        mock_version2 = Mock()
        mock_version2.version = 2
        mock_version2.created_at = datetime.utcnow()
        mock_version2.created_by = user_id
        mock_version2.description = "Updated version"
        mock_version2.size_bytes = 1024
        mock_version2.checksum = "abc123"
        mock_version2.backend = "s3"
        mock_version2.bucket = "test-bucket"
        mock_version2.key = "test-key-v2"
        mock_version2.region = "us-east-1"
        mock_version2.endpoint_url = None
        
        mock_document.versions = [mock_version1, mock_version2]
        
        # Mock scan results
        mock_scan_result = Mock()
        mock_scan_result.scan_id = str(uuid.uuid4())
        mock_scan_result.document_id = document_id
        mock_scan_result.status = "completed"
        mock_scan_result.result = "clean"
        mock_scan_result.scanner_version = "1.0.0"
        mock_scan_result.duration_ms = 1000
        mock_scan_result.started_at = datetime.utcnow()
        mock_scan_result.completed_at = datetime.utcnow()
        mock_scan_result.threats = []
        
        mock_document.scan_results = [mock_scan_result]
        
        # Mock database operations
        with patch('app.services.document_service.get_db') as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value.__aenter__.return_value = mock_db
            
            # Mock query result
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_document
            mock_db.execute.return_value = mock_result
            
            # Mock audit log operations
            mock_db.add = Mock()
            mock_db.commit = AsyncMock()
            
            # Execute get
            result = await document_service.get_document(
                document_id=document_id,
                user_id=user_id,
                tenant_id=tenant_id,
            )
            
            # Verify result includes versions and scan
            assert result.metadata.document_id == document_id
            assert result.metadata.version == 2
            assert len(result.versions) == 2
            assert result.versions[0].version == 1
            assert result.versions[1].version == 2
            assert result.last_scan is not None
            assert result.last_scan.scan_id == mock_scan_result.scan_id
    
    @pytest.mark.asyncio
    async def test_get_document_no_storage_location(self, document_service):
        """Test document retrieval when no storage location found."""
        document_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        
        # Mock document without primary storage location
        mock_document = Mock()
        mock_document.id = document_id
        mock_document.owner_id = user_id
        mock_document.tenant_id = tenant_id
        mock_document.status = "active"
        mock_document.storage_locations = []  # No storage locations
        
        # Mock database operations
        with patch('app.services.document_service.get_db') as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value.__aenter__.return_value = mock_db
            
            # Mock query result
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_document
            mock_db.execute.return_value = mock_result
            
            # Execute get and expect failure
            with pytest.raises(ValueError) as exc_info:
                await document_service.get_document(
                    document_id=document_id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                )
            
            assert "No storage location found" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_delete_document_already_deleted(self, document_service):
        """Test deleting a document that's already deleted."""
        document_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        
        # Mock database operations - no document found (already deleted)
        with patch('app.services.document_service.get_db') as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value.__aenter__.return_value = mock_db
            
            # Mock query result - no document found
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute.return_value = mock_result
            
            # Execute delete and expect failure
            with pytest.raises(ValueError) as exc_info:
                await document_service.delete_document(
                    document_id=document_id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                )
            
            assert "Document not found" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_list_documents_database_error(self, document_service):
        """Test document listing with database error."""
        from app.models.document import DocumentListRequest, SortOrder
        
        request = DocumentListRequest(
            user_id=str(uuid.uuid4()),
            tenant_id=str(uuid.uuid4()),
            offset=0,
            limit=10,
            sort_by="created_at",
            sort_order=SortOrder.DESC,
        )
        
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        
        # Mock database error
        with patch('app.services.document_service.get_db') as mock_get_db:
            mock_db = AsyncMock()
            mock_db.execute.side_effect = Exception("Database error")
            mock_get_db.return_value.__aenter__.return_value = mock_db
            
            # Execute list and expect failure
            with pytest.raises(Exception) as exc_info:
                await document_service.list_documents(request, user_id, tenant_id)
            
            assert "Database error" in str(exc_info.value)