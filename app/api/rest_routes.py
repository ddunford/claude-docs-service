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


@router.post("/documents/upload", response_model=UploadResponse)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    attributes: Optional[str] = Form(None),
    user: AuthenticatedUser = Depends(get_user_with_write_access),
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
        await event_publisher.publish_document_uploaded(
            document_id=result.document_id,
            filename=document_create.filename,
            content_type=document_create.content_type,
            size_bytes=file_size,
            owner_id=user.user_id,
            tenant_id=user.tenant_id,
        )
        
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
        
        return result
        
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
    user: AuthenticatedUser = Depends(get_user_with_read_access),
):
    """Get a document by ID via REST API."""
    try:
        # Get document metadata
        document = await document_service.get_document(
            document_id=document_id,
            user_id=user.user_id,
            tenant_id=user.tenant_id,
            include_content=include_content,
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
    user: AuthenticatedUser = Depends(get_user_with_read_access),
):
    """Download a document by ID via REST API."""
    try:
        # Get document metadata
        document = await document_service.get_document(
            document_id=document_id,
            user_id=user.user_id,
            tenant_id=user.tenant_id,
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


@router.put("/documents/{document_id}")
async def update_document(
    document_id: str,
    document_update: DocumentUpdate,
    user: AuthenticatedUser = Depends(get_user_with_write_access),
):
    """Update a document by ID via REST API."""
    try:
        # TODO: Implement document update in document service
        # For now, return a placeholder response
        
        # Log event
        log_document_event(
            logger,
            "document_updated",
            document_id,
            user.tenant_id,
            user.user_id,
        )
        
        return {
            "message": "Document update endpoint - implementation pending",
            "document_id": document_id,
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
        logger.error(f"Update document failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    user: AuthenticatedUser = Depends(get_user_with_write_access),
):
    """Delete a document by ID via REST API."""
    try:
        # Get document metadata first for event publishing
        document = await document_service.get_document(
            document_id=document_id,
            user_id=user.user_id,
            tenant_id=user.tenant_id,
        )
        
        # Delete document
        success = await document_service.delete_document(
            document_id=document_id,
            user_id=user.user_id,
            tenant_id=user.tenant_id,
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


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    tags: Optional[str] = Query(None, description="Filter by tags (comma-separated)"),
    status: Optional[DocumentStatus] = Query(None, description="Filter by status"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=1000, description="Pagination limit"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: SortOrder = Query(SortOrder.DESC, description="Sort order"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date"),
    user: AuthenticatedUser = Depends(get_user_with_read_access),
):
    """List documents via REST API."""
    try:
        # Parse tags
        tags_list = []
        if tags:
            tags_list = [tag.strip().lower() for tag in tags.split(",") if tag.strip()]
        
        # Create date range
        date_range = None
        if start_date or end_date:
            date_range = DateRange(start_date=start_date, end_date=end_date)
        
        # Create request
        list_request = DocumentListRequest(
            user_id=user_id,
            tenant_id=user.tenant_id,
            tags=tags_list,
            status=status,
            offset=offset,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
            date_range=date_range,
        )
        
        # List documents
        result = await document_service.list_documents(
            request=list_request,
            user_id=user.user_id,
            tenant_id=user.tenant_id,
        )
        
        # Log event
        log_document_event(
            logger,
            "documents_listed",
            "bulk",
            user.tenant_id,
            user.user_id,
            count=len(result.documents),
        )
        
        return result
        
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Validation error: {str(e)}",
        )
    except Exception as e:
        logger.error(f"List documents failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/documents/{document_id}/scan")
async def scan_document(
    document_id: str,
    user: AuthenticatedUser = Depends(get_user_with_admin_access),
):
    """Trigger virus scan for a document via REST API."""
    try:
        # Get document metadata
        document = await document_service.get_document(
            document_id=document_id,
            user_id=user.user_id,
            tenant_id=user.tenant_id,
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
            result=scan_result.result.value,
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
            result=scan_result.result.value,
        )
        
        return {
            "message": "Document scan completed",
            "scan_id": scan_result.scan_id,
            "result": scan_result.result.value,
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
    user: AuthenticatedUser = Depends(get_user_with_read_access),
):
    """Get scan result by ID via REST API."""
    try:
        # TODO: Implement scan result retrieval from database
        # For now, return a placeholder response
        
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
            "message": "Scan result retrieval endpoint - implementation pending",
            "document_id": document_id,
            "scan_id": scan_id,
        }
        
    except Exception as e:
        logger.error(f"Get scan result failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )