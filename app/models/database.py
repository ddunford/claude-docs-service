"""Database models for document storage."""

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    BigInteger,
    Index,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Session
from sqlalchemy.dialects.postgresql import UUID, ARRAY

from app.models.document import DocumentStatus, StorageBackend, ScanStatus, ScanResultType, ThreatSeverity

Base = declarative_base()


class Document(Base):
    """Document metadata table."""
    __tablename__ = "documents"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, index=True)
    
    # Document metadata
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    checksum = Column(String(64), nullable=False)
    
    # Ownership and tenancy
    owner_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Document metadata
    title = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    tags = Column(ARRAY(String), default=[], nullable=False)
    attributes = Column(JSON, default={}, nullable=False)
    
    # Status and versioning
    status = Column(Enum(DocumentStatus), default=DocumentStatus.ACTIVE, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    storage_locations = relationship("StorageLocation", back_populates="document", cascade="all, delete-orphan")
    versions = relationship("DocumentVersion", back_populates="document", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="document", cascade="all, delete-orphan")
    scan_results = relationship("ScanResult", back_populates="document", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index("idx_documents_owner_tenant", "owner_id", "tenant_id"),
        Index("idx_documents_status", "status"),
        Index("idx_documents_created_at", "created_at"),
        Index("idx_documents_tags", "tags", postgresql_using="gin"),
    )


class StorageLocation(Base):
    """Storage location table."""
    __tablename__ = "storage_locations"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, index=True)
    
    # Foreign key to document
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    
    # Storage information
    backend = Column(Enum(StorageBackend), nullable=False)
    bucket = Column(String(255), nullable=False)
    key = Column(String(1024), nullable=False)
    region = Column(String(50), nullable=False)
    endpoint_url = Column(String(255), nullable=True)
    
    # Metadata
    is_primary = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    document = relationship("Document", back_populates="storage_locations")
    
    # Indexes
    __table_args__ = (
        Index("idx_storage_locations_document", "document_id"),
        Index("idx_storage_locations_backend", "backend"),
    )


class DocumentVersion(Base):
    """Document version history table."""
    __tablename__ = "document_versions"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, index=True)
    
    # Foreign key to document
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    
    # Version information
    version = Column(Integer, nullable=False)
    description = Column(Text, nullable=True)
    size_bytes = Column(BigInteger, nullable=False)
    checksum = Column(String(64), nullable=False)
    
    # Storage location for this version
    backend = Column(Enum(StorageBackend), nullable=False)
    bucket = Column(String(255), nullable=False)
    key = Column(String(1024), nullable=False)
    region = Column(String(50), nullable=False)
    endpoint_url = Column(String(255), nullable=True)
    
    # Metadata
    created_by = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    document = relationship("Document", back_populates="versions")
    
    # Indexes
    __table_args__ = (
        Index("idx_document_versions_document", "document_id"),
        Index("idx_document_versions_version", "document_id", "version"),
        Index("idx_document_versions_created_at", "created_at"),
    )


class AuditLog(Base):
    """Audit log table for document operations."""
    __tablename__ = "audit_logs"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, index=True)
    
    # Foreign key to document (nullable for tenant-level operations)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)
    
    # Audit information
    action = Column(String(50), nullable=False)  # upload, download, delete, etc.
    user_id = Column(UUID(as_uuid=True), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    
    # Request/response details
    request_id = Column(String(128), nullable=True)
    ip_address = Column(String(45), nullable=True)  # IPv6 compatible
    user_agent = Column(String(512), nullable=True)
    
    # Operation details
    status = Column(String(20), nullable=False)  # success, failure, pending
    error_message = Column(Text, nullable=True)
    audit_metadata = Column(JSON, default={}, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    document = relationship("Document", back_populates="audit_logs")
    
    # Indexes
    __table_args__ = (
        Index("idx_audit_logs_document", "document_id"),
        Index("idx_audit_logs_user_tenant", "user_id", "tenant_id"),
        Index("idx_audit_logs_action", "action"),
        Index("idx_audit_logs_created_at", "created_at"),
    )


class ScanResult(Base):
    """Virus scan results table."""
    __tablename__ = "scan_results"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, index=True)
    
    # Foreign key to document
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    
    # Scan information
    scan_id = Column(String(128), nullable=False, unique=True)
    status = Column(Enum(ScanStatus), nullable=False)
    result = Column(Enum(ScanResultType), nullable=True)
    
    # Scan details
    scanner_version = Column(String(100), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    
    # Timestamps
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    document = relationship("Document", back_populates="scan_results")
    threats = relationship("ThreatDetail", back_populates="scan_result", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index("idx_scan_results_document", "document_id"),
        Index("idx_scan_results_scan_id", "scan_id"),
        Index("idx_scan_results_status", "status"),
        Index("idx_scan_results_started_at", "started_at"),
    )


class ThreatDetail(Base):
    """Threat details table."""
    __tablename__ = "threat_details"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, index=True)
    
    # Foreign key to scan result
    scan_result_id = Column(UUID(as_uuid=True), ForeignKey("scan_results.id"), nullable=False)
    
    # Threat information
    name = Column(String(255), nullable=False)
    type = Column(String(100), nullable=False)
    severity = Column(Enum(ThreatSeverity), nullable=False)
    description = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    scan_result = relationship("ScanResult", back_populates="threats")
    
    # Indexes
    __table_args__ = (
        Index("idx_threat_details_scan_result", "scan_result_id"),
        Index("idx_threat_details_severity", "severity"),
    )


class UploadSession(Base):
    """Upload session tracking table."""
    __tablename__ = "upload_sessions"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, index=True)
    
    # Session information
    session_id = Column(String(128), nullable=False, unique=True)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    
    # Upload details
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    expected_size = Column(BigInteger, nullable=True)
    uploaded_size = Column(BigInteger, default=0, nullable=False)
    
    # Status
    status = Column(String(20), default="pending", nullable=False)
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    
    # Indexes
    __table_args__ = (
        Index("idx_upload_sessions_session_id", "session_id"),
        Index("idx_upload_sessions_user_tenant", "user_id", "tenant_id"),
        Index("idx_upload_sessions_status", "status"),
        Index("idx_upload_sessions_expires_at", "expires_at"),
    )