"""Tests for gRPC server implementation."""

import pytest
import grpc
import asyncio
import uuid
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
from google.protobuf.empty_pb2 import Empty

from app.api.grpc_server import DocumentServiceServicer
from app.models.document import (
    DocumentCreate, DocumentResponse, DocumentMetadata, 
    UploadResponse, UploadStatus, DocumentStatus, StorageLocation,
    StorageBackend, DocumentListRequest, DocumentListResponse,
    ScanResult, ScanStatus, ScanResultType, ThreatDetail, ThreatSeverity
)
from docs.v1 import document_pb2 as pb
from docs.v1 import document_pb2_grpc


class TestDocumentServiceServicer:
    """Test gRPC service implementation."""
    
    @pytest.fixture
    def servicer(self):
        """Create servicer instance."""
        return DocumentServiceServicer()
    
    @pytest.fixture
    def mock_context(self):
        """Create mock gRPC context."""
        context = Mock()
        context.invocation_metadata.return_value = [
            ('user-id', str(uuid.uuid4())),
            ('tenant-id', str(uuid.uuid4())),
        ]
        return context
    
    @pytest.fixture
    def sample_upload_request(self):
        """Create sample upload request."""
        metadata = pb.DocumentMetadata(
            filename="test.pdf",
            content_type="application/pdf",
            title="Test Document",
            description="A test document",
            tags=["test", "document"],
            attributes={"category": "test"},
        )
        
        return pb.UploadRequest(
            metadata=metadata,
            content=b"Sample PDF content",
            content_type="application/pdf",
            filename="test.pdf",
            session_id=str(uuid.uuid4()),
        )
    
    @pytest.fixture
    def sample_document_id_request(self):
        """Create sample document ID request."""
        return pb.DocumentIdRequest(
            document_id=str(uuid.uuid4()),
            user_id=str(uuid.uuid4()),
            tenant_id=str(uuid.uuid4()),
        )
    
    @pytest.fixture
    def sample_list_request(self):
        """Create sample list request."""
        return pb.ListRequest(
            user_id=str(uuid.uuid4()),
            tenant_id=str(uuid.uuid4()),
            tags=["test"],
            status=pb.DocumentStatus.DOCUMENT_STATUS_ACTIVE,
            offset=0,
            limit=10,
            sort_by="created_at",
            sort_order=pb.SortOrder.SORT_ORDER_DESC,
        )
    
    @pytest.mark.asyncio
    async def test_upload_document_success(self, servicer, mock_context, sample_upload_request):
        """Test successful document upload."""
        # Mock document service
        mock_upload_response = UploadResponse(
            document_id=str(uuid.uuid4()),
            status=UploadStatus.COMPLETED,
            location=StorageLocation(
                backend=StorageBackend.S3,
                bucket="test-bucket",
                key="test-key",
                region="us-east-1",
            ),
            uploaded_at=datetime.utcnow(),
            size_bytes=1024,
            checksum="abc123",
        )
        
        with patch.object(servicer.document_service, 'upload_document', new_callable=AsyncMock) as mock_upload:
            mock_upload.return_value = mock_upload_response
            
            # Execute upload
            response = await servicer.UploadDocument(sample_upload_request, mock_context)
            
            # Verify response
            assert response.document_id == mock_upload_response.document_id
            assert response.status == pb.UploadStatus.UPLOAD_STATUS_COMPLETED
            assert response.size_bytes == 1024
            assert response.checksum == "abc123"
            
            # Verify service was called
            mock_upload.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_upload_document_missing_metadata(self, servicer, sample_upload_request):
        """Test upload with missing user metadata."""
        # Mock context with missing metadata
        mock_context = Mock()
        mock_context.invocation_metadata.return_value = []
        
        # Execute upload
        response = await servicer.UploadDocument(sample_upload_request, mock_context)
        
        # Verify error response
        assert response.document_id == ""
        mock_context.set_code.assert_called_with(grpc.StatusCode.UNAUTHENTICATED)
        mock_context.set_details.assert_called_with('Missing user-id or tenant-id in metadata')
    
    @pytest.mark.asyncio
    async def test_upload_document_file_too_large(self, servicer, mock_context, sample_upload_request):
        """Test upload with file too large."""
        # Mock settings to have small file size limit
        with patch('app.api.grpc_server.settings') as mock_settings:
            mock_settings.MAX_FILE_SIZE_BYTES = 10  # Very small limit
            
            # Execute upload
            response = await servicer.UploadDocument(sample_upload_request, mock_context)
            
            # Verify error response
            assert response.document_id == ""
            mock_context.set_code.assert_called_with(grpc.StatusCode.INVALID_ARGUMENT)
            assert "exceeds maximum allowed size" in mock_context.set_details.call_args[0][0]
    
    @pytest.mark.asyncio
    async def test_upload_document_service_error(self, servicer, mock_context, sample_upload_request):
        """Test upload with service error."""
        # Mock document service to raise error
        with patch.object(servicer.document_service, 'upload_document', new_callable=AsyncMock) as mock_upload:
            mock_upload.side_effect = Exception("Service error")
            
            # Execute upload
            response = await servicer.UploadDocument(sample_upload_request, mock_context)
            
            # Verify error response
            assert response.document_id == ""
            mock_context.set_code.assert_called_with(grpc.StatusCode.INTERNAL)
            mock_context.set_details.assert_called_with('Internal server error')
    
    @pytest.mark.asyncio
    async def test_get_document_success(self, servicer, mock_context, sample_document_id_request):
        """Test successful document retrieval."""
        # Mock document service
        mock_document_response = DocumentResponse(
            metadata=DocumentMetadata(
                document_id=sample_document_id_request.document_id,
                filename="test.pdf",
                content_type="application/pdf",
                size_bytes=1024,
                owner_id=str(uuid.uuid4()),
                tenant_id=str(uuid.uuid4()),
                tags=["test"],
                title="Test Document",
                description="A test document",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                version=1,
                status=DocumentStatus.ACTIVE,
                checksum="abc123",
                attributes={},
            ),
            location=StorageLocation(
                backend=StorageBackend.S3,
                bucket="test-bucket",
                key="test-key",
                region="us-east-1",
            ),
            versions=[],
            last_scan=None,
        )
        
        with patch.object(servicer.document_service, 'get_document', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_document_response
            
            # Execute get
            response = await servicer.GetDocument(sample_document_id_request, mock_context)
            
            # Verify response
            assert response.metadata.document_id == sample_document_id_request.document_id
            assert response.metadata.filename == "test.pdf"
            assert response.location.bucket == "test-bucket"
            
            # Verify service was called
            mock_get.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_document_not_found(self, servicer, mock_context, sample_document_id_request):
        """Test get document when not found."""
        # Mock document service to raise ValueError
        with patch.object(servicer.document_service, 'get_document', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = ValueError("Document not found")
            
            # Execute get
            response = await servicer.GetDocument(sample_document_id_request, mock_context)
            
            # Verify error response
            assert response.metadata.document_id == ""
            mock_context.set_code.assert_called_with(grpc.StatusCode.NOT_FOUND)
            mock_context.set_details.assert_called_with("Document not found")
    
    @pytest.mark.asyncio
    async def test_get_document_permission_denied(self, servicer, mock_context, sample_document_id_request):
        """Test get document with permission denied."""
        # Mock document service to raise PermissionError
        with patch.object(servicer.document_service, 'get_document', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = PermissionError("Access denied")
            
            # Execute get
            response = await servicer.GetDocument(sample_document_id_request, mock_context)
            
            # Verify error response
            assert response.metadata.document_id == ""
            mock_context.set_code.assert_called_with(grpc.StatusCode.PERMISSION_DENIED)
            mock_context.set_details.assert_called_with("Access denied")
    
    @pytest.mark.asyncio
    async def test_delete_document_success(self, servicer, mock_context, sample_document_id_request):
        """Test successful document deletion."""
        # Mock document service
        with patch.object(servicer.document_service, 'delete_document', new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = True
            
            # Execute delete
            response = await servicer.DeleteDocument(sample_document_id_request, mock_context)
            
            # Verify response
            assert isinstance(response, Empty)
            
            # Verify service was called
            mock_delete.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_delete_document_not_found(self, servicer, mock_context, sample_document_id_request):
        """Test delete document when not found."""
        # Mock document service to raise ValueError
        with patch.object(servicer.document_service, 'delete_document', new_callable=AsyncMock) as mock_delete:
            mock_delete.side_effect = ValueError("Document not found")
            
            # Execute delete
            response = await servicer.DeleteDocument(sample_document_id_request, mock_context)
            
            # Verify error response
            assert isinstance(response, Empty)
            mock_context.set_code.assert_called_with(grpc.StatusCode.NOT_FOUND)
            mock_context.set_details.assert_called_with("Document not found")
    
    @pytest.mark.asyncio
    async def test_scan_document_success(self, servicer, mock_context, sample_document_id_request):
        """Test successful document scan."""
        # Mock document service
        mock_document_response = DocumentResponse(
            metadata=DocumentMetadata(
                document_id=sample_document_id_request.document_id,
                filename="test.pdf",
                content_type="application/pdf",
                size_bytes=1024,
                owner_id=str(uuid.uuid4()),
                tenant_id=str(uuid.uuid4()),
                tags=["test"],
                title="Test Document",
                description="A test document",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                version=1,
                status=DocumentStatus.ACTIVE,
                checksum="abc123",
                attributes={},
            ),
            location=StorageLocation(
                backend=StorageBackend.S3,
                bucket="test-bucket",
                key="test-key",
                region="us-east-1",
            ),
            versions=[],
            last_scan=None,
        )
        
        # Mock virus scanner
        mock_scan_result = ScanResult(
            scan_id=str(uuid.uuid4()),
            document_id=sample_document_id_request.document_id,
            status=ScanStatus.COMPLETED,
            result=ScanResultType.CLEAN,
            scanned_at=datetime.utcnow(),
            duration_ms=1000,
            threats=[],
            scanner_version="1.0.0",
        )
        
        with patch.object(servicer.document_service, 'get_document', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_document_response
            
            with patch.object(servicer.virus_scanner, 'scan_bytes', new_callable=AsyncMock) as mock_scan:
                mock_scan.return_value = mock_scan_result
                
                # Execute scan
                response = await servicer.ScanDocument(sample_document_id_request, mock_context)
                
                # Verify response
                assert response.scan_id == mock_scan_result.scan_id
                assert response.document_id == sample_document_id_request.document_id
                assert response.status == pb.ScanStatus.SCAN_STATUS_COMPLETED
                assert response.result == pb.ScanResultType.SCAN_RESULT_TYPE_CLEAN
                
                # Verify services were called
                mock_get.assert_called_once()
                mock_scan.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_scan_document_infected(self, servicer, mock_context, sample_document_id_request):
        """Test document scan with infected result."""
        # Mock document service
        mock_document_response = DocumentResponse(
            metadata=DocumentMetadata(
                document_id=sample_document_id_request.document_id,
                filename="test.pdf",
                content_type="application/pdf",
                size_bytes=1024,
                owner_id=str(uuid.uuid4()),
                tenant_id=str(uuid.uuid4()),
                tags=["test"],
                title="Test Document",
                description="A test document",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                version=1,
                status=DocumentStatus.ACTIVE,
                checksum="abc123",
                attributes={},
            ),
            location=StorageLocation(
                backend=StorageBackend.S3,
                bucket="test-bucket",
                key="test-key",
                region="us-east-1",
            ),
            versions=[],
            last_scan=None,
        )
        
        # Mock virus scanner with infected result
        mock_scan_result = ScanResult(
            scan_id=str(uuid.uuid4()),
            document_id=sample_document_id_request.document_id,
            status=ScanStatus.COMPLETED,
            result=ScanResultType.INFECTED,
            scanned_at=datetime.utcnow(),
            duration_ms=1000,
            threats=[
                ThreatDetail(
                    name="Test.Virus",
                    type="virus",
                    severity=ThreatSeverity.HIGH,
                    description="Test virus detected",
                )
            ],
            scanner_version="1.0.0",
        )
        
        with patch.object(servicer.document_service, 'get_document', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_document_response
            
            with patch.object(servicer.virus_scanner, 'scan_bytes', new_callable=AsyncMock) as mock_scan:
                mock_scan.return_value = mock_scan_result
                
                # Execute scan
                response = await servicer.ScanDocument(sample_document_id_request, mock_context)
                
                # Verify response
                assert response.result == pb.ScanResultType.SCAN_RESULT_TYPE_INFECTED
                assert len(response.threats) == 1
                assert response.threats[0].name == "Test.Virus"
                assert response.threats[0].severity == pb.ThreatSeverity.THREAT_SEVERITY_HIGH
    
    @pytest.mark.asyncio
    async def test_list_documents_success(self, servicer, mock_context, sample_list_request):
        """Test successful document listing."""
        # Mock document service
        mock_list_response = DocumentListResponse(
            documents=[
                DocumentMetadata(
                    document_id=str(uuid.uuid4()),
                    filename="test1.pdf",
                    content_type="application/pdf",
                    size_bytes=1024,
                    owner_id=str(uuid.uuid4()),
                    tenant_id=str(uuid.uuid4()),
                    tags=["test"],
                    title="Test Document 1",
                    description="A test document",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                    version=1,
                    status=DocumentStatus.ACTIVE,
                    checksum="abc123",
                    attributes={},
                ),
                DocumentMetadata(
                    document_id=str(uuid.uuid4()),
                    filename="test2.pdf",
                    content_type="application/pdf",
                    size_bytes=2048,
                    owner_id=str(uuid.uuid4()),
                    tenant_id=str(uuid.uuid4()),
                    tags=["test"],
                    title="Test Document 2",
                    description="Another test document",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                    version=1,
                    status=DocumentStatus.ACTIVE,
                    checksum="def456",
                    attributes={},
                ),
            ],
            total_count=2,
            has_more=False,
            next_token=None,
        )
        
        with patch.object(servicer.document_service, 'list_documents', new_callable=AsyncMock) as mock_list:
            mock_list.return_value = mock_list_response
            
            # Execute list
            response = await servicer.ListDocuments(sample_list_request, mock_context)
            
            # Verify response
            assert len(response.documents) == 2
            assert response.total_count == 2
            assert response.has_more == False
            assert response.documents[0].filename == "test1.pdf"
            assert response.documents[1].filename == "test2.pdf"
            
            # Verify service was called
            mock_list.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_list_documents_empty(self, servicer, mock_context, sample_list_request):
        """Test document listing with no results."""
        # Mock document service
        mock_list_response = DocumentListResponse(
            documents=[],
            total_count=0,
            has_more=False,
            next_token=None,
        )
        
        with patch.object(servicer.document_service, 'list_documents', new_callable=AsyncMock) as mock_list:
            mock_list.return_value = mock_list_response
            
            # Execute list
            response = await servicer.ListDocuments(sample_list_request, mock_context)
            
            # Verify response
            assert len(response.documents) == 0
            assert response.total_count == 0
            assert response.has_more == False
    
    @pytest.mark.asyncio
    async def test_list_documents_validation_error(self, servicer, mock_context, sample_list_request):
        """Test list documents with validation error."""
        # Mock document service to raise ValueError
        with patch.object(servicer.document_service, 'list_documents', new_callable=AsyncMock) as mock_list:
            mock_list.side_effect = ValueError("Invalid request")
            
            # Execute list
            response = await servicer.ListDocuments(sample_list_request, mock_context)
            
            # Verify error response
            assert len(response.documents) == 0
            assert response.total_count == 0
            mock_context.set_code.assert_called_with(grpc.StatusCode.INVALID_ARGUMENT)
            mock_context.set_details.assert_called_with("Invalid request")


class TestGrpcServerIntegration:
    """Integration tests for gRPC server."""
    
    @pytest.mark.asyncio
    async def test_create_grpc_server(self):
        """Test gRPC server creation."""
        from app.api.grpc_server import create_grpc_server
        
        # Create server
        server = create_grpc_server()
        
        # Verify server is created
        assert server is not None
        assert isinstance(server, grpc.aio.Server)
        
        # Clean up
        await server.stop(0)