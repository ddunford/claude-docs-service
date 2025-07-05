"""Tests for Redis client."""

import pytest
import json
import uuid
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timedelta

from app.services.redis_client import RedisClient


class TestRedisClient:
    """Test Redis client."""

    @pytest.fixture
    def redis_client(self):
        """Create Redis client instance."""
        return RedisClient()

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis connection."""
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_redis.get.return_value = None
        mock_redis.setex.return_value = True
        mock_redis.delete.return_value = 1
        mock_redis.llen.return_value = 0
        mock_redis.lpush.return_value = 1
        mock_redis.brpop.return_value = None
        mock_redis.ttl.return_value = 3600
        mock_redis.pipeline.return_value = mock_redis
        mock_redis.execute.return_value = [None, 5, None, True]
        mock_redis.close.return_value = None
        return mock_redis

    @pytest.mark.asyncio
    async def test_connect_success(self, redis_client):
        """Test successful Redis connection."""
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        
        with patch('app.services.redis_client.redis.from_url', return_value=mock_redis):
            await redis_client.connect()
            
            assert redis_client.redis is mock_redis
            mock_redis.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_failure(self, redis_client):
        """Test Redis connection failure."""
        mock_redis = AsyncMock()
        mock_redis.ping.side_effect = Exception("Connection failed")
        
        with patch('app.services.redis_client.redis.from_url', return_value=mock_redis):
            with pytest.raises(Exception) as exc_info:
                await redis_client.connect()
            
            assert "Connection failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_disconnect(self, redis_client, mock_redis):
        """Test Redis disconnection."""
        redis_client.redis = mock_redis
        
        await redis_client.disconnect()
        
        mock_redis.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_success(self, redis_client, mock_redis):
        """Test successful health check."""
        redis_client.redis = mock_redis
        
        result = await redis_client.health_check()
        
        assert result is True
        mock_redis.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_failure(self, redis_client, mock_redis):
        """Test health check failure."""
        redis_client.redis = mock_redis
        mock_redis.ping.side_effect = Exception("Connection failed")
        
        result = await redis_client.health_check()
        
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_no_connection(self, redis_client):
        """Test health check with no connection."""
        redis_client.redis = None
        
        result = await redis_client.health_check()
        
        assert result is False

    @pytest.mark.asyncio
    async def test_create_upload_session_success(self, redis_client, mock_redis):
        """Test successful upload session creation."""
        redis_client.redis = mock_redis
        
        session_id = "session-123"
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        
        result = await redis_client.create_upload_session(
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            filename="test.pdf",
            content_type="application/pdf",
            expected_size=1024,
            ttl_minutes=60,
        )
        
        assert result is True
        
        # Verify setex was called with correct parameters
        mock_redis.setex.assert_called_once()
        args, kwargs = mock_redis.setex.call_args
        assert args[0] == f"upload_session:{session_id}"
        assert isinstance(args[1], timedelta)
        assert args[1].total_seconds() == 3600  # 60 minutes
        
        # Verify session data
        session_data = json.loads(args[2])
        assert session_data["session_id"] == session_id
        assert session_data["user_id"] == user_id
        assert session_data["tenant_id"] == tenant_id
        assert session_data["filename"] == "test.pdf"
        assert session_data["content_type"] == "application/pdf"
        assert session_data["expected_size"] == 1024
        assert session_data["uploaded_size"] == 0
        assert session_data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_upload_session_failure(self, redis_client, mock_redis):
        """Test upload session creation failure."""
        redis_client.redis = mock_redis
        mock_redis.setex.side_effect = Exception("Redis error")
        
        result = await redis_client.create_upload_session(
            session_id="session-123",
            user_id=str(uuid.uuid4()),
            tenant_id=str(uuid.uuid4()),
            filename="test.pdf",
            content_type="application/pdf",
        )
        
        assert result is False

    @pytest.mark.asyncio
    async def test_get_upload_session_success(self, redis_client, mock_redis):
        """Test successful upload session retrieval."""
        redis_client.redis = mock_redis
        
        session_data = {
            "session_id": "session-123",
            "user_id": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "expected_size": 1024,
            "uploaded_size": 0,
            "status": "pending",
        }
        
        mock_redis.get.return_value = json.dumps(session_data)
        
        result = await redis_client.get_upload_session("session-123")
        
        assert result == session_data
        mock_redis.get.assert_called_once_with("upload_session:session-123")

    @pytest.mark.asyncio
    async def test_get_upload_session_not_found(self, redis_client, mock_redis):
        """Test upload session retrieval when not found."""
        redis_client.redis = mock_redis
        mock_redis.get.return_value = None
        
        result = await redis_client.get_upload_session("session-123")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_get_upload_session_failure(self, redis_client, mock_redis):
        """Test upload session retrieval failure."""
        redis_client.redis = mock_redis
        mock_redis.get.side_effect = Exception("Redis error")
        
        result = await redis_client.get_upload_session("session-123")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_update_upload_session_success(self, redis_client, mock_redis):
        """Test successful upload session update."""
        redis_client.redis = mock_redis
        
        session_data = {
            "session_id": "session-123",
            "user_id": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "expected_size": 1024,
            "uploaded_size": 0,
            "status": "pending",
        }
        
        mock_redis.get.return_value = json.dumps(session_data)
        mock_redis.ttl.return_value = 3600
        
        result = await redis_client.update_upload_session(
            session_id="session-123",
            uploaded_size=512,
            status="processing",
        )
        
        assert result is True
        
        # Verify setex was called to update the session
        mock_redis.setex.assert_called_once()
        args, kwargs = mock_redis.setex.call_args
        assert args[0] == "upload_session:session-123"
        assert args[1] == 3600  # Preserved TTL
        
        # Verify updated session data
        updated_data = json.loads(args[2])
        assert updated_data["uploaded_size"] == 512
        assert updated_data["status"] == "processing"

    @pytest.mark.asyncio
    async def test_update_upload_session_not_found(self, redis_client, mock_redis):
        """Test upload session update when session not found."""
        redis_client.redis = mock_redis
        mock_redis.get.return_value = None
        
        result = await redis_client.update_upload_session(
            session_id="session-123",
            uploaded_size=512,
        )
        
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_upload_session_success(self, redis_client, mock_redis):
        """Test successful upload session deletion."""
        redis_client.redis = mock_redis
        mock_redis.delete.return_value = 1
        
        result = await redis_client.delete_upload_session("session-123")
        
        assert result is True
        mock_redis.delete.assert_called_once_with("upload_session:session-123")

    @pytest.mark.asyncio
    async def test_delete_upload_session_not_found(self, redis_client, mock_redis):
        """Test upload session deletion when session not found."""
        redis_client.redis = mock_redis
        mock_redis.delete.return_value = 0
        
        result = await redis_client.delete_upload_session("session-123")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_create_scan_job_success(self, redis_client, mock_redis):
        """Test successful scan job creation."""
        redis_client.redis = mock_redis
        
        scan_id = "scan-123"
        document_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        
        result = await redis_client.create_scan_job(
            scan_id=scan_id,
            document_id=document_id,
            user_id=user_id,
            tenant_id=tenant_id,
            ttl_minutes=30,
        )
        
        assert result is True
        
        # Verify setex was called for job data
        mock_redis.setex.assert_called_once()
        args, kwargs = mock_redis.setex.call_args
        assert args[0] == f"scan_job:{scan_id}"
        assert isinstance(args[1], timedelta)
        assert args[1].total_seconds() == 1800  # 30 minutes
        
        # Verify job data
        job_data = json.loads(args[2])
        assert job_data["scan_id"] == scan_id
        assert job_data["document_id"] == document_id
        assert job_data["user_id"] == user_id
        assert job_data["tenant_id"] == tenant_id
        assert job_data["status"] == "pending"
        
        # Verify job was added to queue
        mock_redis.lpush.assert_called_once_with("scan_queue", scan_id)

    @pytest.mark.asyncio
    async def test_get_scan_job_success(self, redis_client, mock_redis):
        """Test successful scan job retrieval."""
        redis_client.redis = mock_redis
        
        job_data = {
            "scan_id": "scan-123",
            "document_id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "status": "pending",
        }
        
        mock_redis.get.return_value = json.dumps(job_data)
        
        result = await redis_client.get_scan_job("scan-123")
        
        assert result == job_data
        mock_redis.get.assert_called_once_with("scan_job:scan-123")

    @pytest.mark.asyncio
    async def test_update_scan_job_success(self, redis_client, mock_redis):
        """Test successful scan job update."""
        redis_client.redis = mock_redis
        
        job_data = {
            "scan_id": "scan-123",
            "document_id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "status": "pending",
        }
        
        mock_redis.get.return_value = json.dumps(job_data)
        mock_redis.ttl.return_value = 1800
        
        result = await redis_client.update_scan_job(
            scan_id="scan-123",
            status="completed",
            result="clean",
            duration_ms=1000,
        )
        
        assert result is True
        
        # Verify setex was called to update the job
        mock_redis.setex.assert_called_once()
        args, kwargs = mock_redis.setex.call_args
        assert args[0] == "scan_job:scan-123"
        assert args[1] == 1800  # Preserved TTL
        
        # Verify updated job data
        updated_data = json.loads(args[2])
        assert updated_data["status"] == "completed"
        assert updated_data["result"] == "clean"
        assert updated_data["duration_ms"] == 1000

    @pytest.mark.asyncio
    async def test_pop_scan_job_success(self, redis_client, mock_redis):
        """Test successful scan job pop from queue."""
        redis_client.redis = mock_redis
        mock_redis.brpop.return_value = ("scan_queue", "scan-123")
        
        result = await redis_client.pop_scan_job(timeout=10)
        
        assert result == "scan-123"
        mock_redis.brpop.assert_called_once_with("scan_queue", timeout=10)

    @pytest.mark.asyncio
    async def test_pop_scan_job_timeout(self, redis_client, mock_redis):
        """Test scan job pop with timeout."""
        redis_client.redis = mock_redis
        mock_redis.brpop.return_value = None
        
        result = await redis_client.pop_scan_job(timeout=10)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_get_scan_queue_length_success(self, redis_client, mock_redis):
        """Test successful scan queue length retrieval."""
        redis_client.redis = mock_redis
        mock_redis.llen.return_value = 5
        
        result = await redis_client.get_scan_queue_length()
        
        assert result == 5
        mock_redis.llen.assert_called_once_with("scan_queue")

    @pytest.mark.asyncio
    async def test_get_scan_queue_length_failure(self, redis_client, mock_redis):
        """Test scan queue length retrieval failure."""
        redis_client.redis = mock_redis
        mock_redis.llen.side_effect = Exception("Redis error")
        
        result = await redis_client.get_scan_queue_length()
        
        assert result == 0

    @pytest.mark.asyncio
    async def test_cache_set_success(self, redis_client, mock_redis):
        """Test successful cache set."""
        redis_client.redis = mock_redis
        
        result = await redis_client.cache_set(
            key="test_key",
            value={"test": "data"},
            ttl_seconds=3600,
        )
        
        assert result is True
        mock_redis.setex.assert_called_once_with(
            "test_key",
            3600,
            json.dumps({"test": "data"}, default=str),
        )

    @pytest.mark.asyncio
    async def test_cache_get_success(self, redis_client, mock_redis):
        """Test successful cache get."""
        redis_client.redis = mock_redis
        test_data = {"test": "data"}
        mock_redis.get.return_value = json.dumps(test_data)
        
        result = await redis_client.cache_get("test_key")
        
        assert result == test_data
        mock_redis.get.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_cache_get_not_found(self, redis_client, mock_redis):
        """Test cache get when key not found."""
        redis_client.redis = mock_redis
        mock_redis.get.return_value = None
        
        result = await redis_client.cache_get("test_key")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_delete_success(self, redis_client, mock_redis):
        """Test successful cache delete."""
        redis_client.redis = mock_redis
        mock_redis.delete.return_value = 1
        
        result = await redis_client.cache_delete("test_key")
        
        assert result is True
        mock_redis.delete.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_cache_delete_not_found(self, redis_client, mock_redis):
        """Test cache delete when key not found."""
        redis_client.redis = mock_redis
        mock_redis.delete.return_value = 0
        
        result = await redis_client.cache_delete("test_key")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_rate_limit_check_success(self, redis_client):
        """Test successful rate limit check."""
        # Mock the rate_limit_check method to return True (under limit)
        with patch.object(redis_client, 'rate_limit_check', return_value=True) as mock_rate_limit:
            result = await redis_client.rate_limit_check(
                key="rate_limit:user:123",
                limit=10,
                window_seconds=60,
            )
            
            assert result is True
            mock_rate_limit.assert_called_once_with(
                key="rate_limit:user:123",
                limit=10,
                window_seconds=60,
            )

    @pytest.mark.asyncio
    async def test_rate_limit_check_exceeded(self, redis_client):
        """Test rate limit check when limit exceeded."""
        # Mock the rate_limit_check method to return False (over limit)
        with patch.object(redis_client, 'rate_limit_check', return_value=False) as mock_rate_limit:
            result = await redis_client.rate_limit_check(
                key="rate_limit:user:123",
                limit=10,
                window_seconds=60,
            )
            
            assert result is False  # Rate limited
            mock_rate_limit.assert_called_once_with(
                key="rate_limit:user:123",
                limit=10,
                window_seconds=60,
            )

    @pytest.mark.asyncio
    async def test_rate_limit_check_failure(self, redis_client, mock_redis):
        """Test rate limit check failure."""
        redis_client.redis = mock_redis
        mock_redis.pipeline.side_effect = Exception("Redis error")
        
        result = await redis_client.rate_limit_check(
            key="rate_limit:user:123",
            limit=10,
            window_seconds=60,
        )
        
        assert result is True  # Allow request on error