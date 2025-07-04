"""Redis client for session tracking and virus scan jobs."""

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import redis.asyncio as redis
from redis.asyncio import Redis

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class RedisClient:
    """Redis client for session tracking and virus scan jobs."""
    
    def __init__(self):
        """Initialize Redis client."""
        self.redis: Optional[Redis] = None
        self.logger = get_logger(self.__class__.__name__)
    
    async def connect(self) -> None:
        """Connect to Redis."""
        try:
            self.redis = redis.from_url(
                settings.REDIS_URL,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                decode_responses=True,
            )
            # Test connection
            await self.redis.ping()
            self.logger.info("Connected to Redis successfully")
        except Exception as e:
            self.logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self.redis:
            await self.redis.close()
            self.logger.info("Disconnected from Redis")
    
    async def health_check(self) -> bool:
        """Check Redis health."""
        try:
            if not self.redis:
                return False
            await self.redis.ping()
            return True
        except Exception as e:
            self.logger.error(f"Redis health check failed: {e}")
            return False
    
    # Upload Session Management
    async def create_upload_session(
        self,
        session_id: str,
        user_id: str,
        tenant_id: str,
        filename: str,
        content_type: str,
        expected_size: Optional[int] = None,
        ttl_minutes: int = 60,
    ) -> bool:
        """Create an upload session in Redis."""
        try:
            session_data = {
                "session_id": session_id,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "filename": filename,
                "content_type": content_type,
                "expected_size": expected_size,
                "uploaded_size": 0,
                "status": "pending",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }
            
            key = f"upload_session:{session_id}"
            await self.redis.setex(
                key,
                timedelta(minutes=ttl_minutes),
                json.dumps(session_data, default=str),
            )
            
            self.logger.info(f"Created upload session: {session_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create upload session {session_id}: {e}")
            return False
    
    async def get_upload_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get upload session data."""
        try:
            key = f"upload_session:{session_id}"
            data = await self.redis.get(key)
            if data:
                return json.loads(data)
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to get upload session {session_id}: {e}")
            return None
    
    async def update_upload_session(
        self,
        session_id: str,
        uploaded_size: Optional[int] = None,
        status: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """Update upload session data."""
        try:
            key = f"upload_session:{session_id}"
            session_data = await self.get_upload_session(session_id)
            
            if not session_data:
                self.logger.warning(f"Upload session not found: {session_id}")
                return False
            
            # Update fields
            if uploaded_size is not None:
                session_data["uploaded_size"] = uploaded_size
            if status is not None:
                session_data["status"] = status
            if error_message is not None:
                session_data["error_message"] = error_message
            
            session_data["updated_at"] = datetime.utcnow().isoformat()
            
            # Get current TTL and preserve it
            ttl = await self.redis.ttl(key)
            await self.redis.setex(
                key,
                max(ttl, 60),  # Minimum 60 seconds
                json.dumps(session_data, default=str),
            )
            
            self.logger.info(f"Updated upload session: {session_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update upload session {session_id}: {e}")
            return False
    
    async def delete_upload_session(self, session_id: str) -> bool:
        """Delete upload session."""
        try:
            key = f"upload_session:{session_id}"
            result = await self.redis.delete(key)
            
            if result:
                self.logger.info(f"Deleted upload session: {session_id}")
                return True
            else:
                self.logger.warning(f"Upload session not found for deletion: {session_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to delete upload session {session_id}: {e}")
            return False
    
    # Virus Scan Job Management
    async def create_scan_job(
        self,
        scan_id: str,
        document_id: str,
        user_id: str,
        tenant_id: str,
        ttl_minutes: int = 30,
    ) -> bool:
        """Create a virus scan job in Redis."""
        try:
            job_data = {
                "scan_id": scan_id,
                "document_id": document_id,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "status": "pending",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }
            
            key = f"scan_job:{scan_id}"
            await self.redis.setex(
                key,
                timedelta(minutes=ttl_minutes),
                json.dumps(job_data, default=str),
            )
            
            # Add to scan queue
            await self.redis.lpush("scan_queue", scan_id)
            
            self.logger.info(f"Created scan job: {scan_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create scan job {scan_id}: {e}")
            return False
    
    async def get_scan_job(self, scan_id: str) -> Optional[Dict[str, Any]]:
        """Get scan job data."""
        try:
            key = f"scan_job:{scan_id}"
            data = await self.redis.get(key)
            if data:
                return json.loads(data)
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to get scan job {scan_id}: {e}")
            return None
    
    async def update_scan_job(
        self,
        scan_id: str,
        status: Optional[str] = None,
        result: Optional[str] = None,
        threats: Optional[List[Dict[str, Any]]] = None,
        duration_ms: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """Update scan job data."""
        try:
            key = f"scan_job:{scan_id}"
            job_data = await self.get_scan_job(scan_id)
            
            if not job_data:
                self.logger.warning(f"Scan job not found: {scan_id}")
                return False
            
            # Update fields
            if status is not None:
                job_data["status"] = status
            if result is not None:
                job_data["result"] = result
            if threats is not None:
                job_data["threats"] = threats
            if duration_ms is not None:
                job_data["duration_ms"] = duration_ms
            if error_message is not None:
                job_data["error_message"] = error_message
            
            job_data["updated_at"] = datetime.utcnow().isoformat()
            
            # Get current TTL and preserve it
            ttl = await self.redis.ttl(key)
            await self.redis.setex(
                key,
                max(ttl, 60),  # Minimum 60 seconds
                json.dumps(job_data, default=str),
            )
            
            self.logger.info(f"Updated scan job: {scan_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update scan job {scan_id}: {e}")
            return False
    
    async def pop_scan_job(self, timeout: int = 10) -> Optional[str]:
        """Pop a scan job from the queue."""
        try:
            # Blocking pop with timeout
            result = await self.redis.brpop("scan_queue", timeout=timeout)
            if result:
                _, scan_id = result
                self.logger.info(f"Popped scan job from queue: {scan_id}")
                return scan_id
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to pop scan job from queue: {e}")
            return None
    
    async def get_scan_queue_length(self) -> int:
        """Get scan queue length."""
        try:
            length = await self.redis.llen("scan_queue")
            return length
            
        except Exception as e:
            self.logger.error(f"Failed to get scan queue length: {e}")
            return 0
    
    # Cache Management
    async def cache_set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int = 3600,
    ) -> bool:
        """Set cache value."""
        try:
            await self.redis.setex(
                key,
                ttl_seconds,
                json.dumps(value, default=str),
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to set cache key {key}: {e}")
            return False
    
    async def cache_get(self, key: str) -> Optional[Any]:
        """Get cache value."""
        try:
            data = await self.redis.get(key)
            if data:
                return json.loads(data)
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to get cache key {key}: {e}")
            return None
    
    async def cache_delete(self, key: str) -> bool:
        """Delete cache key."""
        try:
            result = await self.redis.delete(key)
            return bool(result)
            
        except Exception as e:
            self.logger.error(f"Failed to delete cache key {key}: {e}")
            return False
    
    # Rate Limiting
    async def rate_limit_check(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> bool:
        """Check if rate limit is exceeded."""
        try:
            current_time = datetime.utcnow()
            window_start = current_time - timedelta(seconds=window_seconds)
            
            # Use a sliding window with sorted sets
            pipe = self.redis.pipeline()
            
            # Remove old entries
            pipe.zremrangebyscore(key, 0, window_start.timestamp())
            
            # Count current entries
            pipe.zcard(key)
            
            # Add current request
            pipe.zadd(key, {str(current_time.timestamp()): current_time.timestamp()})
            
            # Set expiry
            pipe.expire(key, window_seconds)
            
            results = await pipe.execute()
            current_count = results[1]
            
            return current_count < limit
            
        except Exception as e:
            self.logger.error(f"Failed to check rate limit for {key}: {e}")
            return True  # Allow request on error


# Global Redis client instance
redis_client = RedisClient()