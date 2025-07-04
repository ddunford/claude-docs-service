"""S3/MinIO storage backend implementation."""

import asyncio
from datetime import datetime
from typing import Optional, AsyncIterator, Dict, Any
import io

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from botocore.config import Config
import aioboto3

from app.config import settings
from app.models.document import StorageLocation, StorageBackend as StorageBackendEnum
from app.storage.base import (
    StorageBackend,
    StorageError,
    FileNotFoundError,
    StorageConnectionError,
    StoragePermissionError,
    StorageQuotaError,
)
from app.utils.logging import get_logger


class S3StorageBackend(StorageBackend):
    """S3/MinIO storage backend implementation."""
    
    def __init__(self):
        """Initialize S3 storage backend."""
        self.logger = get_logger(self.__class__.__name__)
        self.bucket_name = settings.S3_BUCKET_NAME
        self.region = settings.S3_REGION
        self.endpoint_url = settings.S3_ENDPOINT_URL
        
        # Create boto3 config
        self.config = Config(
            region_name=self.region,
            retries={"max_attempts": 3, "mode": "adaptive"},
            max_pool_connections=50,
        )
        
        # Create async session
        self.session = aioboto3.Session(
            aws_access_key_id=settings.S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
            region_name=self.region,
        )
    
    def _get_client_kwargs(self) -> Dict[str, Any]:
        """Get client kwargs for boto3."""
        kwargs = {
            "config": self.config,
            "aws_access_key_id": settings.S3_ACCESS_KEY_ID,
            "aws_secret_access_key": settings.S3_SECRET_ACCESS_KEY,
            "region_name": self.region,
        }
        
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
        
        return kwargs
    
    async def _handle_client_error(self, error: ClientError, operation: str) -> None:
        """Handle boto3 client errors."""
        error_code = error.response.get("Error", {}).get("Code", "Unknown")
        error_message = error.response.get("Error", {}).get("Message", str(error))
        
        self.logger.error(f"S3 {operation} failed: {error_code} - {error_message}")
        
        if error_code == "NoSuchKey":
            raise FileNotFoundError(f"File not found: {error_message}")
        elif error_code == "AccessDenied":
            raise StoragePermissionError(f"Access denied: {error_message}")
        elif error_code == "QuotaExceeded":
            raise StorageQuotaError(f"Quota exceeded: {error_message}")
        elif error_code in ["NoSuchBucket", "BucketNotFound"]:
            raise StorageConnectionError(f"Bucket not found: {error_message}")
        else:
            raise StorageError(f"S3 {operation} failed: {error_message}")
    
    async def upload_file(
        self,
        file_data: bytes,
        key: str,
        content_type: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> StorageLocation:
        """Upload a file to S3."""
        try:
            async with self.session.client("s3", **self._get_client_kwargs()) as s3:
                # Prepare upload parameters
                upload_params = {
                    "Bucket": self.bucket_name,
                    "Key": key,
                    "Body": file_data,
                    "ContentType": content_type,
                }
                
                # Add metadata if provided
                if metadata:
                    upload_params["Metadata"] = metadata
                
                # Upload file
                await s3.put_object(**upload_params)
                
                self.logger.info(f"File uploaded successfully: {key}")
                
                # Return storage location
                return StorageLocation(
                    backend=StorageBackendEnum.S3 if not self.endpoint_url else StorageBackendEnum.MINIO,
                    bucket=self.bucket_name,
                    key=key,
                    region=self.region,
                    endpoint_url=self.endpoint_url,
                )
                
        except ClientError as e:
            await self._handle_client_error(e, "upload")
        except Exception as e:
            self.logger.error(f"Unexpected error during upload: {e}")
            raise StorageError(f"Upload failed: {str(e)}")
    
    async def download_file(self, location: StorageLocation) -> bytes:
        """Download a file from S3."""
        try:
            async with self.session.client("s3", **self._get_client_kwargs()) as s3:
                response = await s3.get_object(
                    Bucket=location.bucket,
                    Key=location.key,
                )
                
                # Read all data
                data = await response["Body"].read()
                
                self.logger.info(f"File downloaded successfully: {location.key}")
                return data
                
        except ClientError as e:
            await self._handle_client_error(e, "download")
        except Exception as e:
            self.logger.error(f"Unexpected error during download: {e}")
            raise StorageError(f"Download failed: {str(e)}")
    
    async def download_file_stream(self, location: StorageLocation) -> AsyncIterator[bytes]:
        """Download a file from S3 as a stream."""
        try:
            async with self.session.client("s3", **self._get_client_kwargs()) as s3:
                response = await s3.get_object(
                    Bucket=location.bucket,
                    Key=location.key,
                )
                
                # Stream data in chunks
                async for chunk in response["Body"].iter_chunks(chunk_size=8192):
                    yield chunk
                
                self.logger.info(f"File streamed successfully: {location.key}")
                
        except ClientError as e:
            await self._handle_client_error(e, "download_stream")
        except Exception as e:
            self.logger.error(f"Unexpected error during stream download: {e}")
            raise StorageError(f"Stream download failed: {str(e)}")
    
    async def delete_file(self, location: StorageLocation) -> bool:
        """Delete a file from S3."""
        try:
            async with self.session.client("s3", **self._get_client_kwargs()) as s3:
                await s3.delete_object(
                    Bucket=location.bucket,
                    Key=location.key,
                )
                
                self.logger.info(f"File deleted successfully: {location.key}")
                return True
                
        except ClientError as e:
            await self._handle_client_error(e, "delete")
        except Exception as e:
            self.logger.error(f"Unexpected error during deletion: {e}")
            raise StorageError(f"Delete failed: {str(e)}")
    
    async def file_exists(self, location: StorageLocation) -> bool:
        """Check if a file exists in S3."""
        try:
            async with self.session.client("s3", **self._get_client_kwargs()) as s3:
                await s3.head_object(
                    Bucket=location.bucket,
                    Key=location.key,
                )
                return True
                
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "NoSuchKey":
                return False
            await self._handle_client_error(e, "file_exists")
        except Exception as e:
            self.logger.error(f"Unexpected error checking file existence: {e}")
            raise StorageError(f"File existence check failed: {str(e)}")
    
    async def get_file_metadata(self, location: StorageLocation) -> Dict[str, Any]:
        """Get file metadata from S3."""
        try:
            async with self.session.client("s3", **self._get_client_kwargs()) as s3:
                response = await s3.head_object(
                    Bucket=location.bucket,
                    Key=location.key,
                )
                
                metadata = {
                    "size": response.get("ContentLength", 0),
                    "content_type": response.get("ContentType", ""),
                    "last_modified": response.get("LastModified"),
                    "etag": response.get("ETag", "").strip('"'),
                    "metadata": response.get("Metadata", {}),
                }
                
                self.logger.info(f"File metadata retrieved: {location.key}")
                return metadata
                
        except ClientError as e:
            await self._handle_client_error(e, "get_metadata")
        except Exception as e:
            self.logger.error(f"Unexpected error getting metadata: {e}")
            raise StorageError(f"Get metadata failed: {str(e)}")
    
    async def generate_presigned_url(
        self,
        location: StorageLocation,
        expiration_seconds: int = 3600,
        operation: str = "get",
    ) -> str:
        """Generate a presigned URL for file access."""
        try:
            async with self.session.client("s3", **self._get_client_kwargs()) as s3:
                # Map operation to S3 method
                method_map = {
                    "get": "get_object",
                    "put": "put_object",
                    "delete": "delete_object",
                }
                
                if operation not in method_map:
                    raise ValueError(f"Unsupported operation: {operation}")
                
                url = await s3.generate_presigned_url(
                    method_map[operation],
                    Params={
                        "Bucket": location.bucket,
                        "Key": location.key,
                    },
                    ExpiresIn=expiration_seconds,
                )
                
                self.logger.info(f"Presigned URL generated for {operation}: {location.key}")
                return url
                
        except ClientError as e:
            await self._handle_client_error(e, "generate_presigned_url")
        except Exception as e:
            self.logger.error(f"Unexpected error generating presigned URL: {e}")
            raise StorageError(f"Presigned URL generation failed: {str(e)}")
    
    async def list_files(
        self,
        prefix: str = "",
        limit: int = 1000,
        continuation_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List files in S3."""
        try:
            async with self.session.client("s3", **self._get_client_kwargs()) as s3:
                params = {
                    "Bucket": self.bucket_name,
                    "MaxKeys": limit,
                }
                
                if prefix:
                    params["Prefix"] = prefix
                
                if continuation_token:
                    params["ContinuationToken"] = continuation_token
                
                response = await s3.list_objects_v2(**params)
                
                files = []
                for obj in response.get("Contents", []):
                    files.append({
                        "key": obj["Key"],
                        "size": obj["Size"],
                        "last_modified": obj["LastModified"],
                        "etag": obj.get("ETag", "").strip('"'),
                    })
                
                result = {
                    "files": files,
                    "is_truncated": response.get("IsTruncated", False),
                    "next_continuation_token": response.get("NextContinuationToken"),
                }
                
                self.logger.info(f"Listed {len(files)} files with prefix: {prefix}")
                return result
                
        except ClientError as e:
            await self._handle_client_error(e, "list_files")
        except Exception as e:
            self.logger.error(f"Unexpected error listing files: {e}")
            raise StorageError(f"List files failed: {str(e)}")
    
    async def copy_file(
        self,
        source_location: StorageLocation,
        destination_location: StorageLocation,
    ) -> bool:
        """Copy a file within S3."""
        try:
            async with self.session.client("s3", **self._get_client_kwargs()) as s3:
                copy_source = {
                    "Bucket": source_location.bucket,
                    "Key": source_location.key,
                }
                
                await s3.copy_object(
                    CopySource=copy_source,
                    Bucket=destination_location.bucket,
                    Key=destination_location.key,
                )
                
                self.logger.info(
                    f"File copied from {source_location.key} to {destination_location.key}"
                )
                return True
                
        except ClientError as e:
            await self._handle_client_error(e, "copy")
        except Exception as e:
            self.logger.error(f"Unexpected error copying file: {e}")
            raise StorageError(f"Copy failed: {str(e)}")
    
    async def health_check(self) -> bool:
        """Check if the S3 backend is healthy."""
        try:
            async with self.session.client("s3", **self._get_client_kwargs()) as s3:
                await s3.head_bucket(Bucket=self.bucket_name)
                return True
                
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            self.logger.error(f"S3 health check failed: {error_code}")
            return False
        except Exception as e:
            self.logger.error(f"S3 health check failed: {e}")
            return False