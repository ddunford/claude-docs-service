"""Document service for handling document operations."""

import hashlib
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.database import Document, DocumentVersion, AuditLog
from app.models.database import StorageLocation as DBStorageLocation
from app.models.document import (
    DocumentMetadata,
    DocumentCreate,
    DocumentUpdate,
    DocumentResponse,
    DocumentListRequest,
    DocumentListResponse,
    UploadResponse,
    DocumentStatus,
    UploadStatus,
    VersionHistory,
    StorageLocation,
    StorageBackend as StorageBackendEnum,
    ScanStatus,
    ScanResult as ScanResultModel,
    ThreatDetail,
)
from app.storage.factory import get_storage_backend
from app.services.redis_client import redis_client
from app.services.event_publisher import event_publisher
from app.utils.logging import get_logger, log_document_event


class DocumentService:
    """Service for handling document operations."""
    
    def __init__(self):
        """Initialize document service."""
        self.logger = get_logger(self.__class__.__name__)
        self.storage = get_storage_backend()
    
    async def upload_document(
        self,
        file_data: bytes,
        document_create: DocumentCreate,
        user_id: str,
        tenant_id: str,
        session_id: Optional[str] = None,
    ) -> UploadResponse:
        """Upload a document."""
        try:
            # Generate document ID
            document_id = str(uuid.uuid4())
            
            # Calculate checksum
            checksum = hashlib.sha256(file_data).hexdigest()
            
            # Generate storage key
            storage_key = f"{tenant_id}/{document_id}/{document_create.filename}"
            
            # Upload to storage
            storage_location = await self.storage.upload_file(
                file_data=file_data,
                key=storage_key,
                content_type=document_create.content_type,
                metadata={
                    "document_id": document_id,
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "filename": document_create.filename,
                },
            )
            
            # Save to database
            async with get_db() as db:
                # Create document record
                document = Document(
                    id=document_id,
                    filename=document_create.filename,
                    content_type=document_create.content_type,
                    size_bytes=len(file_data),
                    checksum=checksum,
                    owner_id=user_id,
                    tenant_id=tenant_id,
                    title=document_create.title,
                    description=document_create.description,
                    tags=document_create.tags,
                    attributes=document_create.attributes,
                    status=DocumentStatus.ACTIVE,
                    version=1,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                
                db.add(document)
                
                # Create storage location record
                storage_loc = DBStorageLocation(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    backend=storage_location.backend,
                    bucket=storage_location.bucket,
                    key=storage_location.key,
                    region=storage_location.region,
                    endpoint_url=storage_location.endpoint_url,
                    is_primary=True,
                    created_at=datetime.utcnow(),
                )
                
                db.add(storage_loc)
                
                # Create version record
                version = DocumentVersion(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    version=1,
                    description="Initial version",
                    size_bytes=len(file_data),
                    checksum=checksum,
                    backend=storage_location.backend,
                    bucket=storage_location.bucket,
                    key=storage_location.key,
                    region=storage_location.region,
                    endpoint_url=storage_location.endpoint_url,
                    created_by=user_id,
                    created_at=datetime.utcnow(),
                )
                
                db.add(version)
                
                # Create audit log
                audit_log = AuditLog(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    action="upload",
                    user_id=user_id,
                    tenant_id=tenant_id,
                    request_id=session_id,
                    status="success",
                    audit_metadata={
                        "filename": document_create.filename,
                        "size_bytes": len(file_data),
                        "content_type": document_create.content_type,
                    },
                    created_at=datetime.utcnow(),
                )
                
                db.add(audit_log)
                
                await db.commit()
            
            # Clean up upload session if exists
            if session_id:
                await redis_client.delete_upload_session(session_id)
            
            # Log event
            log_document_event(
                self.logger,
                "document_uploaded",
                document_id,
                tenant_id,
                user_id,
                filename=document_create.filename,
                size_bytes=len(file_data),
            )
            
            # Publish event
            try:
                await event_publisher.publish_document_uploaded(
                    document_id=document_id,
                    filename=document_create.filename,
                    content_type=document_create.content_type,
                    size_bytes=len(file_data),
                    owner_id=user_id,
                    tenant_id=tenant_id,
                )
            except Exception as e:
                self.logger.warning(f"Failed to publish upload event: {e}")
            
            return UploadResponse(
                document_id=document_id,
                status=UploadStatus.COMPLETED,
                location=storage_location,
                uploaded_at=datetime.utcnow(),
                size_bytes=len(file_data),
                checksum=checksum,
            )
            
        except Exception as e:
            self.logger.error(f"Document upload failed: {e}")
            
            # Log audit failure
            async with get_db() as db:
                audit_log = AuditLog(
                    id=str(uuid.uuid4()),
                    document_id=document_id if 'document_id' in locals() else None,
                    action="upload",
                    user_id=user_id,
                    tenant_id=tenant_id,
                    request_id=session_id,
                    status="failure",
                    error_message=str(e),
                    audit_metadata={
                        "filename": document_create.filename,
                        "size_bytes": len(file_data),
                    },
                    created_at=datetime.utcnow(),
                )
                
                db.add(audit_log)
                await db.commit()
            
            raise
    
    async def get_document(
        self,
        document_id: str,
        user_id: str,
        tenant_id: str,
        include_content: bool = False,
        user_scopes: Optional[List[str]] = None,
    ) -> DocumentResponse:
        """Get a document by ID."""
        try:
            async with get_db() as db:
                # Query document with relationships
                query = select(Document).options(
                    selectinload(Document.storage_locations),
                    selectinload(Document.versions),
                    selectinload(Document.scan_results),
                ).where(
                    and_(
                        Document.id == document_id,
                        Document.tenant_id == tenant_id,
                        Document.status != DocumentStatus.DELETED,
                    )
                )
                
                result = await db.execute(query)
                document = result.scalar_one_or_none()
                
                if not document:
                    raise ValueError(f"Document not found: {document_id}")
                
                # Check permissions - allow owner or admin users
                has_admin_access = user_scopes and "doc.admin" in user_scopes
                if document.owner_id != user_id and not has_admin_access:
                    raise PermissionError("Access denied to document")
                
                # Get storage location
                storage_location = None
                for loc in document.storage_locations:
                    if loc.is_primary:
                        storage_location = loc
                        break
                
                if not storage_location:
                    raise ValueError("No storage location found for document")
                
                # Convert to response model
                metadata = DocumentMetadata(
                    document_id=str(document.id),
                    filename=document.filename,
                    content_type=document.content_type,
                    size_bytes=document.size_bytes,
                    owner_id=str(document.owner_id),
                    tenant_id=str(document.tenant_id),
                    tags=document.tags,
                    title=document.title,
                    description=document.description,
                    created_at=document.created_at,
                    updated_at=document.updated_at,
                    version=document.version,
                    status=document.status,
                    checksum=document.checksum,
                    attributes=document.attributes,
                )
                
                location = StorageLocation(
                    backend=storage_location.backend,
                    bucket=storage_location.bucket,
                    key=storage_location.key,
                    region=storage_location.region,
                    endpoint_url=storage_location.endpoint_url,
                )
                
                # Get versions
                versions = []
                for version in document.versions:
                    versions.append(VersionHistory(
                        version=version.version,
                        created_at=version.created_at,
                        created_by=str(version.created_by),
                        description=version.description,
                        size_bytes=version.size_bytes,
                        checksum=version.checksum,
                        location=StorageLocation(
                            backend=version.backend,
                            bucket=version.bucket,
                            key=version.key,
                            region=version.region,
                            endpoint_url=version.endpoint_url,
                        ),
                    ))
                
                # Get latest scan result if available
                last_scan = None
                if document.scan_results:
                    latest_scan = max(document.scan_results, key=lambda x: x.started_at)
                    if latest_scan.status == ScanStatus.COMPLETED:
                        threats = []
                        for threat in latest_scan.threats:
                            threats.append(ThreatDetail(
                                name=threat.name,
                                type=threat.type,
                                severity=threat.severity,
                                description=threat.description,
                            ))
                        
                        last_scan = ScanResultModel(
                            scan_id=latest_scan.scan_id,
                            document_id=latest_scan.document_id,
                            status=latest_scan.status,
                            result=latest_scan.result,
                            scanned_at=latest_scan.completed_at or latest_scan.started_at,
                            duration_ms=latest_scan.duration_ms or 0,
                            threats=threats,
                            scanner_version=latest_scan.scanner_version,
                        )
                
                # Create audit log
                audit_log = AuditLog(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    action="get",
                    user_id=user_id,
                    tenant_id=tenant_id,
                    status="success",
                    created_at=datetime.utcnow(),
                )
                
                db.add(audit_log)
                await db.commit()
                
                return DocumentResponse(
                    metadata=metadata,
                    location=location,
                    versions=versions,
                    last_scan=last_scan,
                )
                
        except Exception as e:
            self.logger.error(f"Get document failed: {e}")
            
            # Log audit failure
            async with get_db() as db:
                audit_log = AuditLog(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    action="get",
                    user_id=user_id,
                    tenant_id=tenant_id,
                    status="failure",
                    error_message=str(e),
                    created_at=datetime.utcnow(),
                )
                
                db.add(audit_log)
                await db.commit()
            
            raise
    
    async def delete_document(
        self,
        document_id: str,
        user_id: str,
        tenant_id: str,
        user_scopes: Optional[List[str]] = None,
    ) -> bool:
        """Soft delete a document."""
        try:
            async with get_db() as db:
                # Query document
                query = select(Document).options(
                    selectinload(Document.storage_locations),
                ).where(
                    and_(
                        Document.id == document_id,
                        Document.tenant_id == tenant_id,
                        Document.status != DocumentStatus.DELETED,
                    )
                )
                
                result = await db.execute(query)
                document = result.scalar_one_or_none()
                
                if not document:
                    raise ValueError(f"Document not found: {document_id}")
                
                # Check permissions - allow owner or admin users
                has_admin_access = user_scopes and "doc.admin" in user_scopes
                if document.owner_id != user_id and not has_admin_access:
                    raise PermissionError("Access denied to document")
                
                # Soft delete
                document.status = DocumentStatus.DELETED
                document.updated_at = datetime.utcnow()
                
                # Create audit log
                audit_log = AuditLog(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    action="delete",
                    user_id=user_id,
                    tenant_id=tenant_id,
                    status="success",
                    created_at=datetime.utcnow(),
                )
                
                db.add(audit_log)
                await db.commit()
                
                # Log event
                log_document_event(
                    self.logger,
                    "document_deleted",
                    document_id,
                    tenant_id,
                    user_id,
                )
                
                # Publish event
                try:
                    await event_publisher.publish_document_deleted(
                        document_id=document_id,
                        filename=document.filename,
                        owner_id=user_id,
                        tenant_id=tenant_id,
                    )
                except Exception as e:
                    self.logger.warning(f"Failed to publish delete event: {e}")
                
                return True
                
        except Exception as e:
            self.logger.error(f"Delete document failed: {e}")
            
            # Log audit failure
            async with get_db() as db:
                audit_log = AuditLog(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    action="delete",
                    user_id=user_id,
                    tenant_id=tenant_id,
                    status="failure",
                    error_message=str(e),
                    created_at=datetime.utcnow(),
                )
                
                db.add(audit_log)
                await db.commit()
            
            raise
    
    async def update_document(
        self,
        document_id: str,
        document_update: DocumentUpdate,
        user_id: str,
        tenant_id: str,
    ) -> DocumentResponse:
        """Update a document's metadata."""
        try:
            async with get_db() as db:
                # Query document
                query = select(Document).where(
                    and_(
                        Document.id == document_id,
                        Document.tenant_id == tenant_id,
                        Document.status != DocumentStatus.DELETED,
                    )
                )
                
                result = await db.execute(query)
                document = result.scalar_one_or_none()
                
                if not document:
                    raise ValueError(f"Document not found: {document_id}")
                
                # Check permissions
                if document.owner_id != user_id:
                    raise PermissionError("Access denied to document")
                
                # Update document fields
                if document_update.title is not None:
                    document.title = document_update.title
                if document_update.description is not None:
                    document.description = document_update.description
                if document_update.tags is not None:
                    document.tags = document_update.tags
                if document_update.attributes is not None:
                    document.attributes = document_update.attributes
                
                document.updated_at = datetime.utcnow()
                
                # Create audit log
                audit_log = AuditLog(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    action="update",
                    user_id=user_id,
                    tenant_id=tenant_id,
                    status="success",
                    audit_metadata={
                        "title": document_update.title,
                        "description": document_update.description,
                        "tags": document_update.tags,
                        "attributes": document_update.attributes,
                    },
                    created_at=datetime.utcnow(),
                )
                
                db.add(audit_log)
                await db.commit()
                
                # Log event
                log_document_event(
                    self.logger,
                    "document_updated",
                    document_id,
                    tenant_id,
                    user_id,
                )
                
                # Publish event
                try:
                    await event_publisher.publish_document_updated(
                        document_id=document_id,
                        filename=document.filename,
                        owner_id=user_id,
                        tenant_id=tenant_id,
                        changes={
                            "title": document_update.title,
                            "description": document_update.description,
                            "tags": document_update.tags,
                            "attributes": document_update.attributes,
                        },
                    )
                except Exception as e:
                    self.logger.warning(f"Failed to publish update event: {e}")
                
                # Return updated document
                return await self.get_document(
                    document_id=document_id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                )
                
        except Exception as e:
            self.logger.error(f"Update document failed: {e}")
            
            # Log audit failure
            async with get_db() as db:
                audit_log = AuditLog(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    action="update",
                    user_id=user_id,
                    tenant_id=tenant_id,
                    status="failure",
                    error_message=str(e),
                    created_at=datetime.utcnow(),
                )
                
                db.add(audit_log)
                await db.commit()
            
            raise
    
    async def get_scan_result(
        self,
        document_id: str,
        scan_id: str,
        user_id: str,
        tenant_id: str,
    ) -> ScanResultModel:
        """Get a scan result by scan ID."""
        try:
            async with get_db() as db:
                # Query document first to check permissions
                doc_query = select(Document).where(
                    and_(
                        Document.id == document_id,
                        Document.tenant_id == tenant_id,
                        Document.status != DocumentStatus.DELETED,
                    )
                )
                
                doc_result = await db.execute(doc_query)
                document = doc_result.scalar_one_or_none()
                
                if not document:
                    raise ValueError(f"Document not found: {document_id}")
                
                # Check permissions
                if document.owner_id != user_id:
                    raise PermissionError("Access denied to document")
                
                # Query scan result
                from app.models.database import ScanResult, ThreatDetail
                scan_query = select(ScanResult).where(
                    and_(
                        ScanResult.document_id == document_id,
                        ScanResult.scan_id == scan_id,
                    )
                )
                
                scan_result = await db.execute(scan_query)
                scan = scan_result.scalar_one_or_none()
                
                if not scan:
                    raise ValueError(f"Scan result not found: {scan_id}")
                
                # Get threats
                threats = []
                for threat in scan.threats:
                    threats.append(ThreatDetail(
                        name=threat.name,
                        type=threat.type,
                        severity=threat.severity,
                        description=threat.description,
                    ))
                
                # Create audit log
                audit_log = AuditLog(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    action="get_scan_result",
                    user_id=user_id,
                    tenant_id=tenant_id,
                    status="success",
                    audit_metadata={"scan_id": scan_id},
                    created_at=datetime.utcnow(),
                )
                
                db.add(audit_log)
                await db.commit()
                
                return ScanResultModel(
                    scan_id=scan.scan_id,
                    document_id=scan.document_id,
                    status=scan.status,
                    result=scan.result,
                    scanned_at=scan.completed_at or scan.started_at,
                    duration_ms=scan.duration_ms or 0,
                    threats=threats,
                    scanner_version=scan.scanner_version,
                )
                
        except Exception as e:
            self.logger.error(f"Get scan result failed: {e}")
            
            # Log audit failure
            async with get_db() as db:
                audit_log = AuditLog(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    action="get_scan_result",
                    user_id=user_id,
                    tenant_id=tenant_id,
                    status="failure",
                    error_message=str(e),
                    audit_metadata={"scan_id": scan_id},
                    created_at=datetime.utcnow(),
                )
                
                db.add(audit_log)
                await db.commit()
            
            raise
    
    async def list_documents(
        self,
        request: DocumentListRequest,
        user_id: str,
        tenant_id: str,
    ) -> DocumentListResponse:
        """List documents."""
        try:
            async with get_db() as db:
                # Build query
                query = select(Document).where(
                    and_(
                        Document.tenant_id == tenant_id,
                        Document.status != DocumentStatus.DELETED,
                    )
                )
                
                # Filter by user if specified
                if request.user_id:
                    query = query.where(Document.owner_id == request.user_id)
                
                # Filter by tags
                if request.tags:
                    query = query.where(Document.tags.contains(request.tags))
                
                # Filter by status
                if request.status:
                    query = query.where(Document.status == request.status)
                
                # Filter by date range
                if request.date_range:
                    if request.date_range.start_date:
                        query = query.where(Document.created_at >= request.date_range.start_date)
                    if request.date_range.end_date:
                        query = query.where(Document.created_at <= request.date_range.end_date)
                
                # Get total count
                count_query = select(func.count()).select_from(query.subquery())
                total_result = await db.execute(count_query)
                total_count = total_result.scalar()
                
                # Add sorting
                if request.sort_by == "created_at":
                    order_col = Document.created_at
                elif request.sort_by == "updated_at":
                    order_col = Document.updated_at
                elif request.sort_by == "filename":
                    order_col = Document.filename
                else:
                    order_col = Document.created_at
                
                if request.sort_order.value == "desc":
                    query = query.order_by(desc(order_col))
                else:
                    query = query.order_by(order_col)
                
                # Add pagination
                query = query.offset(request.offset).limit(request.limit)
                
                # Execute query
                result = await db.execute(query)
                documents = result.scalars().all()
                
                # Convert to response models
                document_list = []
                for doc in documents:
                    metadata = DocumentMetadata(
                        document_id=str(doc.id),
                        filename=doc.filename,
                        content_type=doc.content_type,
                        size_bytes=doc.size_bytes,
                        owner_id=str(doc.owner_id),
                        tenant_id=str(doc.tenant_id),
                        tags=doc.tags,
                        title=doc.title,
                        description=doc.description,
                        created_at=doc.created_at,
                        updated_at=doc.updated_at,
                        version=doc.version,
                        status=doc.status,
                        checksum=doc.checksum,
                        attributes=doc.attributes,
                    )
                    document_list.append(metadata)
                
                # Calculate pagination info
                has_more = (request.offset + len(documents)) < total_count
                next_token = None
                if has_more:
                    next_token = str(request.offset + request.limit)
                
                return DocumentListResponse(
                    documents=document_list,
                    total_count=total_count,
                    has_more=has_more,
                    next_token=next_token,
                )
                
        except Exception as e:
            self.logger.error(f"List documents failed: {e}")
            raise


# Global document service instance
document_service = DocumentService()