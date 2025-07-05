"""Unit tests for REST API routes."""

import json
import uuid
from datetime import datetime
from io import BytesIO
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.auth.jwt_utils import jwt_manager
from app.main import create_app
from app.models.document import (
    DocumentStatus,
    DocumentMetadata,
    DocumentResponse,
    UploadResponse,
    UploadStatus,
    StorageLocation,
    StorageBackend,
    ScanResult,
    ScanStatus,
    ScanResultType,
)


class TestRestRoutes:
    """Test REST API routes."""
    
    @pytest.fixture
    def app(self):
        """Create test app."""
        return create_app()
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def auth_headers(self):
        """Create authentication headers."""
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        token = jwt_manager.create_access_token(
            user_id=user_id,
            tenant_id=tenant_id,
            scopes=["doc.read", "doc.write", "doc.admin"],
        )
        return {"Authorization": f"Bearer {token}"}
    
    @pytest.fixture
    def sample_document_metadata(self):
        """Create sample document metadata."""
        return DocumentMetadata(
            document_id=str(uuid.uuid4()),
            filename="test.pdf",
            content_type="application/pdf",
            size_bytes=1024,
            owner_id=str(uuid.uuid4()),
            tenant_id=str(uuid.uuid4()),
            tags=["test", "document"],
            title="Test Document",
            description="A test document",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            version=1,
            status=DocumentStatus.ACTIVE,
            checksum="abc123",
            attributes={"category": "test"},
        )
    
    @pytest.fixture
    def sample_storage_location(self):
        """Create sample storage location."""
        return StorageLocation(
            backend=StorageBackend.S3,
            bucket="test-bucket",
            key="test-key",
            region="us-east-1",
            endpoint_url=None,
        )
    
    def test_health_check(self, client):
        """Test health check endpoint."""
        with patch("app.api.rest_routes.virus_scanner.health_check", return_value=True):
            with patch("app.api.rest_routes.event_publisher.health_check", return_value=True):
                with patch("app.api.rest_routes.storage_backend.health_check", return_value=True):
                    response = client.get("/api/v1/health")
                    
                    assert response.status_code == status.HTTP_200_OK
                    data = response.json()
                    assert data["status"] == "healthy"
                    assert data["service"] == "document-service"
                    assert data["version"] == "0.1.0"
                    assert "timestamp" in data
                    assert "dependencies" in data
    
    def test_metrics(self, client):
        """Test metrics endpoint."""
        response = client.get("/api/v1/metrics")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["service"] == "document-service"
        assert "metrics" in data
        assert "timestamp" in data
    
    def test_upload_document_success(self, client, auth_headers):
        """Test successful document upload."""
        file_content = b"Test PDF content"
        file_data = BytesIO(file_content)
        
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
            size_bytes=len(file_content),
            checksum="abc123",
        )
        
        with patch("app.api.rest_routes.document_service.upload_document") as mock_upload:
            mock_upload.return_value = mock_upload_response
            
            with patch("app.api.rest_routes.event_publisher.publish_document_uploaded") as mock_publish:
                mock_publish.return_value = True
                
                response = client.post(
                    "/api/v1/documents/upload",
                    headers=auth_headers,
                    files={
                        "file": ("test.pdf", file_data, "application/pdf")
                    },
                    data={
                        "title": "Test Document",
                        "description": "A test document",
                        "tags": "test,document",
                    },
                )
                
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["status"] == "completed"
                assert data["size_bytes"] == len(file_content)
                assert "document_id" in data
    
    def test_upload_document_file_too_large(self, client, auth_headers):
        """Test document upload with file too large."""
        # Create a large file content that exceeds the limit
        large_content = b"x" * (21 * 1024 * 1024)  # 21MB
        file_data = BytesIO(large_content)
        
        response = client.post(
            "/api/v1/documents/upload",
            headers=auth_headers,
            files={
                "file": ("large.pdf", file_data, "application/pdf")
            },
        )
        
        assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
        data = response.json()
        assert "File size exceeds maximum" in data["detail"]
    
    def test_upload_document_invalid_file_type(self, client, auth_headers):
        """Test document upload with invalid file type."""
        file_content = b"Test content"
        file_data = BytesIO(file_content)
        
        response = client.post(
            "/api/v1/documents/upload",
            headers=auth_headers,
            files={
                "file": ("test.exe", file_data, "application/octet-stream")
            },
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "File type 'exe' not allowed" in data["detail"]
    
    def test_upload_document_no_auth(self, client):
        """Test document upload without authentication."""
        file_content = b"Test content"
        file_data = BytesIO(file_content)
        
        response = client.post(
            "/api/v1/documents/upload",
            files={
                "file": ("test.pdf", file_data, "application/pdf")
            },
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_get_document_success(self, client, auth_headers, sample_document_metadata, sample_storage_location):
        """Test successful document retrieval."""
        document_id = sample_document_metadata.document_id
        
        mock_document_response = DocumentResponse(
            metadata=sample_document_metadata,
            location=sample_storage_location,
            versions=[],
            last_scan=None,
        )
        
        with patch("app.api.rest_routes.document_service.get_document") as mock_get:
            mock_get.return_value = mock_document_response
            
            response = client.get(
                f"/api/v1/documents/{document_id}",
                headers=auth_headers,
            )
            
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["metadata"]["document_id"] == document_id
            assert data["metadata"]["filename"] == "test.pdf"
            assert data["location"]["backend"] == "s3"
    
    def test_get_document_not_found(self, client, auth_headers):
        """Test document retrieval when document not found."""
        document_id = str(uuid.uuid4())
        
        with patch("app.api.rest_routes.document_service.get_document") as mock_get:
            mock_get.side_effect = ValueError("Document not found")
            
            response = client.get(
                f"/api/v1/documents/{document_id}",
                headers=auth_headers,
            )
            
            assert response.status_code == status.HTTP_404_NOT_FOUND
            data = response.json()
            assert "Document not found" in data["detail"]
    
    def test_get_document_permission_denied(self, client, auth_headers):
        """Test document retrieval with permission denied."""
        document_id = str(uuid.uuid4())
        
        with patch("app.api.rest_routes.document_service.get_document") as mock_get:
            mock_get.side_effect = PermissionError("Access denied")
            
            response = client.get(
                f"/api/v1/documents/{document_id}",
                headers=auth_headers,
            )
            
            assert response.status_code == status.HTTP_403_FORBIDDEN
            data = response.json()
            assert "Access denied" in data["detail"]
    
    def test_download_document_success(self, client, auth_headers, sample_document_metadata, sample_storage_location):
        """Test successful document download."""
        document_id = sample_document_metadata.document_id
        file_content = b"Test PDF content"
        
        mock_document_response = DocumentResponse(
            metadata=sample_document_metadata,
            location=sample_storage_location,
            versions=[],
            last_scan=None,
        )
        
        with patch("app.api.rest_routes.document_service.get_document") as mock_get:
            mock_get.return_value = mock_document_response
            
            with patch("app.api.rest_routes.storage_backend.download_file") as mock_download:
                mock_download.return_value = file_content
                
                response = client.get(
                    f"/api/v1/documents/{document_id}/download",
                    headers=auth_headers,
                )
                
                assert response.status_code == status.HTTP_200_OK
                assert response.content == file_content
                assert response.headers["content-type"] == "application/pdf"
                assert "attachment" in response.headers["content-disposition"]
    
    def test_delete_document_success(self, client, auth_headers, sample_document_metadata, sample_storage_location):
        """Test successful document deletion."""
        document_id = sample_document_metadata.document_id
        
        mock_document_response = DocumentResponse(
            metadata=sample_document_metadata,
            location=sample_storage_location,
            versions=[],
            last_scan=None,
        )
        
        with patch("app.api.rest_routes.document_service.get_document") as mock_get:
            mock_get.return_value = mock_document_response
            
            with patch("app.api.rest_routes.document_service.delete_document") as mock_delete:
                mock_delete.return_value = True
                
                with patch("app.api.rest_routes.event_publisher.publish_document_deleted") as mock_publish:
                    mock_publish.return_value = True
                    
                    response = client.delete(
                        f"/api/v1/documents/{document_id}",
                        headers=auth_headers,
                    )
                    
                    assert response.status_code == status.HTTP_200_OK
                    data = response.json()
                    assert "deleted successfully" in data["message"]
    
    def test_list_documents_success(self, client, auth_headers, sample_document_metadata):
        """Test successful document listing."""
        mock_list_response = {
            "documents": [sample_document_metadata.dict()],
            "total_count": 1,
            "has_more": False,
            "next_token": None,
        }
        
        with patch("app.api.rest_routes.document_service.list_documents") as mock_list:
            mock_list.return_value = Mock(**mock_list_response)
            
            response = client.get(
                "/api/v1/documents",
                headers=auth_headers,
                params={
                    "limit": 10,
                    "offset": 0,
                    "sort_by": "created_at",
                    "sort_order": "desc",
                },
            )
            
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert len(data["documents"]) == 1
            assert data["total_count"] == 1
            assert data["has_more"] is False
    
    def test_scan_document_success(self, client, auth_headers, sample_document_metadata, sample_storage_location):
        """Test successful document scan."""
        document_id = sample_document_metadata.document_id
        file_content = b"Test PDF content"
        
        mock_document_response = DocumentResponse(
            metadata=sample_document_metadata,
            location=sample_storage_location,
            versions=[],
            last_scan=None,
        )
        
        mock_scan_result = ScanResult(
            scan_id=str(uuid.uuid4()),
            document_id=document_id,
            status=ScanStatus.COMPLETED,
            result=ScanResultType.CLEAN,
            scanned_at=datetime.utcnow(),
            duration_ms=500,
            threats=[],
            scanner_version="1.0.0",
        )
        
        with patch("app.api.rest_routes.document_service.get_document") as mock_get:
            mock_get.return_value = mock_document_response
            
            with patch("app.api.rest_routes.storage_backend.download_file") as mock_download:
                mock_download.return_value = file_content
                
                with patch("app.api.rest_routes.virus_scanner.scan_bytes") as mock_scan:
                    mock_scan.return_value = mock_scan_result
                    
                    with patch("app.api.rest_routes.event_publisher.publish_document_scanned") as mock_publish:
                        mock_publish.return_value = True
                        
                        response = client.post(
                            f"/api/v1/documents/{document_id}/scan",
                            headers=auth_headers,
                        )
                        
                        assert response.status_code == status.HTTP_200_OK
                        data = response.json()
                        assert "scan completed" in data["message"]
                        assert data["result"] == "clean"
                        assert data["duration_ms"] == 500
    
    def test_scan_document_infected(self, client, auth_headers, sample_document_metadata, sample_storage_location):
        """Test document scan with infected file."""
        document_id = sample_document_metadata.document_id
        file_content = b"Test virus content"
        
        mock_document_response = DocumentResponse(
            metadata=sample_document_metadata,
            location=sample_storage_location,
            versions=[],
            last_scan=None,
        )
        
        from app.models.document import ThreatDetail, ThreatSeverity
        
        mock_threat = ThreatDetail(
            name="Test.Virus",
            type="virus",
            severity=ThreatSeverity.HIGH,
            description="Test virus detected",
        )
        
        mock_scan_result = ScanResult(
            scan_id=str(uuid.uuid4()),
            document_id=document_id,
            status=ScanStatus.COMPLETED,
            result=ScanResultType.INFECTED,
            scanned_at=datetime.utcnow(),
            duration_ms=750,
            threats=[mock_threat],
            scanner_version="1.0.0",
        )
        
        with patch("app.api.rest_routes.document_service.get_document") as mock_get:
            mock_get.return_value = mock_document_response
            
            with patch("app.api.rest_routes.storage_backend.download_file") as mock_download:
                mock_download.return_value = file_content
                
                with patch("app.api.rest_routes.virus_scanner.scan_bytes") as mock_scan:
                    mock_scan.return_value = mock_scan_result
                    
                    with patch("app.api.rest_routes.event_publisher.publish_document_scanned") as mock_publish:
                        mock_publish.return_value = True
                        
                        response = client.post(
                            f"/api/v1/documents/{document_id}/scan",
                            headers=auth_headers,
                        )
                        
                        assert response.status_code == status.HTTP_200_OK
                        data = response.json()
                        assert data["result"] == "infected"
                        assert len(data["threats"]) == 1
                        assert data["threats"][0]["name"] == "Test.Virus"
    
    def test_endpoints_require_authentication(self, client):
        """Test that protected endpoints require authentication."""
        document_id = str(uuid.uuid4())
        
        # Test all protected endpoints
        endpoints = [
            ("POST", "/api/v1/documents/upload"),
            ("GET", f"/api/v1/documents/{document_id}"),
            ("DELETE", f"/api/v1/documents/{document_id}"),
            ("GET", "/api/v1/documents"),
            ("POST", f"/api/v1/documents/{document_id}/scan"),
        ]
        
        for method, endpoint in endpoints:
            response = client.request(method, endpoint)
            assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_insufficient_scopes(self, client):
        """Test endpoints with insufficient scopes."""
        # Create token with only read access
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        token = jwt_manager.create_access_token(
            user_id=user_id,
            tenant_id=tenant_id,
            scopes=["doc.read"],  # Only read access
        )
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test endpoints that require write access
        document_id = str(uuid.uuid4())
        
        # Upload requires write access
        response = client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={
                "file": ("test.pdf", BytesIO(b"content"), "application/pdf")
            },
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        
        # Delete requires write access
        response = client.delete(
            f"/api/v1/documents/{document_id}",
            headers=headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        
        # Scan requires admin access
        response = client.post(
            f"/api/v1/documents/{document_id}/scan",
            headers=headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
