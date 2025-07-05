"""Tests for database models."""

import pytest
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, Mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.models.database import (
    Base,
    Document,
    DocumentVersion,
    StorageLocation,
    AuditLog,
    ScanResult,
    ThreatDetail,
    UploadSession,
)
from app.models.document import (
    DocumentStatus,
    StorageBackend,
    ScanStatus,
    ScanResultType,
    ThreatSeverity,
)


class TestDatabaseModels:
    """Test database models."""

    @pytest.fixture
    def sample_document_data(self):
        """Sample document data for testing."""
        return {
            "id": uuid.uuid4(),
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "size_bytes": 1024,
            "checksum": "abc123",
            "owner_id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "title": "Test Document",
            "description": "A test document",
            "tags": ["test", "document"],
            "attributes": {"category": "test"},
            "status": DocumentStatus.ACTIVE,
            "version": 1,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

    @pytest.fixture
    def sample_storage_location_data(self):
        """Sample storage location data for testing."""
        return {
            "id": uuid.uuid4(),
            "document_id": uuid.uuid4(),
            "backend": StorageBackend.S3,
            "bucket": "test-bucket",
            "key": "test/file.pdf",
            "region": "us-east-1",
            "endpoint_url": None,
            "is_primary": True,
            "created_at": datetime.utcnow(),
        }

    @pytest.fixture
    def sample_document_version_data(self):
        """Sample document version data for testing."""
        return {
            "id": uuid.uuid4(),
            "document_id": uuid.uuid4(),
            "version": 1,
            "description": "Initial version",
            "size_bytes": 1024,
            "checksum": "abc123",
            "backend": StorageBackend.S3,
            "bucket": "test-bucket",
            "key": "test/file.pdf",
            "region": "us-east-1",
            "endpoint_url": None,
            "created_by": uuid.uuid4(),
            "created_at": datetime.utcnow(),
        }

    @pytest.fixture
    def sample_audit_log_data(self):
        """Sample audit log data for testing."""
        return {
            "id": uuid.uuid4(),
            "document_id": uuid.uuid4(),
            "action": "upload",
            "user_id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "request_id": "req-123",
            "ip_address": "127.0.0.1",
            "user_agent": "test-agent",
            "status": "success",
            "error_message": None,
            "audit_metadata": {"test": "data"},
            "created_at": datetime.utcnow(),
        }

    @pytest.fixture
    def sample_scan_result_data(self):
        """Sample scan result data for testing."""
        return {
            "id": uuid.uuid4(),
            "document_id": uuid.uuid4(),
            "scan_id": "scan-123",
            "status": ScanStatus.COMPLETED,
            "result": ScanResultType.CLEAN,
            "scanner_version": "1.0.0",
            "duration_ms": 1000,
            "started_at": datetime.utcnow(),
            "completed_at": datetime.utcnow(),
        }

    @pytest.fixture
    def sample_threat_detail_data(self):
        """Sample threat detail data for testing."""
        return {
            "id": uuid.uuid4(),
            "scan_result_id": uuid.uuid4(),
            "name": "TestThreat",
            "type": "malware",
            "severity": ThreatSeverity.HIGH,
            "description": "Test threat description",
            "created_at": datetime.utcnow(),
        }

    @pytest.fixture
    def sample_upload_session_data(self):
        """Sample upload session data for testing."""
        return {
            "id": uuid.uuid4(),
            "session_id": "session-123",
            "user_id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "expected_size": 1024,
            "uploaded_size": 0,
            "status": "pending",
            "error_message": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "expires_at": datetime.utcnow(),
        }

    def test_document_model_creation(self, sample_document_data):
        """Test Document model creation."""
        document = Document(**sample_document_data)
        
        assert document.id == sample_document_data["id"]
        assert document.filename == sample_document_data["filename"]
        assert document.content_type == sample_document_data["content_type"]
        assert document.size_bytes == sample_document_data["size_bytes"]
        assert document.checksum == sample_document_data["checksum"]
        assert document.owner_id == sample_document_data["owner_id"]
        assert document.tenant_id == sample_document_data["tenant_id"]
        assert document.title == sample_document_data["title"]
        assert document.description == sample_document_data["description"]
        assert document.tags == sample_document_data["tags"]
        assert document.attributes == sample_document_data["attributes"]
        assert document.status == sample_document_data["status"]
        assert document.version == sample_document_data["version"]
        assert document.created_at == sample_document_data["created_at"]
        assert document.updated_at == sample_document_data["updated_at"]

    def test_document_model_defaults(self):
        """Test Document model with default values."""
        # Test the Column default values directly from the model
        assert Document.__table__.columns['tags'].default.arg == []
        assert Document.__table__.columns['attributes'].default.arg == {}
        assert Document.__table__.columns['status'].default.arg == DocumentStatus.ACTIVE
        assert Document.__table__.columns['version'].default.arg == 1
        
        # Test creating a document with only required fields
        document = Document(
            id=uuid.uuid4(),
            filename="test.pdf",
            content_type="application/pdf",
            size_bytes=1024,
            checksum="abc123",
            owner_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
        )
        
        # These fields should be None until the object is persisted to DB
        assert document.title is None
        assert document.description is None

    def test_storage_location_model_creation(self, sample_storage_location_data):
        """Test StorageLocation model creation."""
        storage_location = StorageLocation(**sample_storage_location_data)
        
        assert storage_location.id == sample_storage_location_data["id"]
        assert storage_location.document_id == sample_storage_location_data["document_id"]
        assert storage_location.backend == sample_storage_location_data["backend"]
        assert storage_location.bucket == sample_storage_location_data["bucket"]
        assert storage_location.key == sample_storage_location_data["key"]
        assert storage_location.region == sample_storage_location_data["region"]
        assert storage_location.endpoint_url == sample_storage_location_data["endpoint_url"]
        assert storage_location.is_primary == sample_storage_location_data["is_primary"]
        assert storage_location.created_at == sample_storage_location_data["created_at"]

    def test_storage_location_model_defaults(self):
        """Test StorageLocation model with default values."""
        # Test the Column default values directly from the model
        assert StorageLocation.__table__.columns['is_primary'].default.arg is True
        
        storage_location = StorageLocation(
            id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            backend=StorageBackend.S3,
            bucket="test-bucket",
            key="test/file.pdf",
            region="us-east-1",
        )
        
        assert storage_location.endpoint_url is None

    def test_document_version_model_creation(self, sample_document_version_data):
        """Test DocumentVersion model creation."""
        document_version = DocumentVersion(**sample_document_version_data)
        
        assert document_version.id == sample_document_version_data["id"]
        assert document_version.document_id == sample_document_version_data["document_id"]
        assert document_version.version == sample_document_version_data["version"]
        assert document_version.description == sample_document_version_data["description"]
        assert document_version.size_bytes == sample_document_version_data["size_bytes"]
        assert document_version.checksum == sample_document_version_data["checksum"]
        assert document_version.backend == sample_document_version_data["backend"]
        assert document_version.bucket == sample_document_version_data["bucket"]
        assert document_version.key == sample_document_version_data["key"]
        assert document_version.region == sample_document_version_data["region"]
        assert document_version.endpoint_url == sample_document_version_data["endpoint_url"]
        assert document_version.created_by == sample_document_version_data["created_by"]
        assert document_version.created_at == sample_document_version_data["created_at"]

    def test_audit_log_model_creation(self, sample_audit_log_data):
        """Test AuditLog model creation."""
        audit_log = AuditLog(**sample_audit_log_data)
        
        assert audit_log.id == sample_audit_log_data["id"]
        assert audit_log.document_id == sample_audit_log_data["document_id"]
        assert audit_log.action == sample_audit_log_data["action"]
        assert audit_log.user_id == sample_audit_log_data["user_id"]
        assert audit_log.tenant_id == sample_audit_log_data["tenant_id"]
        assert audit_log.request_id == sample_audit_log_data["request_id"]
        assert audit_log.ip_address == sample_audit_log_data["ip_address"]
        assert audit_log.user_agent == sample_audit_log_data["user_agent"]
        assert audit_log.status == sample_audit_log_data["status"]
        assert audit_log.error_message == sample_audit_log_data["error_message"]
        assert audit_log.audit_metadata == sample_audit_log_data["audit_metadata"]
        assert audit_log.created_at == sample_audit_log_data["created_at"]

    def test_audit_log_model_defaults(self):
        """Test AuditLog model with default values."""
        # Test the Column default values directly from the model
        assert AuditLog.__table__.columns['audit_metadata'].default.arg == {}
        
        audit_log = AuditLog(
            id=uuid.uuid4(),
            action="upload",
            user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            status="success",
        )
        
        assert audit_log.document_id is None
        assert audit_log.request_id is None
        assert audit_log.ip_address is None
        assert audit_log.user_agent is None
        assert audit_log.error_message is None

    def test_scan_result_model_creation(self, sample_scan_result_data):
        """Test ScanResult model creation."""
        scan_result = ScanResult(**sample_scan_result_data)
        
        assert scan_result.id == sample_scan_result_data["id"]
        assert scan_result.document_id == sample_scan_result_data["document_id"]
        assert scan_result.scan_id == sample_scan_result_data["scan_id"]
        assert scan_result.status == sample_scan_result_data["status"]
        assert scan_result.result == sample_scan_result_data["result"]
        assert scan_result.scanner_version == sample_scan_result_data["scanner_version"]
        assert scan_result.duration_ms == sample_scan_result_data["duration_ms"]
        assert scan_result.started_at == sample_scan_result_data["started_at"]
        assert scan_result.completed_at == sample_scan_result_data["completed_at"]

    def test_threat_detail_model_creation(self, sample_threat_detail_data):
        """Test ThreatDetail model creation."""
        threat_detail = ThreatDetail(**sample_threat_detail_data)
        
        assert threat_detail.id == sample_threat_detail_data["id"]
        assert threat_detail.scan_result_id == sample_threat_detail_data["scan_result_id"]
        assert threat_detail.name == sample_threat_detail_data["name"]
        assert threat_detail.type == sample_threat_detail_data["type"]
        assert threat_detail.severity == sample_threat_detail_data["severity"]
        assert threat_detail.description == sample_threat_detail_data["description"]
        assert threat_detail.created_at == sample_threat_detail_data["created_at"]

    def test_upload_session_model_creation(self, sample_upload_session_data):
        """Test UploadSession model creation."""
        upload_session = UploadSession(**sample_upload_session_data)
        
        assert upload_session.id == sample_upload_session_data["id"]
        assert upload_session.session_id == sample_upload_session_data["session_id"]
        assert upload_session.user_id == sample_upload_session_data["user_id"]
        assert upload_session.tenant_id == sample_upload_session_data["tenant_id"]
        assert upload_session.filename == sample_upload_session_data["filename"]
        assert upload_session.content_type == sample_upload_session_data["content_type"]
        assert upload_session.expected_size == sample_upload_session_data["expected_size"]
        assert upload_session.uploaded_size == sample_upload_session_data["uploaded_size"]
        assert upload_session.status == sample_upload_session_data["status"]
        assert upload_session.error_message == sample_upload_session_data["error_message"]
        assert upload_session.created_at == sample_upload_session_data["created_at"]
        assert upload_session.updated_at == sample_upload_session_data["updated_at"]
        assert upload_session.expires_at == sample_upload_session_data["expires_at"]

    def test_upload_session_model_defaults(self):
        """Test UploadSession model with default values."""
        # Test the Column default values directly from the model
        assert UploadSession.__table__.columns['uploaded_size'].default.arg == 0
        assert UploadSession.__table__.columns['status'].default.arg == "pending"
        
        upload_session = UploadSession(
            id=uuid.uuid4(),
            session_id="session-123",
            user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            filename="test.pdf",
            content_type="application/pdf",
            expires_at=datetime.utcnow(),
        )
        
        assert upload_session.expected_size is None
        assert upload_session.error_message is None

    def test_document_relationships(self):
        """Test Document model relationships."""
        # Check that relationships are properly configured on the class
        assert hasattr(Document, 'storage_locations')
        assert hasattr(Document, 'versions')
        assert hasattr(Document, 'audit_logs')
        assert hasattr(Document, 'scan_results')
        
        # Check relationship back-references
        assert Document.storage_locations.property.back_populates == 'document'
        assert Document.versions.property.back_populates == 'document'
        assert Document.audit_logs.property.back_populates == 'document'
        assert Document.scan_results.property.back_populates == 'document'

    def test_scan_result_relationships(self):
        """Test ScanResult model relationships."""
        # Check that relationships are properly configured on the class
        assert hasattr(ScanResult, 'document')
        assert hasattr(ScanResult, 'threats')
        
        # Check relationship back-references
        assert ScanResult.document.property.back_populates == 'scan_results'
        assert ScanResult.threats.property.back_populates == 'scan_result'

    def test_model_table_names(self):
        """Test that all models have correct table names."""
        assert Document.__tablename__ == "documents"
        assert StorageLocation.__tablename__ == "storage_locations"
        assert DocumentVersion.__tablename__ == "document_versions"
        assert AuditLog.__tablename__ == "audit_logs"
        assert ScanResult.__tablename__ == "scan_results"
        assert ThreatDetail.__tablename__ == "threat_details"
        assert UploadSession.__tablename__ == "upload_sessions"

    def test_model_indexes(self):
        """Test that all models have required indexes."""
        # Check Document indexes
        document_indexes = [idx.name for idx in Document.__table__.indexes]
        assert "idx_documents_owner_tenant" in document_indexes
        assert "idx_documents_status" in document_indexes
        assert "idx_documents_created_at" in document_indexes
        assert "idx_documents_tags" in document_indexes
        
        # Check StorageLocation indexes
        storage_indexes = [idx.name for idx in StorageLocation.__table__.indexes]
        assert "idx_storage_locations_document" in storage_indexes
        assert "idx_storage_locations_backend" in storage_indexes
        
        # Check DocumentVersion indexes
        version_indexes = [idx.name for idx in DocumentVersion.__table__.indexes]
        assert "idx_document_versions_document" in version_indexes
        assert "idx_document_versions_version" in version_indexes
        assert "idx_document_versions_created_at" in version_indexes
        
        # Check AuditLog indexes
        audit_indexes = [idx.name for idx in AuditLog.__table__.indexes]
        assert "idx_audit_logs_document" in audit_indexes
        assert "idx_audit_logs_user_tenant" in audit_indexes
        assert "idx_audit_logs_action" in audit_indexes
        assert "idx_audit_logs_created_at" in audit_indexes
        
        # Check ScanResult indexes
        scan_indexes = [idx.name for idx in ScanResult.__table__.indexes]
        assert "idx_scan_results_document" in scan_indexes
        assert "idx_scan_results_scan_id" in scan_indexes
        assert "idx_scan_results_status" in scan_indexes
        assert "idx_scan_results_started_at" in scan_indexes
        
        # Check ThreatDetail indexes
        threat_indexes = [idx.name for idx in ThreatDetail.__table__.indexes]
        assert "idx_threat_details_scan_result" in threat_indexes
        assert "idx_threat_details_severity" in threat_indexes
        
        # Check UploadSession indexes
        upload_indexes = [idx.name for idx in UploadSession.__table__.indexes]
        assert "idx_upload_sessions_session_id" in upload_indexes
        assert "idx_upload_sessions_user_tenant" in upload_indexes
        assert "idx_upload_sessions_status" in upload_indexes
        assert "idx_upload_sessions_expires_at" in upload_indexes