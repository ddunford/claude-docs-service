"""Pydantic models for document metadata and validation."""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, validator


class DocumentStatus(str, Enum):
    """Document status enumeration."""
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"
    PROCESSING = "processing"
    QUARANTINED = "quarantined"


class StorageBackend(str, Enum):
    """Storage backend enumeration."""
    S3 = "s3"
    MINIO = "minio"
    GCS = "gcs"
    AZURE = "azure"


class UploadStatus(str, Enum):
    """Upload status enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ScanStatus(str, Enum):
    """Virus scan status enumeration."""
    PENDING = "pending"
    SCANNING = "scanning"
    COMPLETED = "completed"
    FAILED = "failed"


class ScanResultType(str, Enum):
    """Virus scan result enumeration."""
    CLEAN = "clean"
    INFECTED = "infected"
    SUSPICIOUS = "suspicious"
    ERROR = "error"


class ThreatSeverity(str, Enum):
    """Threat severity enumeration."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SortOrder(str, Enum):
    """Sort order enumeration."""
    ASC = "asc"
    DESC = "desc"


class StorageLocation(BaseModel):
    """Storage location information."""
    backend: StorageBackend
    bucket: str
    key: str
    region: str
    endpoint_url: Optional[str] = None
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class ThreatDetail(BaseModel):
    """Threat detail information."""
    name: str
    type: str
    severity: ThreatSeverity
    description: Optional[str] = None
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class ScanResult(BaseModel):
    """Virus scan result."""
    scan_id: str
    document_id: str
    status: ScanStatus
    result: ScanResultType
    scanned_at: datetime
    duration_ms: int
    threats: List[ThreatDetail] = Field(default_factory=list)
    scanner_version: Optional[str] = None
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class VersionHistory(BaseModel):
    """Version history entry."""
    version: int
    created_at: datetime
    created_by: str
    description: Optional[str] = None
    size_bytes: int
    checksum: str
    location: StorageLocation
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class DocumentMetadata(BaseModel):
    """Document metadata model."""
    document_id: str
    filename: str
    content_type: str
    size_bytes: int
    owner_id: str
    tenant_id: str
    tags: List[str] = Field(default_factory=list)
    title: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    version: int = 1
    status: DocumentStatus = DocumentStatus.ACTIVE
    checksum: str
    attributes: Dict[str, str] = Field(default_factory=dict)
    
    @validator('tags')
    def validate_tags(cls, v):
        """Validate tags list."""
        if not isinstance(v, list):
            raise ValueError('Tags must be a list')
        return [tag.strip().lower() for tag in v if tag.strip()]
    
    @validator('size_bytes')
    def validate_size(cls, v):
        """Validate file size."""
        if v <= 0:
            raise ValueError('File size must be greater than 0')
        return v
    
    @validator('filename')
    def validate_filename(cls, v):
        """Validate filename."""
        if not v or not v.strip():
            raise ValueError('Filename cannot be empty')
        return v.strip()
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class DocumentCreate(BaseModel):
    """Document creation request model."""
    filename: str
    content_type: str
    title: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    attributes: Dict[str, str] = Field(default_factory=dict)
    
    @validator('tags')
    def validate_tags(cls, v):
        """Validate tags list."""
        if not isinstance(v, list):
            raise ValueError('Tags must be a list')
        return [tag.strip().lower() for tag in v if tag.strip()]
    
    @validator('filename')
    def validate_filename(cls, v):
        """Validate filename."""
        if not v or not v.strip():
            raise ValueError('Filename cannot be empty')
        return v.strip()
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class DocumentUpdate(BaseModel):
    """Document update request model."""
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    attributes: Optional[Dict[str, str]] = None
    status: Optional[DocumentStatus] = None
    
    @validator('tags')
    def validate_tags(cls, v):
        """Validate tags list."""
        if v is not None and not isinstance(v, list):
            raise ValueError('Tags must be a list')
        return [tag.strip().lower() for tag in v if tag.strip()] if v else v
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class DocumentResponse(BaseModel):
    """Document response model."""
    metadata: DocumentMetadata
    location: StorageLocation
    versions: List[VersionHistory] = Field(default_factory=list)
    last_scan: Optional[ScanResult] = None
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class UploadRequest(BaseModel):
    """Document upload request model."""
    metadata: DocumentCreate
    session_id: Optional[str] = None
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class UploadResponse(BaseModel):
    """Document upload response model."""
    document_id: str
    status: UploadStatus
    location: StorageLocation
    uploaded_at: datetime
    size_bytes: int
    checksum: str
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class DateRange(BaseModel):
    """Date range filter model."""
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    
    @validator('end_date')
    def validate_date_range(cls, v, values):
        """Validate that end_date is after start_date."""
        if v is not None and 'start_date' in values and values['start_date'] is not None:
            if v <= values['start_date']:
                raise ValueError('End date must be after start date')
        return v


class DocumentListRequest(BaseModel):
    """Document list request model."""
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    status: Optional[DocumentStatus] = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=1000)
    sort_by: str = Field(default="created_at")
    sort_order: SortOrder = Field(default=SortOrder.DESC)
    date_range: Optional[DateRange] = None
    
    @validator('tags')
    def validate_tags(cls, v):
        """Validate tags list."""
        if not isinstance(v, list):
            raise ValueError('Tags must be a list')
        return [tag.strip().lower() for tag in v if tag.strip()]
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class DocumentListResponse(BaseModel):
    """Document list response model."""
    documents: List[DocumentMetadata]
    total_count: int
    has_more: bool
    next_token: Optional[str] = None
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class ErrorResponse(BaseModel):
    """Error response model."""
    error: str
    message: str
    details: Optional[Dict[str, str]] = None
    trace_id: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    service: str
    version: str
    timestamp: datetime
    dependencies: Dict[str, str] = Field(default_factory=dict)