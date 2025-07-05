"""REST API routes for the document service."""

import io
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
    Query,
)
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from app.auth.dependencies import (
    get_current_user,
    get_user_with_read_access,
    get_user_with_write_access,
    get_user_with_admin_access,
    # Testing dependencies
    get_mock_user_with_read_access,
    get_mock_user_with_write_access,
    get_mock_user_with_admin_access,
)
from app.auth.jwt_utils import AuthenticatedUser
from app.config import settings
from app.models.document import (
    DocumentCreate,
    DocumentUpdate,
    DocumentListRequest,
    DocumentListResponse,
    DocumentResponse,
    UploadResponse,
    ErrorResponse,
    HealthResponse,
    DateRange,
    SortOrder,
    DocumentStatus,
)
from app.services.document_service import document_service
from app.services.virus_scanner import virus_scanner
from app.services.event_publisher import event_publisher
from app.storage.factory import get_storage_backend
from app.utils.logging import get_logger, log_document_event

logger = get_logger(__name__)
router = APIRouter()
storage_backend = get_storage_backend()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    # Check dependencies
    dependencies = {}
    
    # Check virus scanner
    try:
        virus_healthy = await virus_scanner.health_check()
        dependencies["virus_scanner"] = "healthy" if virus_healthy else "unhealthy"
    except Exception as e:
        dependencies["virus_scanner"] = f"error: {str(e)}"
    
    # Check event publisher
    try:
        event_healthy = await event_publisher.health_check()
        dependencies["event_publisher"] = "healthy" if event_healthy else "unhealthy"
    except Exception as e:
        dependencies["event_publisher"] = f"error: {str(e)}"
    
    # Check storage backend
    try:
        storage_healthy = await storage_backend.health_check()
        dependencies["storage_backend"] = "healthy" if storage_healthy else "unhealthy"
    except Exception as e:
        dependencies["storage_backend"] = f"error: {str(e)}"
    
    return HealthResponse(
        status="healthy",
        service="document-service",
        version="0.1.0",
        timestamp=datetime.utcnow(),
        dependencies=dependencies,
    )


@router.get("/metrics")
async def metrics():
    """Metrics endpoint for Prometheus."""
    # Basic metrics - in production this would be handled by prometheus_client
    return {
        "service": "document-service",
        "version": "0.1.0",
        "timestamp": datetime.utcnow().isoformat(),
        "metrics": {
            "requests_total": 0,  # TODO: Implement proper metrics
            "documents_uploaded_total": 0,
            "documents_scanned_total": 0,
            "storage_bytes_total": 0,
        },
    }


@router.post("/documents/upload")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    attributes: Optional[str] = Form(None),
    user: AuthenticatedUser = Depends(get_mock_user_with_write_access),
):
    """Upload a document via REST API."""
    try:
        # Validate file size
        file_size = 0
        file_data = b""
        
        # Read file data
        chunk_size = 8192
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            file_data += chunk
            file_size += len(chunk)
            
            # Check file size limit
            if file_size > settings.max_file_size_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File size exceeds maximum allowed size of {settings.MAX_FILE_SIZE_MB}MB",
                )
        
        # Validate file type
        if file.content_type:
            file_extension = file.filename.split(".")[-1].lower() if file.filename else ""
            if file_extension not in settings.ALLOWED_FILE_TYPES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File type '{file_extension}' not allowed. Allowed types: {settings.ALLOWED_FILE_TYPES}",
                )
        
        # Parse additional fields
        tags_list = []
        if tags:
            tags_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
        
        attributes_dict = {}
        if attributes:
            import json
            try:
                attributes_dict = json.loads(attributes)
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid JSON format for attributes",
                )
        
        # Create document metadata
        document_create = DocumentCreate(
            filename=file.filename or f"upload_{uuid.uuid4().hex}",
            content_type=file.content_type or "application/octet-stream",
            title=title,
            description=description,
            tags=tags_list,
            attributes=attributes_dict,
        )
        
        # Upload document
        result = await document_service.upload_document(
            file_data=file_data,
            document_create=document_create,
            user_id=user.user_id,
            tenant_id=user.tenant_id,
        )
        
        # Publish event 
        try:
            await event_publisher.publish_document_uploaded(
                document_id=result.document_id,
                filename=document_create.filename,
                content_type=document_create.content_type,
                size_bytes=file_size,
                owner_id=user.user_id,
                tenant_id=user.tenant_id,
            )
        except Exception as e:
            logger.warning(f"Failed to publish upload event: {e}")
        
        # Log event
        log_document_event(
            logger,
            "document_uploaded",
            result.document_id,
            user.tenant_id,
            user.user_id,
            filename=document_create.filename,
            size_bytes=file_size,
        )
        
        # Return response in format expected by UI
        return {
            "id": result.document_id,
            "document_id": result.document_id,  # Keep both for compatibility
            "filename": document_create.filename,
            "size": file_size,
            "size_bytes": file_size,  # Keep both for compatibility
            "status": result.status,
            "location": result.location,
            "uploaded_at": result.uploaded_at,
            "checksum": result.checksum
        }
        
    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Validation error: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Document upload failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during upload",
        )


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    include_content: bool = Query(False, description="Include file content in response"),
    user: AuthenticatedUser = Depends(get_mock_user_with_read_access),
):
    """Get a document by ID via REST API."""
    try:
        # Get document metadata
        document = await document_service.get_document(
            document_id=document_id,
            user_id=user.user_id,
            tenant_id=user.tenant_id,
            include_content=include_content,
            user_scopes=user.scopes,
        )
        
        # Log event
        log_document_event(
            logger,
            "document_retrieved",
            document_id,
            user.tenant_id,
            user.user_id,
        )
        
        return document
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Get document failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: str,
    user: AuthenticatedUser = Depends(get_mock_user_with_read_access),
):
    """Download a document by ID via REST API."""
    try:
        # Get document metadata
        document = await document_service.get_document(
            document_id=document_id,
            user_id=user.user_id,
            tenant_id=user.tenant_id,
            user_scopes=user.scopes,
        )
        
        # Download file from storage
        file_data = await storage_backend.download_file(document.location)
        
        # Create streaming response
        file_stream = io.BytesIO(file_data)
        
        # Log event
        log_document_event(
            logger,
            "document_downloaded",
            document_id,
            user.tenant_id,
            user.user_id,
            filename=document.metadata.filename,
        )
        
        return StreamingResponse(
            io.BytesIO(file_data),
            media_type=document.metadata.content_type,
            headers={
                "Content-Disposition": f"attachment; filename={document.metadata.filename}",
                "Content-Length": str(len(file_data)),
            },
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Download document failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.put("/documents/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: str,
    document_update: DocumentUpdate,
    user: AuthenticatedUser = Depends(get_mock_user_with_write_access),
):
    """Update a document by ID via REST API."""
    try:
        # Update document using service
        updated_document = await document_service.update_document(
            document_id=document_id,
            document_update=document_update,
            user_id=user.user_id,
            tenant_id=user.tenant_id,
        )
        
        # Log event
        log_document_event(
            logger,
            "document_updated",
            document_id,
            user.tenant_id,
            user.user_id,
        )
        
        return updated_document
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Update document failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    user: AuthenticatedUser = Depends(get_mock_user_with_write_access),
):
    """Delete a document by ID via REST API."""
    try:
        # Get document metadata first for event publishing
        document = await document_service.get_document(
            document_id=document_id,
            user_id=user.user_id,
            tenant_id=user.tenant_id,
            user_scopes=user.scopes,
        )
        
        # Delete document
        success = await document_service.delete_document(
            document_id=document_id,
            user_id=user.user_id,
            tenant_id=user.tenant_id,
            user_scopes=user.scopes,
        )
        
        if success:
            # Publish event
            await event_publisher.publish_document_deleted(
                document_id=document_id,
                filename=document.metadata.filename,
                owner_id=user.user_id,
                tenant_id=user.tenant_id,
            )
            
            # Log event
            log_document_event(
                logger,
                "document_deleted",
                document_id,
                user.tenant_id,
                user.user_id,
                filename=document.metadata.filename,
            )
            
            return {"message": "Document deleted successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete document",
            )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Delete document failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/documents")
async def list_documents(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    tags: Optional[str] = Query(None, description="Filter by tags (comma-separated)"),
    doc_status: Optional[DocumentStatus] = Query(None, description="Filter by status"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=1000, description="Pagination limit"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: SortOrder = Query(SortOrder.DESC, description="Sort order"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date"),
    user: AuthenticatedUser = Depends(get_mock_user_with_read_access),
):
    """List documents via REST API."""
    try:
        # For testing, let's query the database directly
        from app.database import get_db
        from app.models.database import Document
        from sqlalchemy import select
        
        async with get_db() as db:
            # Simple query to get documents
            query = select(Document).where(
                Document.tenant_id == user.tenant_id,
                Document.status != DocumentStatus.DELETED
            ).limit(limit).offset(offset)
            
            result = await db.execute(query)
            documents = result.scalars().all()
            
            # Convert to simple dict format
            doc_list = []
            for doc in documents:
                doc_list.append({
                    "id": str(doc.id),
                    "filename": doc.filename,
                    "content_type": doc.content_type,
                    "size": doc.size_bytes,
                    "size_bytes": doc.size_bytes,
                    "document_type": "document",  # Default type
                    "description": doc.description,
                    "status": doc.status,
                    "created_at": doc.created_at.isoformat() if doc.created_at else None,
                    "updated_at": doc.updated_at.isoformat() if doc.updated_at else None
                })
            
            return {
                "documents": doc_list,
                "total_count": len(doc_list),
                "offset": offset,
                "limit": limit,
                "has_more": len(doc_list) == limit
            }
        
    except Exception as e:
        logger.error(f"List documents failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )


@router.post("/documents/{document_id}/scan")
async def scan_document(
    document_id: str,
    user: AuthenticatedUser = Depends(get_mock_user_with_admin_access),
):
    """Trigger virus scan for a document via REST API."""
    try:
        # Get document metadata
        document = await document_service.get_document(
            document_id=document_id,
            user_id=user.user_id,
            tenant_id=user.tenant_id,
            user_scopes=user.scopes,
        )
        
        # Download file for scanning
        file_data = await storage_backend.download_file(document.location)
        
        # Perform virus scan
        scan_result = await virus_scanner.scan_bytes(
            data=file_data,
            document_id=document_id,
        )
        
        # Publish event
        await event_publisher.publish_document_scanned(
            document_id=document_id,
            scan_id=scan_result.scan_id,
            result=scan_result.result,
            threats=[threat.dict() for threat in scan_result.threats],
            tenant_id=user.tenant_id,
        )
        
        # Log event
        log_document_event(
            logger,
            "document_scanned",
            document_id,
            user.tenant_id,
            user.user_id,
            scan_id=scan_result.scan_id,
            result=scan_result.result,
        )
        
        return {
            "message": "Document scan completed",
            "scan_id": scan_result.scan_id,
            "result": scan_result.result,
            "threats": [threat.dict() for threat in scan_result.threats],
            "duration_ms": scan_result.duration_ms,
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Scan document failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/documents/{document_id}/scan/{scan_id}")
async def get_scan_result(
    document_id: str,
    scan_id: str,
    user: AuthenticatedUser = Depends(get_mock_user_with_read_access),
):
    """Get scan result by ID via REST API."""
    try:
        # Get scan result using service
        scan_result = await document_service.get_scan_result(
            document_id=document_id,
            scan_id=scan_id,
            user_id=user.user_id,
            tenant_id=user.tenant_id,
        )
        
        # Log event
        log_document_event(
            logger,
            "scan_result_retrieved",
            document_id,
            user.tenant_id,
            user.user_id,
            scan_id=scan_id,
        )
        
        return {
            "scan_id": scan_result.scan_id,
            "document_id": scan_result.document_id,
            "status": scan_result.status,
            "result": scan_result.result if scan_result.result else None,
            "scanned_at": scan_result.scanned_at.isoformat() if scan_result.scanned_at else None,
            "duration_ms": scan_result.duration_ms,
            "threats": [threat.dict() for threat in scan_result.threats],
            "scanner_version": scan_result.scanner_version,
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Get scan result failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )