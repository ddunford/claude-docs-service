"""Integration tests for database operations."""

import pytest
import uuid
import asyncio
from datetime import datetime, timedelta
from typing import AsyncGenerator

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from app.models.database import (
    Base,
    Document,
    DocumentVersion,
    StorageLocation,
    AuditLog,
    ScanResult,
    ThreatDetail,
    UploadSession,
)
from app.models.document import (
    DocumentStatus,
    StorageBackend,
    ScanStatus,
    ScanResultType,
    ThreatSeverity,
)


@pytest.fixture(scope="session")
def postgres_container():
    """Create PostgreSQL container for testing."""
    with PostgresContainer("postgres:15") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def database_url(postgres_container):
    """Get database URL from container."""
    return postgres_container.get_connection_url()


@pytest.fixture(scope="session")
def async_database_url(postgres_container):
    """Get async database URL from container."""
    return postgres_container.get_connection_url().replace("postgresql://", "postgresql+asyncpg://")


@pytest.fixture(scope="session")
def sync_engine(database_url):
    """Create synchronous database engine."""
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def async_engine(async_database_url):
    """Create asynchronous database engine."""
    engine = create_async_engine(async_database_url)
    yield engine
    asyncio.run(engine.dispose())


@pytest.fixture(scope="session")
def sync_session_factory(sync_engine):
    """Create synchronous session factory."""
    return sessionmaker(bind=sync_engine)


@pytest.fixture(scope="session")
def async_session_factory(async_engine):
    """Create asynchronous session factory."""
    return async_sessionmaker(bind=async_engine, class_=AsyncSession)


@pytest.fixture
async def async_session(async_session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Create async database session for testing."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.rollback()  # Rollback after each test
        finally:
            await session.close()


class TestDatabaseIntegration:
    """Integration tests for database operations."""

    @pytest.mark.asyncio
    async def test_create_document_with_storage_location(self, async_session):
        """Test creating a document with storage location."""
        document_id = uuid.uuid4()
        owner_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        
        # Create document
        document = Document(
            id=document_id,
            filename="test.pdf",
            content_type="application/pdf",
            size_bytes=1024,
            checksum="abc123",
            owner_id=owner_id,
            tenant_id=tenant_id,
            title="Test Document",
            description="A test document",
            tags=["test", "document"],
            attributes={"category": "test"},
            status=DocumentStatus.ACTIVE,
            version=1,
        )
        
        # Create storage location
        storage_location = StorageLocation(
            id=uuid.uuid4(),
            document_id=document_id,
            backend=StorageBackend.S3,
            bucket="test-bucket",
            key="test/file.pdf",
            region="us-east-1",
            endpoint_url=None,
            is_primary=True,
        )
        
        # Add to session
        async_session.add(document)
        async_session.add(storage_location)
        await async_session.commit()
        
        # Verify creation
        result = await async_session.get(Document, document_id)
        assert result is not None
        assert result.filename == "test.pdf"
        assert result.owner_id == owner_id
        assert result.tenant_id == tenant_id
        assert result.tags == ["test", "document"]
        assert result.attributes == {"category": "test"}
        
        # Verify storage location
        storage_result = await async_session.get(StorageLocation, storage_location.id)
        assert storage_result is not None
        assert storage_result.document_id == document_id
        assert storage_result.backend == StorageBackend.S3
        assert storage_result.bucket == "test-bucket"

    @pytest.mark.asyncio
    async def test_document_with_versions(self, async_session):
        """Test creating a document with version history."""
        document_id = uuid.uuid4()
        owner_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        
        # Create document
        document = Document(
            id=document_id,
            filename="test.pdf",
            content_type="application/pdf",
            size_bytes=1024,
            checksum="abc123",
            owner_id=owner_id,
            tenant_id=tenant_id,
            version=2,  # Current version
        )
        
        # Create version history
        version1 = DocumentVersion(
            id=uuid.uuid4(),
            document_id=document_id,
            version=1,
            description="Initial version",
            size_bytes=512,
            checksum="def456",
            backend=StorageBackend.S3,
            bucket="test-bucket",
            key="test/file-v1.pdf",
            region="us-east-1",
            created_by=owner_id,
        )
        
        version2 = DocumentVersion(
            id=uuid.uuid4(),
            document_id=document_id,
            version=2,
            description="Updated version",
            size_bytes=1024,
            checksum="abc123",
            backend=StorageBackend.S3,
            bucket="test-bucket",
            key="test/file-v2.pdf",
            region="us-east-1",
            created_by=owner_id,
        )
        
        # Add to session
        async_session.add(document)
        async_session.add(version1)
        async_session.add(version2)
        await async_session.commit()
        
        # Verify versions
        result = await async_session.get(Document, document_id)
        assert result is not None
        assert result.version == 2
        
        # Query versions
        from sqlalchemy import select
        versions_query = select(DocumentVersion).where(DocumentVersion.document_id == document_id)
        versions_result = await async_session.execute(versions_query)
        versions = versions_result.scalars().all()
        
        assert len(versions) == 2
        assert any(v.version == 1 for v in versions)
        assert any(v.version == 2 for v in versions)

    @pytest.mark.asyncio
    async def test_document_with_audit_log(self, async_session):
        """Test creating a document with audit log."""
        document_id = uuid.uuid4()
        owner_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        
        # Create document
        document = Document(
            id=document_id,
            filename="test.pdf",
            content_type="application/pdf",
            size_bytes=1024,
            checksum="abc123",
            owner_id=owner_id,
            tenant_id=tenant_id,
        )
        
        # Create audit log
        audit_log = AuditLog(
            id=uuid.uuid4(),
            document_id=document_id,
            action="upload",
            user_id=owner_id,
            tenant_id=tenant_id,
            request_id="req-123",
            ip_address="127.0.0.1",
            user_agent="test-agent",
            status="success",
            metadata={"file_size": 1024, "content_type": "application/pdf"},
        )
        
        # Add to session
        async_session.add(document)
        async_session.add(audit_log)
        await async_session.commit()
        
        # Verify audit log
        result = await async_session.get(AuditLog, audit_log.id)
        assert result is not None
        assert result.document_id == document_id
        assert result.action == "upload"
        assert result.user_id == owner_id
        assert result.tenant_id == tenant_id
        assert result.status == "success"
        assert result.metadata == {"file_size": 1024, "content_type": "application/pdf"}

    @pytest.mark.asyncio
    async def test_document_with_scan_results(self, async_session):
        """Test creating a document with scan results."""
        document_id = uuid.uuid4()
        owner_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        
        # Create document
        document = Document(
            id=document_id,
            filename="test.pdf",
            content_type="application/pdf",
            size_bytes=1024,
            checksum="abc123",
            owner_id=owner_id,
            tenant_id=tenant_id,
        )
        
        # Create scan result
        scan_result = ScanResult(
            id=uuid.uuid4(),
            document_id=document_id,
            scan_id="scan-123",
            status=ScanStatus.COMPLETED,
            result=ScanResultType.INFECTED,
            scanner_version="1.0.0",
            duration_ms=1000,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        
        # Create threat detail
        threat_detail = ThreatDetail(
            id=uuid.uuid4(),
            scan_result_id=scan_result.id,
            name="TestThreat",
            type="malware",
            severity=ThreatSeverity.HIGH,
            description="Test threat description",
        )
        
        # Add to session
        async_session.add(document)
        async_session.add(scan_result)
        async_session.add(threat_detail)
        await async_session.commit()
        
        # Verify scan result
        result = await async_session.get(ScanResult, scan_result.id)
        assert result is not None
        assert result.document_id == document_id
        assert result.scan_id == "scan-123"
        assert result.status == ScanStatus.COMPLETED
        assert result.result == ScanResultType.INFECTED
        assert result.scanner_version == "1.0.0"
        assert result.duration_ms == 1000
        
        # Verify threat detail
        threat_result = await async_session.get(ThreatDetail, threat_detail.id)
        assert threat_result is not None
        assert threat_result.scan_result_id == scan_result.id
        assert threat_result.name == "TestThreat"
        assert threat_result.type == "malware"
        assert threat_result.severity == ThreatSeverity.HIGH

    @pytest.mark.asyncio
    async def test_upload_session_creation(self, async_session):
        """Test creating upload session."""
        session_id = str(uuid.uuid4())
        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        
        # Create upload session
        upload_session = UploadSession(
            id=uuid.uuid4(),
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            filename="test.pdf",
            content_type="application/pdf",
            expected_size=1024,
            uploaded_size=0,
            status="pending",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        
        # Add to session
        async_session.add(upload_session)
        await async_session.commit()
        
        # Verify creation
        result = await async_session.get(UploadSession, upload_session.id)
        assert result is not None
        assert result.session_id == session_id
        assert result.user_id == user_id
        assert result.tenant_id == tenant_id
        assert result.filename == "test.pdf"
        assert result.content_type == "application/pdf"
        assert result.expected_size == 1024
        assert result.uploaded_size == 0
        assert result.status == "pending"

    @pytest.mark.asyncio
    async def test_document_relationships(self, async_session):
        """Test document relationships."""
        document_id = uuid.uuid4()
        owner_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        
        # Create document
        document = Document(
            id=document_id,
            filename="test.pdf",
            content_type="application/pdf",
            size_bytes=1024,
            checksum="abc123",
            owner_id=owner_id,
            tenant_id=tenant_id,
        )
        
        # Create related records
        storage_location = StorageLocation(
            id=uuid.uuid4(),
            document_id=document_id,
            backend=StorageBackend.S3,
            bucket="test-bucket",
            key="test/file.pdf",
            region="us-east-1",
        )
        
        version = DocumentVersion(
            id=uuid.uuid4(),
            document_id=document_id,
            version=1,
            size_bytes=1024,
            checksum="abc123",
            backend=StorageBackend.S3,
            bucket="test-bucket",
            key="test/file.pdf",
            region="us-east-1",
            created_by=owner_id,
        )
        
        audit_log = AuditLog(
            id=uuid.uuid4(),
            document_id=document_id,
            action="upload",
            user_id=owner_id,
            tenant_id=tenant_id,
            status="success",
        )
        
        scan_result = ScanResult(
            id=uuid.uuid4(),
            document_id=document_id,
            scan_id="scan-123",
            status=ScanStatus.COMPLETED,
            result=ScanResultType.CLEAN,
            started_at=datetime.utcnow(),
        )
        
        # Add to session
        async_session.add(document)
        async_session.add(storage_location)
        async_session.add(version)
        async_session.add(audit_log)
        async_session.add(scan_result)
        await async_session.commit()
        
        # Query document with relationships
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        
        query = select(Document).options(
            selectinload(Document.storage_locations),
            selectinload(Document.versions),
            selectinload(Document.audit_logs),
            selectinload(Document.scan_results),
        ).where(Document.id == document_id)
        
        result = await async_session.execute(query)
        document_with_relations = result.scalar_one()
        
        # Verify relationships
        assert len(document_with_relations.storage_locations) == 1
        assert len(document_with_relations.versions) == 1
        assert len(document_with_relations.audit_logs) == 1
        assert len(document_with_relations.scan_results) == 1
        
        assert document_with_relations.storage_locations[0].backend == StorageBackend.S3
        assert document_with_relations.versions[0].version == 1
        assert document_with_relations.audit_logs[0].action == "upload"
        assert document_with_relations.scan_results[0].result == ScanResultType.CLEAN

    @pytest.mark.asyncio
    async def test_cascade_delete(self, async_session):
        """Test cascade delete behavior."""
        document_id = uuid.uuid4()
        owner_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        
        # Create document
        document = Document(
            id=document_id,
            filename="test.pdf",
            content_type="application/pdf",
            size_bytes=1024,
            checksum="abc123",
            owner_id=owner_id,
            tenant_id=tenant_id,
        )
        
        # Create related records
        storage_location = StorageLocation(
            id=uuid.uuid4(),
            document_id=document_id,
            backend=StorageBackend.S3,
            bucket="test-bucket",
            key="test/file.pdf",
            region="us-east-1",
        )
        
        version = DocumentVersion(
            id=uuid.uuid4(),
            document_id=document_id,
            version=1,
            size_bytes=1024,
            checksum="abc123",
            backend=StorageBackend.S3,
            bucket="test-bucket",
            key="test/file.pdf",
            region="us-east-1",
            created_by=owner_id,
        )
        
        # Add to session
        async_session.add(document)
        async_session.add(storage_location)
        async_session.add(version)
        await async_session.commit()
        
        # Store IDs for verification
        storage_id = storage_location.id
        version_id = version.id
        
        # Delete document
        await async_session.delete(document)
        await async_session.commit()
        
        # Verify cascade delete
        assert await async_session.get(Document, document_id) is None
        assert await async_session.get(StorageLocation, storage_id) is None
        assert await async_session.get(DocumentVersion, version_id) is None

    @pytest.mark.asyncio
    async def test_indexes_performance(self, async_session):
        """Test that indexes are working properly."""
        # Create test data
        documents = []
        for i in range(100):
            document = Document(
                id=uuid.uuid4(),
                filename=f"test{i}.pdf",
                content_type="application/pdf",
                size_bytes=1024 + i,
                checksum=f"checksum{i}",
                owner_id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                tags=[f"tag{i % 10}"],
                status=DocumentStatus.ACTIVE if i % 2 == 0 else DocumentStatus.ARCHIVED,
            )
            documents.append(document)
        
        # Add to session
        async_session.add_all(documents)
        await async_session.commit()
        
        # Test index-based queries
        from sqlalchemy import select, func
        
        # Test status index
        status_query = select(func.count(Document.id)).where(Document.status == DocumentStatus.ACTIVE)
        result = await async_session.execute(status_query)
        active_count = result.scalar()
        assert active_count == 50
        
        # Test tags index (GIN index)
        tags_query = select(func.count(Document.id)).where(Document.tags.contains(["tag1"]))
        result = await async_session.execute(tags_query)
        tag_count = result.scalar()
        assert tag_count == 10  # Every 10th document has tag1

    @pytest.mark.asyncio
    async def test_concurrent_access(self, async_session_factory):
        """Test concurrent database access."""
        document_id = uuid.uuid4()
        owner_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        
        async def create_document():
            async with async_session_factory() as session:
                document = Document(
                    id=document_id,
                    filename="test.pdf",
                    content_type="application/pdf",
                    size_bytes=1024,
                    checksum="abc123",
                    owner_id=owner_id,
                    tenant_id=tenant_id,
                )
                session.add(document)
                await session.commit()
        
        async def read_document():
            async with async_session_factory() as session:
                result = await session.get(Document, document_id)
                return result
        
        # Create document in one session
        await create_document()
        
        # Read document in another session
        document = await read_document()
        assert document is not None
        assert document.filename == "test.pdf"