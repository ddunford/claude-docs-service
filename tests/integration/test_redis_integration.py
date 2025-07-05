"""Integration tests for Redis operations."""

import pytest
import uuid
import json
import asyncio
from datetime import datetime, timedelta

from testcontainers.redis import RedisContainer
import redis.asyncio as redis

from app.services.redis_client import RedisClient


@pytest.fixture(scope="session")
def redis_container():
    """Create Redis container for testing."""
    with RedisContainer("redis:7") as redis_cont:
        yield redis_cont


@pytest.fixture(scope="session")
def redis_url(redis_container):
    """Get Redis URL from container."""
    return redis_container.get_connection_url()


@pytest.fixture
async def redis_client(redis_url):
    """Create Redis client for testing."""
    # Mock settings for RedisClient
    import app.services.redis_client
    original_settings = app.services.redis_client.settings
    
    class MockSettings:
        REDIS_URL = redis_url
        REDIS_MAX_CONNECTIONS = 10
    
    app.services.redis_client.settings = MockSettings()
    
    client = RedisClient()
    await client.connect()
    
    yield client
    
    await client.disconnect()
    app.services.redis_client.settings = original_settings


@pytest.fixture
async def raw_redis_client(redis_url):
    """Create raw Redis client for verification."""
    client = redis.from_url(redis_url, decode_responses=True)
    yield client
    await client.close()


class TestRedisIntegration:
    """Integration tests for Redis operations."""

    @pytest.mark.asyncio
    async def test_redis_connection(self, redis_client):
        """Test Redis connection."""
        health = await redis_client.health_check()
        assert health is True

    @pytest.mark.asyncio
    async def test_upload_session_lifecycle(self, redis_client, raw_redis_client):
        """Test complete upload session lifecycle."""
        session_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        
        # Create upload session
        success = await redis_client.create_upload_session(
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            filename="test.pdf",
            content_type="application/pdf",
            expected_size=1024,
            ttl_minutes=1,
        )
        assert success is True
        
        # Verify session exists in Redis
        raw_data = await raw_redis_client.get(f"upload_session:{session_id}")
        assert raw_data is not None
        session_data = json.loads(raw_data)
        assert session_data["session_id"] == session_id
        assert session_data["user_id"] == user_id
        assert session_data["tenant_id"] == tenant_id
        assert session_data["filename"] == "test.pdf"
        assert session_data["content_type"] == "application/pdf"
        assert session_data["expected_size"] == 1024
        assert session_data["uploaded_size"] == 0
        assert session_data["status"] == "pending"
        
        # Get upload session
        retrieved_session = await redis_client.get_upload_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session["session_id"] == session_id
        assert retrieved_session["user_id"] == user_id
        assert retrieved_session["tenant_id"] == tenant_id
        assert retrieved_session["filename"] == "test.pdf"
        assert retrieved_session["uploaded_size"] == 0
        assert retrieved_session["status"] == "pending"
        
        # Update upload session
        update_success = await redis_client.update_upload_session(
            session_id=session_id,
            uploaded_size=512,
            status="processing",
        )
        assert update_success is True
        
        # Verify update
        updated_session = await redis_client.get_upload_session(session_id)
        assert updated_session["uploaded_size"] == 512
        assert updated_session["status"] == "processing"
        
        # Update with error
        error_update = await redis_client.update_upload_session(
            session_id=session_id,
            status="failed",
            error_message="Upload failed",
        )
        assert error_update is True
        
        # Verify error update
        error_session = await redis_client.get_upload_session(session_id)
        assert error_session["status"] == "failed"
        assert error_session["error_message"] == "Upload failed"
        
        # Delete upload session
        delete_success = await redis_client.delete_upload_session(session_id)
        assert delete_success is True
        
        # Verify deletion
        deleted_session = await redis_client.get_upload_session(session_id)
        assert deleted_session is None

    @pytest.mark.asyncio
    async def test_upload_session_expiration(self, redis_client):
        """Test upload session expiration."""
        session_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        
        # Create upload session with very short TTL
        success = await redis_client.create_upload_session(
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            filename="test.pdf",
            content_type="application/pdf",
            ttl_minutes=0.01,  # 0.6 seconds
        )
        assert success is True
        
        # Verify session exists
        session = await redis_client.get_upload_session(session_id)
        assert session is not None
        
        # Wait for expiration
        await asyncio.sleep(1)
        
        # Verify session has expired
        expired_session = await redis_client.get_upload_session(session_id)
        assert expired_session is None

    @pytest.mark.asyncio
    async def test_scan_job_lifecycle(self, redis_client, raw_redis_client):
        """Test complete scan job lifecycle."""
        scan_id = str(uuid.uuid4())
        document_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        
        # Create scan job
        success = await redis_client.create_scan_job(
            scan_id=scan_id,
            document_id=document_id,
            user_id=user_id,
            tenant_id=tenant_id,
            ttl_minutes=30,
        )
        assert success is True
        
        # Verify job exists in Redis
        raw_data = await raw_redis_client.get(f"scan_job:{scan_id}")
        assert raw_data is not None
        job_data = json.loads(raw_data)
        assert job_data["scan_id"] == scan_id
        assert job_data["document_id"] == document_id
        assert job_data["user_id"] == user_id
        assert job_data["tenant_id"] == tenant_id
        assert job_data["status"] == "pending"
        
        # Verify job was added to queue
        queue_length = await redis_client.get_scan_queue_length()
        assert queue_length >= 1
        
        # Get scan job
        retrieved_job = await redis_client.get_scan_job(scan_id)
        assert retrieved_job is not None
        assert retrieved_job["scan_id"] == scan_id
        assert retrieved_job["document_id"] == document_id
        assert retrieved_job["status"] == "pending"
        
        # Pop scan job from queue
        popped_scan_id = await redis_client.pop_scan_job(timeout=1)
        assert popped_scan_id == scan_id
        
        # Update scan job to processing
        update_success = await redis_client.update_scan_job(
            scan_id=scan_id,
            status="scanning",
        )
        assert update_success is True
        
        # Verify update
        updated_job = await redis_client.get_scan_job(scan_id)
        assert updated_job["status"] == "scanning"
        
        # Complete scan job
        threats = [
            {
                "name": "TestThreat",
                "type": "malware",
                "severity": "high",
                "description": "Test threat",
            }
        ]
        
        complete_success = await redis_client.update_scan_job(
            scan_id=scan_id,
            status="completed",
            result="infected",
            threats=threats,
            duration_ms=1000,
        )
        assert complete_success is True
        
        # Verify completion
        completed_job = await redis_client.get_scan_job(scan_id)
        assert completed_job["status"] == "completed"
        assert completed_job["result"] == "infected"
        assert completed_job["threats"] == threats
        assert completed_job["duration_ms"] == 1000

    @pytest.mark.asyncio
    async def test_scan_queue_operations(self, redis_client, raw_redis_client):
        """Test scan queue operations."""
        # Create multiple scan jobs
        scan_ids = [str(uuid.uuid4()) for _ in range(5)]
        
        for scan_id in scan_ids:
            success = await redis_client.create_scan_job(
                scan_id=scan_id,
                document_id=str(uuid.uuid4()),
                user_id=str(uuid.uuid4()),
                tenant_id=str(uuid.uuid4()),
            )
            assert success is True
        
        # Check queue length
        queue_length = await redis_client.get_scan_queue_length()
        assert queue_length >= 5
        
        # Pop jobs from queue
        popped_ids = []
        for _ in range(5):
            popped_id = await redis_client.pop_scan_job(timeout=1)
            if popped_id:
                popped_ids.append(popped_id)
        
        # Verify all jobs were popped (order may vary due to Redis LIFO)
        assert len(popped_ids) == 5
        assert set(popped_ids) == set(scan_ids)
        
        # Queue should be empty or much smaller now
        remaining_length = await redis_client.get_scan_queue_length()
        assert remaining_length < queue_length

    @pytest.mark.asyncio
    async def test_scan_job_timeout(self, redis_client):
        """Test scan job queue timeout."""
        # Try to pop from empty queue with short timeout
        start_time = datetime.now()
        popped_id = await redis_client.pop_scan_job(timeout=1)
        end_time = datetime.now()
        
        assert popped_id is None
        # Should have waited approximately 1 second
        duration = (end_time - start_time).total_seconds()
        assert 0.8 <= duration <= 1.5  # Allow some variance

    @pytest.mark.asyncio
    async def test_cache_operations(self, redis_client, raw_redis_client):
        """Test cache operations."""
        key = "test_cache_key"
        value = {
            "string_field": "test_value",
            "number_field": 42,
            "list_field": [1, 2, 3],
            "dict_field": {"nested": "value"},
        }
        
        # Set cache value
        success = await redis_client.cache_set(key, value, ttl_seconds=3600)
        assert success is True
        
        # Verify value exists in Redis
        raw_data = await raw_redis_client.get(key)
        assert raw_data is not None
        cached_value = json.loads(raw_data)
        assert cached_value == value
        
        # Get cache value
        retrieved_value = await redis_client.cache_get(key)
        assert retrieved_value == value
        
        # Cache non-existent key
        non_existent = await redis_client.cache_get("non_existent_key")
        assert non_existent is None
        
        # Delete cache key
        delete_success = await redis_client.cache_delete(key)
        assert delete_success is True
        
        # Verify deletion
        deleted_value = await redis_client.cache_get(key)
        assert deleted_value is None
        
        # Delete non-existent key
        delete_non_existent = await redis_client.cache_delete("non_existent_key")
        assert delete_non_existent is False

    @pytest.mark.asyncio
    async def test_cache_expiration(self, redis_client):
        """Test cache expiration."""
        key = "expiring_key"
        value = {"test": "data"}
        
        # Set cache value with short TTL
        success = await redis_client.cache_set(key, value, ttl_seconds=1)
        assert success is True
        
        # Verify value exists
        retrieved_value = await redis_client.cache_get(key)
        assert retrieved_value == value
        
        # Wait for expiration
        await asyncio.sleep(1.5)
        
        # Verify value has expired
        expired_value = await redis_client.cache_get(key)
        assert expired_value is None

    @pytest.mark.asyncio
    async def test_rate_limiting(self, redis_client, raw_redis_client):
        """Test rate limiting functionality."""
        key = "rate_limit:test_user"
        limit = 5
        window_seconds = 10
        
        # Make requests within limit
        for i in range(limit):
            allowed = await redis_client.rate_limit_check(key, limit, window_seconds)
            assert allowed is True
        
        # Next request should be rate limited
        rate_limited = await redis_client.rate_limit_check(key, limit, window_seconds)
        assert rate_limited is False
        
        # Verify rate limit data exists in Redis
        raw_data = await raw_redis_client.zcard(key)
        assert raw_data >= limit

    @pytest.mark.asyncio
    async def test_rate_limiting_sliding_window(self, redis_client):
        """Test rate limiting sliding window behavior."""
        key = "rate_limit:sliding_test"
        limit = 3
        window_seconds = 2
        
        # Make requests at the limit
        for i in range(limit):
            allowed = await redis_client.rate_limit_check(key, limit, window_seconds)
            assert allowed is True
        
        # Should be rate limited now
        rate_limited = await redis_client.rate_limit_check(key, limit, window_seconds)
        assert rate_limited is False
        
        # Wait for window to slide
        await asyncio.sleep(2.1)
        
        # Should be allowed again
        allowed_after_window = await redis_client.rate_limit_check(key, limit, window_seconds)
        assert allowed_after_window is True

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, redis_client):
        """Test concurrent Redis operations."""
        async def upload_session_worker(worker_id):
            session_id = f"session-{worker_id}-{uuid.uuid4()}"
            user_id = str(uuid.uuid4())
            tenant_id = str(uuid.uuid4())
            
            # Create session
            success = await redis_client.create_upload_session(
                session_id=session_id,
                user_id=user_id,
                tenant_id=tenant_id,
                filename=f"file-{worker_id}.pdf",
                content_type="application/pdf",
            )
            assert success is True
            
            # Update session
            update_success = await redis_client.update_upload_session(
                session_id=session_id,
                uploaded_size=1024,
                status="completed",
            )
            assert update_success is True
            
            # Verify session
            session = await redis_client.get_upload_session(session_id)
            assert session is not None
            assert session["status"] == "completed"
            assert session["uploaded_size"] == 1024
            
            return session_id
        
        async def scan_job_worker(worker_id):
            scan_id = f"scan-{worker_id}-{uuid.uuid4()}"
            document_id = str(uuid.uuid4())
            user_id = str(uuid.uuid4())
            tenant_id = str(uuid.uuid4())
            
            # Create scan job
            success = await redis_client.create_scan_job(
                scan_id=scan_id,
                document_id=document_id,
                user_id=user_id,
                tenant_id=tenant_id,
            )
            assert success is True
            
            # Pop and process job
            popped_id = await redis_client.pop_scan_job(timeout=5)
            if popped_id:
                # Update job status
                update_success = await redis_client.update_scan_job(
                    scan_id=popped_id,
                    status="completed",
                    result="clean",
                    duration_ms=500,
                )
                assert update_success is True
                return popped_id
            
            return None
        
        # Run multiple concurrent workers
        upload_tasks = [upload_session_worker(i) for i in range(10)]
        scan_tasks = [scan_job_worker(i) for i in range(10)]
        
        # Wait for all tasks to complete
        upload_results = await asyncio.gather(*upload_tasks)
        scan_results = await asyncio.gather(*scan_tasks)
        
        # Verify all upload sessions were created
        assert len(upload_results) == 10
        assert all(result is not None for result in upload_results)
        
        # Verify scan jobs were processed
        processed_jobs = [result for result in scan_results if result is not None]
        assert len(processed_jobs) >= 5  # At least some jobs should be processed

    @pytest.mark.asyncio
    async def test_error_handling(self, redis_client):
        """Test error handling in Redis operations."""
        # Test operations on non-existent sessions
        non_existent_session = await redis_client.get_upload_session("non-existent")
        assert non_existent_session is None
        
        update_non_existent = await redis_client.update_upload_session(
            session_id="non-existent",
            uploaded_size=1024,
        )
        assert update_non_existent is False
        
        # Test operations on non-existent scan jobs
        non_existent_job = await redis_client.get_scan_job("non-existent")
        assert non_existent_job is None
        
        update_non_existent_job = await redis_client.update_scan_job(
            scan_id="non-existent",
            status="completed",
        )
        assert update_non_existent_job is False

    @pytest.mark.asyncio
    async def test_data_persistence(self, redis_client, raw_redis_client):
        """Test data persistence and consistency."""
        # Create multiple types of data
        session_id = str(uuid.uuid4())
        scan_id = str(uuid.uuid4())
        cache_key = "persistence_test"
        
        # Create upload session
        await redis_client.create_upload_session(
            session_id=session_id,
            user_id=str(uuid.uuid4()),
            tenant_id=str(uuid.uuid4()),
            filename="test.pdf",
            content_type="application/pdf",
        )
        
        # Create scan job
        await redis_client.create_scan_job(
            scan_id=scan_id,
            document_id=str(uuid.uuid4()),
            user_id=str(uuid.uuid4()),
            tenant_id=str(uuid.uuid4()),
        )
        
        # Set cache value
        await redis_client.cache_set(cache_key, {"test": "data"})
        
        # Verify all data exists through raw client
        session_exists = await raw_redis_client.exists(f"upload_session:{session_id}")
        assert session_exists == 1
        
        job_exists = await raw_redis_client.exists(f"scan_job:{scan_id}")
        assert job_exists == 1
        
        cache_exists = await raw_redis_client.exists(cache_key)
        assert cache_exists == 1
        
        queue_length = await raw_redis_client.llen("scan_queue")
        assert queue_length >= 1
        
        # Verify data through Redis client
        session = await redis_client.get_upload_session(session_id)
        assert session is not None
        
        job = await redis_client.get_scan_job(scan_id)
        assert job is not None
        
        cache_value = await redis_client.cache_get(cache_key)
        assert cache_value == {"test": "data"}