"""Integration tests for document workflows."""

import uuid
from io import BytesIO
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt_utils import jwt_manager
from app.main import create_app
from app.models.document import (
    DocumentStatus,
    UploadStatus,
    ScanResultType,
    ScanStatus,
)


class TestDocumentWorkflow:
    """Integration tests for document workflows."""
    
    @pytest.fixture
    def app(self):
        """Create test app."""
        return create_app()
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def user_data(self):
        """Create test user data."""
        return {
            "user_id": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "scopes": ["doc.read", "doc.write", "doc.admin"],
        }
    
    @pytest.fixture
    def auth_headers(self, user_data):
        """Create authentication headers."""
        token = jwt_manager.create_access_token(
            user_id=user_data["user_id"],
            tenant_id=user_data["tenant_id"],
            scopes=user_data["scopes"],
        )
        return {"Authorization": f"Bearer {token}"}
    
    @pytest.mark.asyncio
    async def test_complete_document_lifecycle(self, client, auth_headers, user_data):
        """Test complete document lifecycle: upload -> get -> scan -> delete."""
        file_content = b"Test PDF content for integration test"
        file_data = BytesIO(file_content)
        document_id = str(uuid.uuid4())
        
        # Mock all external dependencies
        mock_upload_response = Mock()
        mock_upload_response.document_id = document_id
        mock_upload_response.status = UploadStatus.COMPLETED
        mock_upload_response.size_bytes = len(file_content)
        mock_upload_response.checksum = "test-checksum"
        mock_upload_response.uploaded_at = "2023-01-01T00:00:00"
        mock_upload_response.location = Mock()
        mock_upload_response.location.backend = "s3"
        mock_upload_response.location.bucket = "test-bucket"
        mock_upload_response.location.key = "test-key"
        mock_upload_response.location.region = "us-east-1"
        mock_upload_response.location.endpoint_url = None
        
        mock_document_response = Mock()
        mock_document_response.metadata = Mock()
        mock_document_response.metadata.document_id = document_id
        mock_document_response.metadata.filename = "test.pdf"
        mock_document_response.metadata.content_type = "application/pdf"
        mock_document_response.metadata.size_bytes = len(file_content)
        mock_document_response.metadata.owner_id = user_data["user_id"]
        mock_document_response.metadata.tenant_id = user_data["tenant_id"]
        mock_document_response.metadata.status = DocumentStatus.ACTIVE
        mock_document_response.location = mock_upload_response.location
        mock_document_response.versions = []
        mock_document_response.last_scan = None
        
        mock_scan_result = Mock()
        mock_scan_result.scan_id = str(uuid.uuid4())
        mock_scan_result.document_id = document_id
        mock_scan_result.status = ScanStatus.COMPLETED
        mock_scan_result.result = ScanResultType.CLEAN
        mock_scan_result.duration_ms = 500
        mock_scan_result.threats = []
        
        with patch("app.api.rest_routes.document_service.upload_document") as mock_upload:
            mock_upload.return_value = mock_upload_response
            
            with patch("app.api.rest_routes.event_publisher.publish_document_uploaded") as mock_pub_upload:
                mock_pub_upload.return_value = True
                
                # Step 1: Upload document
                upload_response = client.post(
                    "/api/v1/documents/upload",
                    headers=auth_headers,
                    files={
                        "file": ("test.pdf", file_data, "application/pdf")
                    },
                    data={
                        "title": "Integration Test Document",
                        "description": "A document for integration testing",
                        "tags": "test,integration",
                    },
                )
                
                assert upload_response.status_code == 200
                upload_data = upload_response.json()
                assert upload_data["document_id"] == document_id
                assert upload_data["status"] == "completed"
        
        with patch("app.api.rest_routes.document_service.get_document") as mock_get:
            mock_get.return_value = mock_document_response
            
            # Step 2: Get document
            get_response = client.get(
                f"/api/v1/documents/{document_id}",
                headers=auth_headers,
            )
            
            assert get_response.status_code == 200
            get_data = get_response.json()
            assert get_data["metadata"]["document_id"] == document_id
            assert get_data["metadata"]["filename"] == "test.pdf"
        
        with patch("app.api.rest_routes.document_service.get_document") as mock_get_scan:
            mock_get_scan.return_value = mock_document_response
            
            with patch("app.api.rest_routes.storage_backend.download_file") as mock_download:
                mock_download.return_value = file_content
                
                with patch("app.api.rest_routes.virus_scanner.scan_bytes") as mock_scan:
                    mock_scan.return_value = mock_scan_result
                    
                    with patch("app.api.rest_routes.event_publisher.publish_document_scanned") as mock_pub_scan:
                        mock_pub_scan.return_value = True
                        
                        # Step 3: Scan document
                        scan_response = client.post(
                            f"/api/v1/documents/{document_id}/scan",
                            headers=auth_headers,
                        )
                        
                        assert scan_response.status_code == 200
                        scan_data = scan_response.json()
                        assert "scan completed" in scan_data["message"]
                        assert scan_data["result"] == "clean"
        
        with patch("app.api.rest_routes.document_service.get_document") as mock_get_del:
            mock_get_del.return_value = mock_document_response
            
            with patch("app.api.rest_routes.document_service.delete_document") as mock_delete:
                mock_delete.return_value = True
                
                with patch("app.api.rest_routes.event_publisher.publish_document_deleted") as mock_pub_del:
                    mock_pub_del.return_value = True
                    
                    # Step 4: Delete document
                    delete_response = client.delete(
                        f"/api/v1/documents/{document_id}",
                        headers=auth_headers,
                    )
                    
                    assert delete_response.status_code == 200
                    delete_data = delete_response.json()
                    assert "deleted successfully" in delete_data["message"]
    
    @pytest.mark.asyncio
    async def test_document_upload_and_download_workflow(self, client, auth_headers, user_data):
        """Test document upload and download workflow."""
        file_content = b"Test content for download"
        file_data = BytesIO(file_content)
        document_id = str(uuid.uuid4())
        
        # Mock upload
        mock_upload_response = Mock()
        mock_upload_response.document_id = document_id
        mock_upload_response.status = UploadStatus.COMPLETED
        mock_upload_response.size_bytes = len(file_content)
        mock_upload_response.checksum = "test-checksum"
        mock_upload_response.uploaded_at = "2023-01-01T00:00:00"
        mock_upload_response.location = Mock()
        mock_upload_response.location.backend = "s3"
        mock_upload_response.location.bucket = "test-bucket"
        mock_upload_response.location.key = "test-key"
        mock_upload_response.location.region = "us-east-1"
        
        # Mock document response
        mock_document_response = Mock()
        mock_document_response.metadata = Mock()
        mock_document_response.metadata.document_id = document_id
        mock_document_response.metadata.filename = "download-test.pdf"
        mock_document_response.metadata.content_type = "application/pdf"
        mock_document_response.metadata.size_bytes = len(file_content)
        mock_document_response.metadata.owner_id = user_data["user_id"]
        mock_document_response.metadata.tenant_id = user_data["tenant_id"]
        mock_document_response.location = mock_upload_response.location
        
        with patch("app.api.rest_routes.document_service.upload_document") as mock_upload:
            mock_upload.return_value = mock_upload_response
            
            with patch("app.api.rest_routes.event_publisher.publish_document_uploaded") as mock_pub:
                mock_pub.return_value = True
                
                # Upload document
                upload_response = client.post(
                    "/api/v1/documents/upload",
                    headers=auth_headers,
                    files={
                        "file": ("download-test.pdf", file_data, "application/pdf")
                    },
                )
                
                assert upload_response.status_code == 200
        
        with patch("app.api.rest_routes.document_service.get_document") as mock_get:
            mock_get.return_value = mock_document_response
            
            with patch("app.api.rest_routes.storage_backend.download_file") as mock_download:
                mock_download.return_value = file_content
                
                # Download document
                download_response = client.get(
                    f"/api/v1/documents/{document_id}/download",
                    headers=auth_headers,
                )
                
                assert download_response.status_code == 200
                assert download_response.content == file_content
                assert "attachment" in download_response.headers["content-disposition"]
    
    @pytest.mark.asyncio
    async def test_document_list_workflow(self, client, auth_headers, user_data):
        """Test document listing workflow."""
        # Mock document metadata
        mock_documents = []
        for i in range(3):
            doc = Mock()
            doc.dict.return_value = {
                "document_id": str(uuid.uuid4()),
                "filename": f"test-{i}.pdf",
                "content_type": "application/pdf",
                "size_bytes": 1024,
                "owner_id": user_data["user_id"],
                "tenant_id": user_data["tenant_id"],
                "tags": ["test"],
                "title": f"Test Document {i}",
                "description": f"Test document {i}",
                "created_at": "2023-01-01T00:00:00",
                "updated_at": "2023-01-01T00:00:00",
                "version": 1,
                "status": "active",
                "checksum": f"checksum-{i}",
                "attributes": {},
            }
            mock_documents.append(doc)
        
        mock_list_response = Mock()
        mock_list_response.documents = mock_documents
        mock_list_response.total_count = len(mock_documents)
        mock_list_response.has_more = False
        mock_list_response.next_token = None
        
        with patch("app.api.rest_routes.document_service.list_documents") as mock_list:
            mock_list.return_value = mock_list_response
            
            # List documents
            list_response = client.get(
                "/api/v1/documents",
                headers=auth_headers,
                params={
                    "limit": 10,
                    "offset": 0,
                    "sort_by": "created_at",
                    "sort_order": "desc",
                },
            )
            
            assert list_response.status_code == 200
            list_data = list_response.json()
            assert len(list_data["documents"]) == 3
            assert list_data["total_count"] == 3
            assert list_data["has_more"] is False
    
    @pytest.mark.asyncio
    async def test_authentication_workflow(self, client, user_data):
        """Test authentication workflow with different permission levels."""
        # Test with read-only user
        read_token = jwt_manager.create_access_token(
            user_id=user_data["user_id"],
            tenant_id=user_data["tenant_id"],
            scopes=["doc.read"],
        )
        read_headers = {"Authorization": f"Bearer {read_token}"}
        
        # Test with write user
        write_token = jwt_manager.create_access_token(
            user_id=user_data["user_id"],
            tenant_id=user_data["tenant_id"],
            scopes=["doc.read", "doc.write"],
        )
        write_headers = {"Authorization": f"Bearer {write_token}"}
        
        # Test with admin user
        admin_token = jwt_manager.create_access_token(
            user_id=user_data["user_id"],
            tenant_id=user_data["tenant_id"],
            scopes=["doc.read", "doc.write", "doc.admin"],
        )
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        
        document_id = str(uuid.uuid4())
        
        # Mock document response for GET requests
        mock_document_response = Mock()
        mock_document_response.metadata = Mock()
        mock_document_response.metadata.document_id = document_id
        mock_document_response.metadata.filename = "test.pdf"
        mock_document_response.location = Mock()
        mock_document_response.versions = []
        mock_document_response.last_scan = None
        
        # Read-only user can GET documents
        with patch("app.api.rest_routes.document_service.get_document") as mock_get:
            mock_get.return_value = mock_document_response
            
            response = client.get(
                f"/api/v1/documents/{document_id}",
                headers=read_headers,
            )
            assert response.status_code == 200
        
        # Read-only user cannot upload documents
        response = client.post(
            "/api/v1/documents/upload",
            headers=read_headers,
            files={
                "file": ("test.pdf", BytesIO(b"content"), "application/pdf")
            },
        )
        assert response.status_code == 403
        
        # Write user can upload documents
        mock_upload_response = Mock()
        mock_upload_response.document_id = document_id
        mock_upload_response.status = UploadStatus.COMPLETED
        mock_upload_response.size_bytes = 7
        mock_upload_response.checksum = "test"
        mock_upload_response.uploaded_at = "2023-01-01T00:00:00"
        mock_upload_response.location = Mock()
        mock_upload_response.location.backend = "s3"
        
        with patch("app.api.rest_routes.document_service.upload_document") as mock_upload:
            mock_upload.return_value = mock_upload_response
            
            with patch("app.api.rest_routes.event_publisher.publish_document_uploaded") as mock_pub:
                mock_pub.return_value = True
                
                response = client.post(
                    "/api/v1/documents/upload",
                    headers=write_headers,
                    files={
                        "file": ("test.pdf", BytesIO(b"content"), "application/pdf")
                    },
                )
                assert response.status_code == 200
        
        # Write user cannot scan documents (requires admin)
        response = client.post(
            f"/api/v1/documents/{document_id}/scan",
            headers=write_headers,
        )
        assert response.status_code == 403
        
        # Admin user can scan documents
        mock_scan_result = Mock()
        mock_scan_result.scan_id = str(uuid.uuid4())
        mock_scan_result.result = ScanResultType.CLEAN
        mock_scan_result.duration_ms = 500
        mock_scan_result.threats = []
        
        with patch("app.api.rest_routes.document_service.get_document") as mock_get_scan:
            mock_get_scan.return_value = mock_document_response
            
            with patch("app.api.rest_routes.storage_backend.download_file") as mock_download:
                mock_download.return_value = b"content"
                
                with patch("app.api.rest_routes.virus_scanner.scan_bytes") as mock_scan:
                    mock_scan.return_value = mock_scan_result
                    
                    with patch("app.api.rest_routes.event_publisher.publish_document_scanned") as mock_pub_scan:
                        mock_pub_scan.return_value = True
                        
                        response = client.post(
                            f"/api/v1/documents/{document_id}/scan",
                            headers=admin_headers,
                        )
                        assert response.status_code == 200
    
    def test_health_check_workflow(self, client):
        """Test health check workflow."""
        with patch("app.api.rest_routes.virus_scanner.health_check", return_value=True):
            with patch("app.api.rest_routes.event_publisher.health_check", return_value=True):
                with patch("app.api.rest_routes.storage_backend.health_check", return_value=True):
                    response = client.get("/api/v1/health")
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert data["status"] == "healthy"
                    assert data["service"] == "document-service"
                    assert "dependencies" in data
                    assert data["dependencies"]["virus_scanner"] == "healthy"
                    assert data["dependencies"]["event_publisher"] == "healthy"
                    assert data["dependencies"]["storage_backend"] == "healthy"
    
    def test_error_handling_workflow(self, client, auth_headers):
        """Test error handling workflow."""
        document_id = str(uuid.uuid4())
        
        # Test 404 error
        with patch("app.api.rest_routes.document_service.get_document") as mock_get:
            mock_get.side_effect = ValueError("Document not found")
            
            response = client.get(
                f"/api/v1/documents/{document_id}",
                headers=auth_headers,
            )
            
            assert response.status_code == 404
            data = response.json()
            assert "Document not found" in data["detail"]
        
        # Test 403 error
        with patch("app.api.rest_routes.document_service.get_document") as mock_get:
            mock_get.side_effect = PermissionError("Access denied")
            
            response = client.get(
                f"/api/v1/documents/{document_id}",
                headers=auth_headers,
            )
            
            assert response.status_code == 403
            data = response.json()
            assert "Access denied" in data["detail"]
        
        # Test 500 error
        with patch("app.api.rest_routes.document_service.get_document") as mock_get:
            mock_get.side_effect = Exception("Internal error")
            
            response = client.get(
                f"/api/v1/documents/{document_id}",
                headers=auth_headers,
            )
            
            assert response.status_code == 500
            data = response.json()
            assert "Internal server error" in data["detail"]
