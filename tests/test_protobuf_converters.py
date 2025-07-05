"""Tests for protobuf converter utilities."""

import pytest
import uuid
from datetime import datetime
from google.protobuf.timestamp_pb2 import Timestamp

from app.utils.protobuf_converters import (
    datetime_to_timestamp,
    timestamp_to_datetime,
    pydantic_to_protobuf_upload_status,
    pydantic_to_protobuf_document_status,
    protobuf_to_pydantic_document_status,
    pydantic_to_protobuf_storage_backend,
    pydantic_to_protobuf_scan_status,
    pydantic_to_protobuf_scan_result_type,
    pydantic_to_protobuf_threat_severity,
    pydantic_to_protobuf_sort_order,
    protobuf_to_pydantic_sort_order,
    pydantic_storage_location_to_protobuf,
    pydantic_threat_detail_to_protobuf,
    pydantic_version_history_to_protobuf,
    pydantic_scan_result_to_protobuf,
    pydantic_document_metadata_to_protobuf,
    pydantic_upload_response_to_protobuf,
    pydantic_document_response_to_protobuf,
    protobuf_upload_request_to_pydantic,
    protobuf_list_request_to_pydantic,
    pydantic_document_list_response_to_protobuf,
)
from app.models.document import (
    DocumentMetadata,
    DocumentCreate,
    DocumentListRequest,
    DocumentResponse,
    DocumentListResponse,
    UploadResponse,
    StorageLocation,
    VersionHistory,
    ScanResult,
    ThreatDetail,
    DateRange,
    DocumentStatus,
    StorageBackend,
    UploadStatus,
    ScanStatus,
    ScanResultType,
    ThreatSeverity,
    SortOrder,
)
from docs.v1 import document_pb2 as pb


class TestDateTimeConverters:
    """Test datetime conversion utilities."""
    
    def test_datetime_to_timestamp(self):
        """Test datetime to protobuf timestamp conversion."""
        dt = datetime(2023, 12, 25, 10, 30, 45)
        timestamp = datetime_to_timestamp(dt)
        
        assert isinstance(timestamp, Timestamp)
        assert timestamp.ToDatetime() == dt
    
    def test_datetime_to_timestamp_none(self):
        """Test datetime to timestamp with None input."""
        result = datetime_to_timestamp(None)
        assert result is None
    
    def test_timestamp_to_datetime(self):
        """Test protobuf timestamp to datetime conversion."""
        dt = datetime(2023, 12, 25, 10, 30, 45)
        timestamp = Timestamp()
        timestamp.FromDatetime(dt)
        
        result = timestamp_to_datetime(timestamp)
        assert result == dt
    
    def test_timestamp_to_datetime_none(self):
        """Test timestamp to datetime with None input."""
        result = timestamp_to_datetime(None)
        assert result is None


class TestEnumConverters:
    """Test enum conversion utilities."""
    
    def test_upload_status_conversion(self):
        """Test UploadStatus enum conversion."""
        assert pydantic_to_protobuf_upload_status(UploadStatus.PENDING) == pb.UploadStatus.UPLOAD_STATUS_PENDING
        assert pydantic_to_protobuf_upload_status(UploadStatus.PROCESSING) == pb.UploadStatus.UPLOAD_STATUS_PROCESSING
        assert pydantic_to_protobuf_upload_status(UploadStatus.COMPLETED) == pb.UploadStatus.UPLOAD_STATUS_COMPLETED
        assert pydantic_to_protobuf_upload_status(UploadStatus.FAILED) == pb.UploadStatus.UPLOAD_STATUS_FAILED
    
    def test_document_status_conversion(self):
        """Test DocumentStatus enum conversion."""
        assert pydantic_to_protobuf_document_status(DocumentStatus.ACTIVE) == pb.DocumentStatus.DOCUMENT_STATUS_ACTIVE
        assert pydantic_to_protobuf_document_status(DocumentStatus.ARCHIVED) == pb.DocumentStatus.DOCUMENT_STATUS_ARCHIVED
        assert pydantic_to_protobuf_document_status(DocumentStatus.DELETED) == pb.DocumentStatus.DOCUMENT_STATUS_DELETED
        assert pydantic_to_protobuf_document_status(DocumentStatus.PROCESSING) == pb.DocumentStatus.DOCUMENT_STATUS_PROCESSING
        assert pydantic_to_protobuf_document_status(DocumentStatus.QUARANTINED) == pb.DocumentStatus.DOCUMENT_STATUS_QUARANTINED
    
    def test_document_status_reverse_conversion(self):
        """Test DocumentStatus enum reverse conversion."""
        assert protobuf_to_pydantic_document_status(pb.DocumentStatus.DOCUMENT_STATUS_ACTIVE) == DocumentStatus.ACTIVE
        assert protobuf_to_pydantic_document_status(pb.DocumentStatus.DOCUMENT_STATUS_ARCHIVED) == DocumentStatus.ARCHIVED
        assert protobuf_to_pydantic_document_status(pb.DocumentStatus.DOCUMENT_STATUS_DELETED) == DocumentStatus.DELETED
        assert protobuf_to_pydantic_document_status(pb.DocumentStatus.DOCUMENT_STATUS_PROCESSING) == DocumentStatus.PROCESSING
        assert protobuf_to_pydantic_document_status(pb.DocumentStatus.DOCUMENT_STATUS_QUARANTINED) == DocumentStatus.QUARANTINED
    
    def test_storage_backend_conversion(self):
        """Test StorageBackend enum conversion."""
        assert pydantic_to_protobuf_storage_backend(StorageBackend.S3) == pb.StorageBackend.STORAGE_BACKEND_S3
        assert pydantic_to_protobuf_storage_backend(StorageBackend.MINIO) == pb.StorageBackend.STORAGE_BACKEND_MINIO
        assert pydantic_to_protobuf_storage_backend(StorageBackend.GCS) == pb.StorageBackend.STORAGE_BACKEND_GCS
        assert pydantic_to_protobuf_storage_backend(StorageBackend.AZURE) == pb.StorageBackend.STORAGE_BACKEND_AZURE
    
    def test_scan_status_conversion(self):
        """Test ScanStatus enum conversion."""
        assert pydantic_to_protobuf_scan_status(ScanStatus.PENDING) == pb.ScanStatus.SCAN_STATUS_PENDING
        assert pydantic_to_protobuf_scan_status(ScanStatus.SCANNING) == pb.ScanStatus.SCAN_STATUS_SCANNING
        assert pydantic_to_protobuf_scan_status(ScanStatus.COMPLETED) == pb.ScanStatus.SCAN_STATUS_COMPLETED
        assert pydantic_to_protobuf_scan_status(ScanStatus.FAILED) == pb.ScanStatus.SCAN_STATUS_FAILED
    
    def test_scan_result_type_conversion(self):
        """Test ScanResultType enum conversion."""
        assert pydantic_to_protobuf_scan_result_type(ScanResultType.CLEAN) == pb.ScanResultType.SCAN_RESULT_TYPE_CLEAN
        assert pydantic_to_protobuf_scan_result_type(ScanResultType.INFECTED) == pb.ScanResultType.SCAN_RESULT_TYPE_INFECTED
        assert pydantic_to_protobuf_scan_result_type(ScanResultType.SUSPICIOUS) == pb.ScanResultType.SCAN_RESULT_TYPE_SUSPICIOUS
        assert pydantic_to_protobuf_scan_result_type(ScanResultType.ERROR) == pb.ScanResultType.SCAN_RESULT_TYPE_ERROR
    
    def test_threat_severity_conversion(self):
        """Test ThreatSeverity enum conversion."""
        assert pydantic_to_protobuf_threat_severity(ThreatSeverity.LOW) == pb.ThreatSeverity.THREAT_SEVERITY_LOW
        assert pydantic_to_protobuf_threat_severity(ThreatSeverity.MEDIUM) == pb.ThreatSeverity.THREAT_SEVERITY_MEDIUM
        assert pydantic_to_protobuf_threat_severity(ThreatSeverity.HIGH) == pb.ThreatSeverity.THREAT_SEVERITY_HIGH
        assert pydantic_to_protobuf_threat_severity(ThreatSeverity.CRITICAL) == pb.ThreatSeverity.THREAT_SEVERITY_CRITICAL
    
    def test_sort_order_conversion(self):
        """Test SortOrder enum conversion."""
        assert pydantic_to_protobuf_sort_order(SortOrder.ASC) == pb.SortOrder.SORT_ORDER_ASC
        assert pydantic_to_protobuf_sort_order(SortOrder.DESC) == pb.SortOrder.SORT_ORDER_DESC
    
    def test_sort_order_reverse_conversion(self):
        """Test SortOrder enum reverse conversion."""
        assert protobuf_to_pydantic_sort_order(pb.SortOrder.SORT_ORDER_ASC) == SortOrder.ASC
        assert protobuf_to_pydantic_sort_order(pb.SortOrder.SORT_ORDER_DESC) == SortOrder.DESC


class TestModelConverters:
    """Test model conversion utilities."""
    
    def test_storage_location_conversion(self):
        """Test StorageLocation conversion."""
        location = StorageLocation(
            backend=StorageBackend.S3,
            bucket="test-bucket",
            key="test/key",
            region="us-east-1",
            endpoint_url="https://s3.amazonaws.com",
        )
        
        pb_location = pydantic_storage_location_to_protobuf(location)
        
        assert pb_location.backend == pb.StorageBackend.STORAGE_BACKEND_S3
        assert pb_location.bucket == "test-bucket"
        assert pb_location.key == "test/key"
        assert pb_location.region == "us-east-1"
        assert pb_location.endpoint_url == "https://s3.amazonaws.com"
    
    def test_threat_detail_conversion(self):
        """Test ThreatDetail conversion."""
        threat = ThreatDetail(
            name="Test.Virus",
            type="virus",
            severity=ThreatSeverity.HIGH,
            description="Test virus detected",
        )
        
        pb_threat = pydantic_threat_detail_to_protobuf(threat)
        
        assert pb_threat.name == "Test.Virus"
        assert pb_threat.type == "virus"
        assert pb_threat.severity == pb.ThreatSeverity.THREAT_SEVERITY_HIGH
        assert pb_threat.description == "Test virus detected"
    
    def test_version_history_conversion(self):
        """Test VersionHistory conversion."""
        dt = datetime(2023, 12, 25, 10, 30, 45)
        version = VersionHistory(
            version=1,
            created_at=dt,
            created_by="user123",
            description="Initial version",
            size_bytes=1024,
            checksum="abc123",
            location=StorageLocation(
                backend=StorageBackend.S3,
                bucket="test-bucket",
                key="test/key",
                region="us-east-1",
            ),
        )
        
        pb_version = pydantic_version_history_to_protobuf(version)
        
        assert pb_version.version == 1
        assert pb_version.created_at.ToDatetime() == dt
        assert pb_version.created_by == "user123"
        assert pb_version.description == "Initial version"
        assert pb_version.size_bytes == 1024
        assert pb_version.checksum == "abc123"
        assert pb_version.location.bucket == "test-bucket"
    
    def test_scan_result_conversion(self):
        """Test ScanResult conversion."""
        dt = datetime(2023, 12, 25, 10, 30, 45)
        scan_result = ScanResult(
            scan_id="scan123",
            document_id="doc123",
            status=ScanStatus.COMPLETED,
            result=ScanResultType.CLEAN,
            scanned_at=dt,
            duration_ms=1000,
            threats=[],
            scanner_version="1.0.0",
        )
        
        pb_scan = pydantic_scan_result_to_protobuf(scan_result)
        
        assert pb_scan.scan_id == "scan123"
        assert pb_scan.document_id == "doc123"
        assert pb_scan.status == pb.ScanStatus.SCAN_STATUS_COMPLETED
        assert pb_scan.result == pb.ScanResultType.SCAN_RESULT_TYPE_CLEAN
        assert pb_scan.scanned_at.ToDatetime() == dt
        assert pb_scan.duration_ms == 1000
        assert len(pb_scan.threats) == 0
        assert pb_scan.scanner_version == "1.0.0"
    
    def test_document_metadata_conversion(self):
        """Test DocumentMetadata conversion."""
        dt = datetime(2023, 12, 25, 10, 30, 45)
        metadata = DocumentMetadata(
            document_id="doc123",
            filename="test.pdf",
            content_type="application/pdf",
            size_bytes=1024,
            owner_id="user123",
            tenant_id="tenant123",
            tags=["test", "document"],
            title="Test Document",
            description="A test document",
            created_at=dt,
            updated_at=dt,
            version=1,
            status=DocumentStatus.ACTIVE,
            checksum="abc123",
            attributes={"category": "test"},
        )
        
        pb_metadata = pydantic_document_metadata_to_protobuf(metadata)
        
        assert pb_metadata.document_id == "doc123"
        assert pb_metadata.filename == "test.pdf"
        assert pb_metadata.content_type == "application/pdf"
        assert pb_metadata.size_bytes == 1024
        assert pb_metadata.owner_id == "user123"
        assert pb_metadata.tenant_id == "tenant123"
        assert list(pb_metadata.tags) == ["test", "document"]
        assert pb_metadata.title == "Test Document"
        assert pb_metadata.description == "A test document"
        assert pb_metadata.created_at.ToDatetime() == dt
        assert pb_metadata.updated_at.ToDatetime() == dt
        assert pb_metadata.version == 1
        assert pb_metadata.status == pb.DocumentStatus.DOCUMENT_STATUS_ACTIVE
        assert pb_metadata.checksum == "abc123"
        assert pb_metadata.attributes["category"] == "test"
    
    def test_upload_response_conversion(self):
        """Test UploadResponse conversion."""
        dt = datetime(2023, 12, 25, 10, 30, 45)
        response = UploadResponse(
            document_id="doc123",
            status=UploadStatus.COMPLETED,
            location=StorageLocation(
                backend=StorageBackend.S3,
                bucket="test-bucket",
                key="test/key",
                region="us-east-1",
            ),
            uploaded_at=dt,
            size_bytes=1024,
            checksum="abc123",
        )
        
        pb_response = pydantic_upload_response_to_protobuf(response)
        
        assert pb_response.document_id == "doc123"
        assert pb_response.status == pb.UploadStatus.UPLOAD_STATUS_COMPLETED
        assert pb_response.location.bucket == "test-bucket"
        assert pb_response.uploaded_at.ToDatetime() == dt
        assert pb_response.size_bytes == 1024
        assert pb_response.checksum == "abc123"
    
    def test_document_response_conversion(self):
        """Test DocumentResponse conversion."""
        dt = datetime(2023, 12, 25, 10, 30, 45)
        response = DocumentResponse(
            metadata=DocumentMetadata(
                document_id="doc123",
                filename="test.pdf",
                content_type="application/pdf",
                size_bytes=1024,
                owner_id="user123",
                tenant_id="tenant123",
                tags=["test"],
                title="Test Document",
                description="A test document",
                created_at=dt,
                updated_at=dt,
                version=1,
                status=DocumentStatus.ACTIVE,
                checksum="abc123",
                attributes={},
            ),
            location=StorageLocation(
                backend=StorageBackend.S3,
                bucket="test-bucket",
                key="test/key",
                region="us-east-1",
            ),
            versions=[],
            last_scan=None,
        )
        
        pb_response = pydantic_document_response_to_protobuf(response)
        
        assert pb_response.metadata.document_id == "doc123"
        assert pb_response.metadata.filename == "test.pdf"
        assert pb_response.location.bucket == "test-bucket"
        assert pb_response.content == b""
        assert len(pb_response.versions) == 0
        assert pb_response.last_scan is None


class TestRequestConverters:
    """Test request conversion utilities."""
    
    def test_upload_request_conversion(self):
        """Test UploadRequest conversion."""
        metadata = pb.DocumentMetadata(
            filename="test.pdf",
            content_type="application/pdf",
            title="Test Document",
            description="A test document",
            tags=["test", "document"],
            attributes={"category": "test"},
        )
        
        request = pb.UploadRequest(
            metadata=metadata,
            content=b"file content",
            content_type="application/pdf",
            filename="test.pdf",
            session_id="session123",
        )
        
        file_data, document_create, session_id = protobuf_upload_request_to_pydantic(request)
        
        assert file_data == b"file content"
        assert document_create.filename == "test.pdf"
        assert document_create.content_type == "application/pdf"
        assert document_create.title == "Test Document"
        assert document_create.description == "A test document"
        assert document_create.tags == ["test", "document"]
        assert document_create.attributes == {"category": "test"}
        assert session_id == "session123"
    
    def test_list_request_conversion(self):
        """Test ListRequest conversion."""
        start_dt = datetime(2023, 1, 1)
        end_dt = datetime(2023, 12, 31)
        
        date_range = pb.DateRange(
            start_date=datetime_to_timestamp(start_dt),
            end_date=datetime_to_timestamp(end_dt),
        )
        
        request = pb.ListRequest(
            user_id="user123",
            tenant_id="tenant123",
            tags=["test", "document"],
            status=pb.DocumentStatus.DOCUMENT_STATUS_ACTIVE,
            offset=10,
            limit=20,
            sort_by="created_at",
            sort_order=pb.SortOrder.SORT_ORDER_DESC,
            date_range=date_range,
        )
        
        list_request = protobuf_list_request_to_pydantic(request)
        
        assert list_request.user_id == "user123"
        assert list_request.tenant_id == "tenant123"
        assert list_request.tags == ["test", "document"]
        assert list_request.status == DocumentStatus.ACTIVE
        assert list_request.offset == 10
        assert list_request.limit == 20
        assert list_request.sort_by == "created_at"
        assert list_request.sort_order == SortOrder.DESC
        assert list_request.date_range.start_date == start_dt
        assert list_request.date_range.end_date == end_dt
    
    def test_document_list_response_conversion(self):
        """Test DocumentListResponse conversion."""
        dt = datetime(2023, 12, 25, 10, 30, 45)
        response = DocumentListResponse(
            documents=[
                DocumentMetadata(
                    document_id="doc123",
                    filename="test.pdf",
                    content_type="application/pdf",
                    size_bytes=1024,
                    owner_id="user123",
                    tenant_id="tenant123",
                    tags=["test"],
                    title="Test Document",
                    description="A test document",
                    created_at=dt,
                    updated_at=dt,
                    version=1,
                    status=DocumentStatus.ACTIVE,
                    checksum="abc123",
                    attributes={},
                ),
            ],
            total_count=1,
            has_more=False,
            next_token=None,
        )
        
        pb_response = pydantic_document_list_response_to_protobuf(response)
        
        assert len(pb_response.documents) == 1
        assert pb_response.documents[0].document_id == "doc123"
        assert pb_response.documents[0].filename == "test.pdf"
        assert pb_response.total_count == 1
        assert pb_response.has_more == False
        assert pb_response.next_token == ""