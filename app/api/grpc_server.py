"""gRPC server configuration and service implementation."""

import asyncio
from typing import Optional
import traceback

import grpc
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer
from opentelemetry import trace
from google.protobuf.empty_pb2 import Empty

from app.config import settings
from app.utils.logging import get_logger
from app.services.document_service import document_service
from app.services.virus_scanner import virus_scanner
from app.storage.factory import get_storage_backend
from app.utils.protobuf_converters import (
    protobuf_upload_request_to_pydantic,
    pydantic_upload_response_to_protobuf,
    pydantic_document_response_to_protobuf,
    protobuf_list_request_to_pydantic,
    pydantic_document_list_response_to_protobuf,
    pydantic_scan_result_to_protobuf,
)
from docs.v1 import document_pb2_grpc
from docs.v1 import document_pb2 as pb

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)


class DocumentServiceServicer(document_pb2_grpc.DocumentServiceServicer):
    """gRPC service implementation for document operations."""
    
    def __init__(self):
        """Initialize the document service."""
        self.logger = get_logger(self.__class__.__name__)
        self.document_service = document_service
        self.virus_scanner = virus_scanner
    
    async def UploadDocument(self, request: pb.UploadRequest, context: grpc.ServicerContext) -> pb.UploadResponse:
        """Upload a document to storage."""
        with tracer.start_as_current_span("UploadDocument") as span:
            try:
                # Extract user info from context metadata
                metadata = dict(context.invocation_metadata())
                user_id = metadata.get('user-id', '')
                tenant_id = metadata.get('tenant-id', '')
                
                if not user_id or not tenant_id:
                    context.set_code(grpc.StatusCode.UNAUTHENTICATED)
                    context.set_details('Missing user-id or tenant-id in metadata')
                    return pb.UploadResponse()
                
                # Convert protobuf request to Pydantic models
                file_data, document_create, session_id = protobuf_upload_request_to_pydantic(request)
                
                # Validate file size
                if len(file_data) > settings.MAX_FILE_SIZE_BYTES:
                    context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                    context.set_details(f'File size {len(file_data)} exceeds maximum allowed size {settings.MAX_FILE_SIZE_BYTES}')
                    return pb.UploadResponse()
                
                # Add span attributes
                span.set_attribute("document.filename", document_create.filename)
                span.set_attribute("document.content_type", document_create.content_type)
                span.set_attribute("document.size_bytes", len(file_data))
                span.set_attribute("user.id", user_id)
                span.set_attribute("tenant.id", tenant_id)
                
                # Upload document
                upload_response = await self.document_service.upload_document(
                    file_data=file_data,
                    document_create=document_create,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    session_id=session_id,
                )
                
                # Convert response to protobuf
                protobuf_response = pydantic_upload_response_to_protobuf(upload_response)
                
                self.logger.info(f"Document uploaded successfully: {upload_response.document_id}")
                return protobuf_response
                
            except ValueError as e:
                self.logger.error(f"Upload validation error: {e}")
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details(str(e))
                return pb.UploadResponse()
            except PermissionError as e:
                self.logger.error(f"Upload permission error: {e}")
                context.set_code(grpc.StatusCode.PERMISSION_DENIED)
                context.set_details(str(e))
                return pb.UploadResponse()
            except Exception as e:
                self.logger.error(f"Upload error: {e}")
                self.logger.error(traceback.format_exc())
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details('Internal server error')
                return pb.UploadResponse()
    
    async def GetDocument(self, request: pb.DocumentIdRequest, context: grpc.ServicerContext) -> pb.DocumentResponse:
        """Fetch document metadata and content."""
        with tracer.start_as_current_span("GetDocument") as span:
            try:
                # Extract user info from context metadata
                metadata = dict(context.invocation_metadata())
                user_id = metadata.get('user-id', request.user_id)
                tenant_id = metadata.get('tenant-id', request.tenant_id)
                
                if not user_id or not tenant_id:
                    context.set_code(grpc.StatusCode.UNAUTHENTICATED)
                    context.set_details('Missing user-id or tenant-id')
                    return pb.DocumentResponse()
                
                # Add span attributes
                span.set_attribute("document.id", request.document_id)
                span.set_attribute("user.id", user_id)
                span.set_attribute("tenant.id", tenant_id)
                
                # Get document
                document_response = await self.document_service.get_document(
                    document_id=request.document_id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    include_content=False,  # Don't include content by default for performance
                )
                
                # Convert response to protobuf
                protobuf_response = pydantic_document_response_to_protobuf(document_response)
                
                self.logger.info(f"Document retrieved successfully: {request.document_id}")
                return protobuf_response
                
            except ValueError as e:
                self.logger.error(f"Get document validation error: {e}")
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(str(e))
                return pb.DocumentResponse()
            except PermissionError as e:
                self.logger.error(f"Get document permission error: {e}")
                context.set_code(grpc.StatusCode.PERMISSION_DENIED)
                context.set_details(str(e))
                return pb.DocumentResponse()
            except Exception as e:
                self.logger.error(f"Get document error: {e}")
                self.logger.error(traceback.format_exc())
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details('Internal server error')
                return pb.DocumentResponse()
    
    async def DeleteDocument(self, request: pb.DocumentIdRequest, context: grpc.ServicerContext) -> Empty:
        """Soft delete document (archival policy)."""
        with tracer.start_as_current_span("DeleteDocument") as span:
            try:
                # Extract user info from context metadata
                metadata = dict(context.invocation_metadata())
                user_id = metadata.get('user-id', request.user_id)
                tenant_id = metadata.get('tenant-id', request.tenant_id)
                
                if not user_id or not tenant_id:
                    context.set_code(grpc.StatusCode.UNAUTHENTICATED)
                    context.set_details('Missing user-id or tenant-id')
                    return Empty()
                
                # Add span attributes
                span.set_attribute("document.id", request.document_id)
                span.set_attribute("user.id", user_id)
                span.set_attribute("tenant.id", tenant_id)
                
                # Delete document
                success = await self.document_service.delete_document(
                    document_id=request.document_id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                )
                
                if success:
                    self.logger.info(f"Document deleted successfully: {request.document_id}")
                    return Empty()
                else:
                    context.set_code(grpc.StatusCode.INTERNAL)
                    context.set_details('Failed to delete document')
                    return Empty()
                    
            except ValueError as e:
                self.logger.error(f"Delete document validation error: {e}")
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(str(e))
                return Empty()
            except PermissionError as e:
                self.logger.error(f"Delete document permission error: {e}")
                context.set_code(grpc.StatusCode.PERMISSION_DENIED)
                context.set_details(str(e))
                return Empty()
            except Exception as e:
                self.logger.error(f"Delete document error: {e}")
                self.logger.error(traceback.format_exc())
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details('Internal server error')
                return Empty()
    
    async def ScanDocument(self, request: pb.DocumentIdRequest, context: grpc.ServicerContext) -> pb.ScanResult:
        """Trigger AV scan, returns status."""
        with tracer.start_as_current_span("ScanDocument") as span:
            try:
                # Extract user info from context metadata
                metadata = dict(context.invocation_metadata())
                user_id = metadata.get('user-id', request.user_id)
                tenant_id = metadata.get('tenant-id', request.tenant_id)
                
                if not user_id or not tenant_id:
                    context.set_code(grpc.StatusCode.UNAUTHENTICATED)
                    context.set_details('Missing user-id or tenant-id')
                    return pb.ScanResult()
                
                # Add span attributes
                span.set_attribute("document.id", request.document_id)
                span.set_attribute("user.id", user_id)
                span.set_attribute("tenant.id", tenant_id)
                
                # Get document to scan
                document_response = await self.document_service.get_document(
                    document_id=request.document_id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    include_content=False,  # Don't need content in response
                )
                
                # Get file content from storage
                storage_backend = get_storage_backend()
                try:
                    file_content = await storage_backend.download_file(document_response.location)
                    self.logger.info(f"Downloaded file for scanning: {request.document_id}, size: {len(file_content)} bytes")
                except Exception as e:
                    self.logger.error(f"Failed to download file for scanning: {e}")
                    context.set_code(grpc.StatusCode.INTERNAL)
                    context.set_details(f'Failed to retrieve file for scanning: {str(e)}')
                    return pb.ScanResult()
                
                # Perform virus scan
                scan_result = await self.virus_scanner.scan_bytes(
                    data=file_content,
                    document_id=request.document_id,
                )
                
                # Convert response to protobuf
                protobuf_response = pydantic_scan_result_to_protobuf(scan_result)
                
                self.logger.info(f"Document scan completed: {request.document_id}, result: {scan_result.result}")
                return protobuf_response
                
            except ValueError as e:
                self.logger.error(f"Scan document validation error: {e}")
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(str(e))
                return pb.ScanResult()
            except PermissionError as e:
                self.logger.error(f"Scan document permission error: {e}")
                context.set_code(grpc.StatusCode.PERMISSION_DENIED)
                context.set_details(str(e))
                return pb.ScanResult()
            except Exception as e:
                self.logger.error(f"Scan document error: {e}")
                self.logger.error(traceback.format_exc())
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details('Internal server error')
                return pb.ScanResult()
    
    async def ListDocuments(self, request: pb.ListRequest, context: grpc.ServicerContext) -> pb.DocumentListResponse:
        """List documents by owner, tags, etc."""
        with tracer.start_as_current_span("ListDocuments") as span:
            try:
                # Extract user info from context metadata
                metadata = dict(context.invocation_metadata())
                user_id = metadata.get('user-id', request.user_id)
                tenant_id = metadata.get('tenant-id', request.tenant_id)
                
                if not user_id or not tenant_id:
                    context.set_code(grpc.StatusCode.UNAUTHENTICATED)
                    context.set_details('Missing user-id or tenant-id')
                    return pb.DocumentListResponse()
                
                # Add span attributes
                span.set_attribute("user.id", user_id)
                span.set_attribute("tenant.id", tenant_id)
                span.set_attribute("list.limit", request.limit)
                span.set_attribute("list.offset", request.offset)
                
                # Convert protobuf request to Pydantic
                list_request = protobuf_list_request_to_pydantic(request)
                
                # List documents
                list_response = await self.document_service.list_documents(
                    request=list_request,
                    user_id=user_id,
                    tenant_id=tenant_id,
                )
                
                # Convert response to protobuf
                protobuf_response = pydantic_document_list_response_to_protobuf(list_response)
                
                self.logger.info(f"Documents listed successfully: {len(list_response.documents)} documents")
                return protobuf_response
                
            except ValueError as e:
                self.logger.error(f"List documents validation error: {e}")
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details(str(e))
                return pb.DocumentListResponse()
            except Exception as e:
                self.logger.error(f"List documents error: {e}")
                self.logger.error(traceback.format_exc())
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details('Internal server error')
                return pb.DocumentListResponse()


def create_grpc_server() -> grpc.aio.Server:
    """Create and configure gRPC server."""
    # Instrument gRPC with OpenTelemetry
    GrpcInstrumentorServer().instrument()
    
    server = grpc.aio.server()
    
    # Add service to server
    document_pb2_grpc.add_DocumentServiceServicer_to_server(
        DocumentServiceServicer(), server
    )
    
    # Add server reflection for debugging
    from grpc_reflection.v1alpha import reflection
    from docs.v1 import document_pb2
    
    SERVICE_NAMES = (
        document_pb2.DESCRIPTOR.services_by_name['DocumentService'].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)
    
    logger.info("gRPC server created with DocumentService")
    return server