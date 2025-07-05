"""Utilities for converting between protobuf messages and Pydantic models."""

from datetime import datetime
from typing import List, Optional, Dict, Any
from google.protobuf.timestamp_pb2 import Timestamp
from google.protobuf.empty_pb2 import Empty

from docs.v1 import document_pb2 as pb
from app.models.document import (
    DocumentMetadata as PydanticDocumentMetadata,
    DocumentCreate,
    DocumentListRequest,
    DocumentResponse,
    UploadResponse,
    StorageLocation as PydanticStorageLocation,
    VersionHistory as PydanticVersionHistory,
    ScanResult as PydanticScanResult,
    ThreatDetail as PydanticThreatDetail,
    DateRange as PydanticDateRange,
    DocumentStatus,
    StorageBackend,
    UploadStatus,
    ScanStatus,
    ScanResultType,
    ThreatSeverity,
    SortOrder,
)


def datetime_to_timestamp(dt: datetime) -> Timestamp:
    """Convert datetime to protobuf timestamp."""
    if dt is None:
        return None
    timestamp = Timestamp()
    timestamp.FromDatetime(dt)
    return timestamp


def timestamp_to_datetime(timestamp: Timestamp) -> datetime:
    """Convert protobuf timestamp to datetime."""
    if timestamp is None:
        return None
    return timestamp.ToDatetime()


def pydantic_to_protobuf_upload_status(status: UploadStatus) -> int:
    """Convert Pydantic UploadStatus to protobuf enum."""
    mapping = {
        UploadStatus.PENDING: pb.UploadStatus.UPLOAD_STATUS_PENDING,
        UploadStatus.PROCESSING: pb.UploadStatus.UPLOAD_STATUS_PROCESSING,
        UploadStatus.COMPLETED: pb.UploadStatus.UPLOAD_STATUS_COMPLETED,
        UploadStatus.FAILED: pb.UploadStatus.UPLOAD_STATUS_FAILED,
    }
    return mapping.get(status, pb.UploadStatus.UPLOAD_STATUS_UNKNOWN)


def pydantic_to_protobuf_document_status(status: DocumentStatus) -> int:
    """Convert Pydantic DocumentStatus to protobuf enum."""
    mapping = {
        DocumentStatus.ACTIVE: pb.DocumentStatus.DOCUMENT_STATUS_ACTIVE,
        DocumentStatus.ARCHIVED: pb.DocumentStatus.DOCUMENT_STATUS_ARCHIVED,
        DocumentStatus.DELETED: pb.DocumentStatus.DOCUMENT_STATUS_DELETED,
        DocumentStatus.PROCESSING: pb.DocumentStatus.DOCUMENT_STATUS_PROCESSING,
        DocumentStatus.QUARANTINED: pb.DocumentStatus.DOCUMENT_STATUS_QUARANTINED,
    }
    return mapping.get(status, pb.DocumentStatus.DOCUMENT_STATUS_UNKNOWN)


def protobuf_to_pydantic_document_status(status: int) -> DocumentStatus:
    """Convert protobuf enum to Pydantic DocumentStatus."""
    mapping = {
        pb.DocumentStatus.DOCUMENT_STATUS_ACTIVE: DocumentStatus.ACTIVE,
        pb.DocumentStatus.DOCUMENT_STATUS_ARCHIVED: DocumentStatus.ARCHIVED,
        pb.DocumentStatus.DOCUMENT_STATUS_DELETED: DocumentStatus.DELETED,
        pb.DocumentStatus.DOCUMENT_STATUS_PROCESSING: DocumentStatus.PROCESSING,
        pb.DocumentStatus.DOCUMENT_STATUS_QUARANTINED: DocumentStatus.QUARANTINED,
    }
    return mapping.get(status, DocumentStatus.ACTIVE)


def pydantic_to_protobuf_storage_backend(backend: StorageBackend) -> int:
    """Convert Pydantic StorageBackend to protobuf enum."""
    mapping = {
        StorageBackend.S3: pb.StorageBackend.STORAGE_BACKEND_S3,
        StorageBackend.MINIO: pb.StorageBackend.STORAGE_BACKEND_MINIO,
        StorageBackend.GCS: pb.StorageBackend.STORAGE_BACKEND_GCS,
        StorageBackend.AZURE: pb.StorageBackend.STORAGE_BACKEND_AZURE,
    }
    return mapping.get(backend, pb.StorageBackend.STORAGE_BACKEND_UNKNOWN)


def pydantic_to_protobuf_scan_status(status: ScanStatus) -> int:
    """Convert Pydantic ScanStatus to protobuf enum."""
    mapping = {
        ScanStatus.PENDING: pb.ScanStatus.SCAN_STATUS_PENDING,
        ScanStatus.SCANNING: pb.ScanStatus.SCAN_STATUS_SCANNING,
        ScanStatus.COMPLETED: pb.ScanStatus.SCAN_STATUS_COMPLETED,
        ScanStatus.FAILED: pb.ScanStatus.SCAN_STATUS_FAILED,
    }
    return mapping.get(status, pb.ScanStatus.SCAN_STATUS_UNKNOWN)


def pydantic_to_protobuf_scan_result_type(result_type: ScanResultType) -> int:
    """Convert Pydantic ScanResultType to protobuf enum."""
    mapping = {
        ScanResultType.CLEAN: pb.ScanResultType.SCAN_RESULT_TYPE_CLEAN,
        ScanResultType.INFECTED: pb.ScanResultType.SCAN_RESULT_TYPE_INFECTED,
        ScanResultType.SUSPICIOUS: pb.ScanResultType.SCAN_RESULT_TYPE_SUSPICIOUS,
        ScanResultType.ERROR: pb.ScanResultType.SCAN_RESULT_TYPE_ERROR,
    }
    return mapping.get(result_type, pb.ScanResultType.SCAN_RESULT_TYPE_UNKNOWN)


def pydantic_to_protobuf_threat_severity(severity: ThreatSeverity) -> int:
    """Convert Pydantic ThreatSeverity to protobuf enum."""
    mapping = {
        ThreatSeverity.LOW: pb.ThreatSeverity.THREAT_SEVERITY_LOW,
        ThreatSeverity.MEDIUM: pb.ThreatSeverity.THREAT_SEVERITY_MEDIUM,
        ThreatSeverity.HIGH: pb.ThreatSeverity.THREAT_SEVERITY_HIGH,
        ThreatSeverity.CRITICAL: pb.ThreatSeverity.THREAT_SEVERITY_CRITICAL,
    }
    return mapping.get(severity, pb.ThreatSeverity.THREAT_SEVERITY_UNKNOWN)


def pydantic_to_protobuf_sort_order(order: SortOrder) -> int:
    """Convert Pydantic SortOrder to protobuf enum."""
    mapping = {
        SortOrder.ASC: pb.SortOrder.SORT_ORDER_ASC,
        SortOrder.DESC: pb.SortOrder.SORT_ORDER_DESC,
    }
    return mapping.get(order, pb.SortOrder.SORT_ORDER_UNKNOWN)


def protobuf_to_pydantic_sort_order(order: int) -> SortOrder:
    """Convert protobuf enum to Pydantic SortOrder."""
    mapping = {
        pb.SortOrder.SORT_ORDER_ASC: SortOrder.ASC,
        pb.SortOrder.SORT_ORDER_DESC: SortOrder.DESC,
    }
    return mapping.get(order, SortOrder.DESC)


def pydantic_storage_location_to_protobuf(location: PydanticStorageLocation) -> pb.StorageLocation:
    """Convert Pydantic StorageLocation to protobuf."""
    return pb.StorageLocation(
        backend=pydantic_to_protobuf_storage_backend(location.backend),
        bucket=location.bucket,
        key=location.key,
        region=location.region,
        endpoint_url=location.endpoint_url or "",
    )


def pydantic_threat_detail_to_protobuf(threat: PydanticThreatDetail) -> pb.ThreatDetail:
    """Convert Pydantic ThreatDetail to protobuf."""
    return pb.ThreatDetail(
        name=threat.name,
        type=threat.type,
        severity=pydantic_to_protobuf_threat_severity(threat.severity),
        description=threat.description or "",
    )


def pydantic_version_history_to_protobuf(version: PydanticVersionHistory) -> pb.VersionHistory:
    """Convert Pydantic VersionHistory to protobuf."""
    return pb.VersionHistory(
        version=version.version,
        created_at=datetime_to_timestamp(version.created_at),
        created_by=version.created_by,
        description=version.description or "",
        size_bytes=version.size_bytes,
        checksum=version.checksum,
        location=pydantic_storage_location_to_protobuf(version.location),
    )


def pydantic_scan_result_to_protobuf(scan_result: PydanticScanResult) -> pb.ScanResult:
    """Convert Pydantic ScanResult to protobuf."""
    return pb.ScanResult(
        scan_id=scan_result.scan_id,
        document_id=scan_result.document_id,
        status=pydantic_to_protobuf_scan_status(scan_result.status),
        result=pydantic_to_protobuf_scan_result_type(scan_result.result),
        scanned_at=datetime_to_timestamp(scan_result.scanned_at),
        duration_ms=scan_result.duration_ms,
        threats=[pydantic_threat_detail_to_protobuf(threat) for threat in scan_result.threats],
        scanner_version=scan_result.scanner_version or "",
    )


def pydantic_document_metadata_to_protobuf(metadata: PydanticDocumentMetadata) -> pb.DocumentMetadata:
    """Convert Pydantic DocumentMetadata to protobuf."""
    return pb.DocumentMetadata(
        document_id=metadata.document_id,
        filename=metadata.filename,
        content_type=metadata.content_type,
        size_bytes=metadata.size_bytes,
        owner_id=metadata.owner_id,
        tenant_id=metadata.tenant_id,
        tags=metadata.tags,
        title=metadata.title or "",
        description=metadata.description or "",
        created_at=datetime_to_timestamp(metadata.created_at),
        updated_at=datetime_to_timestamp(metadata.updated_at),
        version=metadata.version,
        status=pydantic_to_protobuf_document_status(metadata.status),
        checksum=metadata.checksum,
        attributes=metadata.attributes,
    )


def pydantic_upload_response_to_protobuf(response: UploadResponse) -> pb.UploadResponse:
    """Convert Pydantic UploadResponse to protobuf."""
    return pb.UploadResponse(
        document_id=response.document_id,
        status=pydantic_to_protobuf_upload_status(response.status),
        location=pydantic_storage_location_to_protobuf(response.location),
        uploaded_at=datetime_to_timestamp(response.uploaded_at),
        size_bytes=response.size_bytes,
        checksum=response.checksum,
    )


def pydantic_document_response_to_protobuf(response: DocumentResponse) -> pb.DocumentResponse:
    """Convert Pydantic DocumentResponse to protobuf."""
    return pb.DocumentResponse(
        metadata=pydantic_document_metadata_to_protobuf(response.metadata),
        content=b"",  # Content is not included in protobuf response by default
        location=pydantic_storage_location_to_protobuf(response.location),
        versions=[pydantic_version_history_to_protobuf(v) for v in response.versions],
        last_scan=pydantic_scan_result_to_protobuf(response.last_scan) if response.last_scan else None,
    )


def protobuf_upload_request_to_pydantic(request: pb.UploadRequest) -> tuple[bytes, DocumentCreate, str]:
    """Convert protobuf UploadRequest to Pydantic models."""
    # Extract metadata from protobuf
    metadata = request.metadata
    
    # Convert to Pydantic DocumentCreate
    document_create = DocumentCreate(
        filename=request.filename,
        content_type=request.content_type,
        title=metadata.title if metadata else "",
        description=metadata.description if metadata else "",
        tags=list(metadata.tags) if metadata else [],
        attributes=dict(metadata.attributes) if metadata else {},
    )
    
    return request.content, document_create, request.session_id


def protobuf_list_request_to_pydantic(request: pb.ListRequest) -> DocumentListRequest:
    """Convert protobuf ListRequest to Pydantic DocumentListRequest."""
    date_range = None
    if request.date_range:
        date_range = PydanticDateRange(
            start_date=timestamp_to_datetime(request.date_range.start_date),
            end_date=timestamp_to_datetime(request.date_range.end_date),
        )
    
    return DocumentListRequest(
        user_id=request.user_id or None,
        tenant_id=request.tenant_id or None,
        tags=list(request.tags),
        status=protobuf_to_pydantic_document_status(request.status),
        offset=request.offset,
        limit=request.limit,
        sort_by=request.sort_by,
        sort_order=protobuf_to_pydantic_sort_order(request.sort_order),
        date_range=date_range,
    )


def pydantic_document_list_response_to_protobuf(response) -> pb.DocumentListResponse:
    """Convert Pydantic DocumentListResponse to protobuf."""
    return pb.DocumentListResponse(
        documents=[pydantic_document_metadata_to_protobuf(doc) for doc in response.documents],
        total_count=response.total_count,
        has_more=response.has_more,
        next_token=response.next_token or "",
    )