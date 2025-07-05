"""Unit tests for database connection and session management."""

import pytest
from unittest.mock import AsyncMock, Mock, patch, call
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import (
    get_db,
    init_db,
    close_db,
    get_db_session,
    async_engine,
    sync_engine,
    AsyncSessionLocal,
    SessionLocal,
)


class TestDatabaseModule:
    """Test database module initialization and configuration."""
    
    @patch('app.database.settings')
    @patch('app.database.create_async_engine')
    def test_async_engine_creation(self, mock_create_async_engine, mock_settings):
        """Test async engine creation with correct parameters."""
        mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@localhost/test"
        mock_settings.DATABASE_POOL_SIZE = 15
        mock_settings.DATABASE_MAX_OVERFLOW = 25
        mock_settings.DEBUG = True
        
        # Import after mocking to ensure the mocked values are used
        import importlib
        import app.database
        importlib.reload(app.database)
        
        mock_create_async_engine.assert_called_with(
            "postgresql+asyncpg://user:pass@localhost/test",
            pool_size=15,
            max_overflow=25,
            echo=True,
        )
    
    @patch('app.database.settings')
    @patch('app.database.create_engine')
    def test_sync_engine_creation(self, mock_create_engine, mock_settings):
        """Test sync engine creation with correct parameters."""
        mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@localhost/test"
        mock_settings.DATABASE_POOL_SIZE = 15
        mock_settings.DATABASE_MAX_OVERFLOW = 25
        mock_settings.DEBUG = False
        
        # Import after mocking to ensure the mocked values are used
        import importlib
        import app.database
        importlib.reload(app.database)
        
        # Sync engine should use postgresql:// instead of postgresql+asyncpg://
        mock_create_engine.assert_called_with(
            "postgresql://user:pass@localhost/test",
            pool_size=15,
            max_overflow=25,
            echo=False,
        )
    
    @patch('app.database.async_sessionmaker')
    @patch('app.database.async_engine')
    def test_async_session_factory_creation(self, mock_async_engine, mock_async_sessionmaker):
        """Test async session factory creation."""
        import importlib
        import app.database
        importlib.reload(app.database)
        
        mock_async_sessionmaker.assert_called_with(
            mock_async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    
    @patch('app.database.sessionmaker')
    @patch('app.database.sync_engine')
    def test_sync_session_factory_creation(self, mock_sync_engine, mock_sessionmaker):
        """Test sync session factory creation."""
        import importlib
        import app.database
        importlib.reload(app.database)
        
        mock_sessionmaker.assert_called_with(
            autocommit=False,
            autoflush=False,
            bind=mock_sync_engine,
        )


class TestGetDb:
    """Test get_db async context manager."""
    
    @pytest.mark.asyncio
    async def test_get_db_success(self):
        """Test successful database session usage."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session_factory = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_session_factory.return_value.__aexit__.return_value = None
        
        with patch('app.database.AsyncSessionLocal', mock_session_factory):
            async with get_db() as session:
                assert session == mock_session
                # Simulate some database operations
                await session.execute("SELECT 1")
            
            # Verify session lifecycle
            mock_session.commit.assert_called_once()
            mock_session.close.assert_called_once()
            mock_session.rollback.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_get_db_exception_handling(self):
        """Test get_db exception handling and rollback."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session_factory = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_session_factory.return_value.__aexit__.return_value = None
        
        with patch('app.database.AsyncSessionLocal', mock_session_factory):
            with patch('app.database.logger') as mock_logger:
                with pytest.raises(ValueError):
                    async with get_db() as session:
                        # Simulate an exception during database operations
                        raise ValueError("Database operation failed")
                
                # Verify rollback was called
                mock_session.rollback.assert_called_once()
                mock_session.close.assert_called_once()
                mock_session.commit.assert_not_called()
                
                # Verify error was logged
                mock_logger.error.assert_called_once()
                assert "Database session error" in str(mock_logger.error.call_args)
    
    @pytest.mark.asyncio
    async def test_get_db_commit_exception(self):
        """Test get_db when commit raises an exception."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit.side_effect = Exception("Commit failed")
        mock_session_factory = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_session_factory.return_value.__aexit__.return_value = None
        
        with patch('app.database.AsyncSessionLocal', mock_session_factory):
            with patch('app.database.logger') as mock_logger:
                with pytest.raises(Exception) as exc_info:
                    async with get_db() as session:
                        # Normal operation, but commit will fail
                        pass
                
                assert "Commit failed" in str(exc_info.value)
                
                # Verify rollback was called due to commit failure
                mock_session.commit.assert_called_once()
                mock_session.rollback.assert_called_once()
                mock_session.close.assert_called_once()
                
                # Verify error was logged
                mock_logger.error.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_db_rollback_exception(self):
        """Test get_db when rollback also raises an exception."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.rollback.side_effect = Exception("Rollback failed")
        mock_session_factory = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_session_factory.return_value.__aexit__.return_value = None
        
        with patch('app.database.AsyncSessionLocal', mock_session_factory):
            with patch('app.database.logger') as mock_logger:
                # The original exception should be raised, not the rollback exception
                with pytest.raises(ValueError) as exc_info:
                    async with get_db() as session:
                        raise ValueError("Original error")
                
                assert "Original error" in str(exc_info.value)
                
                # Verify both rollback and close were attempted
                mock_session.rollback.assert_called_once()
                mock_session.close.assert_called_once()
                
                # Error should be logged (the original error)
                mock_logger.error.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_db_close_exception(self):
        """Test get_db when close raises an exception."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.close.side_effect = Exception("Close failed")
        mock_session_factory = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_session_factory.return_value.__aexit__.return_value = None
        
        with patch('app.database.AsyncSessionLocal', mock_session_factory):
            # Should complete normally despite close failure
            async with get_db() as session:
                assert session == mock_session
            
            # Verify normal lifecycle was attempted
            mock_session.commit.assert_called_once()
            mock_session.close.assert_called_once()


class TestInitDb:
    """Test init_db function."""
    
    @pytest.mark.asyncio
    async def test_init_db_success(self):
        """Test successful database initialization."""
        mock_conn = AsyncMock()
        mock_engine = AsyncMock()
        mock_engine.begin.return_value.__aenter__.return_value = mock_conn
        mock_engine.begin.return_value.__aexit__.return_value = None
        
        with patch('app.database.async_engine', mock_engine):
            with patch('app.database.Base') as mock_base:
                with patch('app.database.logger') as mock_logger:
                    await init_db()
                    
                    # Verify database initialization
                    mock_engine.begin.assert_called_once()
                    mock_conn.run_sync.assert_called_once_with(mock_base.metadata.create_all)
                    mock_logger.info.assert_called_once_with("Database initialized successfully")
    
    @pytest.mark.asyncio
    async def test_init_db_exception(self):
        """Test init_db with exception."""
        mock_conn = AsyncMock()
        mock_conn.run_sync.side_effect = Exception("Database initialization failed")
        mock_engine = AsyncMock()
        mock_engine.begin.return_value.__aenter__.return_value = mock_conn
        mock_engine.begin.return_value.__aexit__.return_value = None
        
        with patch('app.database.async_engine', mock_engine):
            with patch('app.database.Base') as mock_base:
                with pytest.raises(Exception) as exc_info:
                    await init_db()
                
                assert "Database initialization failed" in str(exc_info.value)
                mock_conn.run_sync.assert_called_once_with(mock_base.metadata.create_all)


class TestCloseDb:
    """Test close_db function."""
    
    @pytest.mark.asyncio
    async def test_close_db_success(self):
        """Test successful database connection closure."""
        mock_engine = AsyncMock()
        
        with patch('app.database.async_engine', mock_engine):
            with patch('app.database.logger') as mock_logger:
                await close_db()
                
                mock_engine.dispose.assert_called_once()
                mock_logger.info.assert_called_once_with("Database connections closed")
    
    @pytest.mark.asyncio
    async def test_close_db_exception(self):
        """Test close_db with exception."""
        mock_engine = AsyncMock()
        mock_engine.dispose.side_effect = Exception("Failed to close connections")
        
        with patch('app.database.async_engine', mock_engine):
            with pytest.raises(Exception) as exc_info:
                await close_db()
            
            assert "Failed to close connections" in str(exc_info.value)
            mock_engine.dispose.assert_called_once()


class TestGetDbSession:
    """Test get_db_session FastAPI dependency."""
    
    @pytest.mark.asyncio
    async def test_get_db_session_success(self):
        """Test successful FastAPI database session dependency."""
        mock_session = AsyncMock(spec=AsyncSession)
        
        # Mock the get_db context manager
        @asynccontextmanager
        async def mock_get_db():
            yield mock_session
        
        with patch('app.database.get_db', mock_get_db):
            # Test the dependency
            async with get_db_session() as session:
                assert session == mock_session
    
    @pytest.mark.asyncio
    async def test_get_db_session_as_async_generator(self):
        """Test that get_db_session works as an async generator for FastAPI."""
        mock_session = AsyncMock(spec=AsyncSession)
        
        @asynccontextmanager
        async def mock_get_db():
            yield mock_session
        
        with patch('app.database.get_db', mock_get_db):
            # Test using the generator protocol
            session_generator = get_db_session()
            session = await session_generator.__anext__()
            
            assert session == mock_session
            
            # Test that generator can be closed
            try:
                await session_generator.__anext__()
            except StopAsyncIteration:
                # This is expected when the generator is exhausted
                pass


class TestDatabaseConfiguration:
    """Test database configuration and settings."""
    
    def test_database_url_replacement(self):
        """Test that sync engine uses correct database URL format."""
        async_url = "postgresql+asyncpg://user:pass@localhost:5432/dbname"
        expected_sync_url = "postgresql://user:pass@localhost:5432/dbname"
        
        # Test the URL replacement logic
        sync_url = async_url.replace("postgresql+asyncpg://", "postgresql://")
        assert sync_url == expected_sync_url
    
    def test_database_url_replacement_complex(self):
        """Test database URL replacement with complex URLs."""
        test_cases = [
            (
                "postgresql+asyncpg://user:password@host:5432/database?sslmode=require",
                "postgresql://user:password@host:5432/database?sslmode=require"
            ),
            (
                "postgresql+asyncpg://localhost/testdb",
                "postgresql://localhost/testdb"
            ),
            (
                "postgresql+asyncpg://user@localhost:5432/db",
                "postgresql://user@localhost:5432/db"
            ),
        ]
        
        for async_url, expected_sync_url in test_cases:
            sync_url = async_url.replace("postgresql+asyncpg://", "postgresql://")
            assert sync_url == expected_sync_url


class TestDatabaseEngineProperties:
    """Test database engine configuration properties."""
    
    @patch('app.database.settings')
    def test_engine_configuration_debug_true(self, mock_settings):
        """Test engine configuration when DEBUG is True."""
        mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@localhost/test"
        mock_settings.DATABASE_POOL_SIZE = 10
        mock_settings.DATABASE_MAX_OVERFLOW = 20
        mock_settings.DEBUG = True
        
        with patch('app.database.create_async_engine') as mock_create_async:
            with patch('app.database.create_engine') as mock_create_sync:
                # Import after mocking
                import importlib
                import app.database
                importlib.reload(app.database)
                
                # Verify async engine has echo=True
                mock_create_async.assert_called_with(
                    mock_settings.DATABASE_URL,
                    pool_size=mock_settings.DATABASE_POOL_SIZE,
                    max_overflow=mock_settings.DATABASE_MAX_OVERFLOW,
                    echo=True,
                )
                
                # Verify sync engine has echo=True
                mock_create_sync.assert_called_with(
                    "postgresql://user:pass@localhost/test",
                    pool_size=mock_settings.DATABASE_POOL_SIZE,
                    max_overflow=mock_settings.DATABASE_MAX_OVERFLOW,
                    echo=True,
                )
    
    @patch('app.database.settings')
    def test_engine_configuration_debug_false(self, mock_settings):
        """Test engine configuration when DEBUG is False."""
        mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@localhost/test"
        mock_settings.DATABASE_POOL_SIZE = 10
        mock_settings.DATABASE_MAX_OVERFLOW = 20
        mock_settings.DEBUG = False
        
        with patch('app.database.create_async_engine') as mock_create_async:
            with patch('app.database.create_engine') as mock_create_sync:
                # Import after mocking
                import importlib
                import app.database
                importlib.reload(app.database)
                
                # Verify async engine has echo=False
                mock_create_async.assert_called_with(
                    mock_settings.DATABASE_URL,
                    pool_size=mock_settings.DATABASE_POOL_SIZE,
                    max_overflow=mock_settings.DATABASE_MAX_OVERFLOW,
                    echo=False,
                )
                
                # Verify sync engine has echo=False
                mock_create_sync.assert_called_with(
                    "postgresql://user:pass@localhost/test",
                    pool_size=mock_settings.DATABASE_POOL_SIZE,
                    max_overflow=mock_settings.DATABASE_MAX_OVERFLOW,
                    echo=False,
                )


class TestDatabaseModuleImports:
    """Test that database module imports and exports are correct."""
    
    def test_module_exports(self):
        """Test that all expected functions and objects are exported."""
        import app.database as db_module
        
        # Test that all expected exports exist
        assert hasattr(db_module, 'get_db')
        assert hasattr(db_module, 'init_db')
        assert hasattr(db_module, 'close_db')
        assert hasattr(db_module, 'get_db_session')
        assert hasattr(db_module, 'async_engine')
        assert hasattr(db_module, 'sync_engine')
        assert hasattr(db_module, 'AsyncSessionLocal')
        assert hasattr(db_module, 'SessionLocal')
        assert hasattr(db_module, 'logger')
    
    def test_logger_configuration(self):
        """Test that logger is properly configured."""
        import app.database as db_module
        
        # Test that logger exists and has the correct name
        assert hasattr(db_module, 'logger')
        # The logger should be a structlog BoundLogger or similar
        assert hasattr(db_module.logger, 'info')
        assert hasattr(db_module.logger, 'error')
        assert hasattr(db_module.logger, 'warning')


class TestDatabaseIntegration:
    """Integration tests for database functionality."""
    
    @pytest.mark.asyncio
    async def test_database_session_lifecycle_complete(self):
        """Test complete database session lifecycle."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session_factory = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_session_factory.return_value.__aexit__.return_value = None
        
        with patch('app.database.AsyncSessionLocal', mock_session_factory):
            # Test multiple operations in a single session
            async with get_db() as session:
                # Simulate database operations
                await session.execute("SELECT 1")
                await session.execute("INSERT INTO test VALUES (1)")
                await session.execute("UPDATE test SET value = 2")
            
            # Verify all operations used the same session
            assert mock_session.execute.call_count == 3
            mock_session.commit.assert_called_once()
            mock_session.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_multiple_database_sessions(self):
        """Test using multiple database sessions."""
        mock_session1 = AsyncMock(spec=AsyncSession)
        mock_session2 = AsyncMock(spec=AsyncSession)
        
        session_instances = [mock_session1, mock_session2]
        session_index = 0
        
        def mock_session_factory():
            nonlocal session_index
            session = session_instances[session_index]
            session_index += 1
            
            @asynccontextmanager
            async def session_context():
                yield session
            
            return session_context()
        
        with patch('app.database.AsyncSessionLocal', side_effect=mock_session_factory):
            # Use first session
            async with get_db() as session1:
                assert session1 == mock_session1
                await session1.execute("SELECT 1")
            
            # Use second session
            async with get_db() as session2:
                assert session2 == mock_session2
                await session2.execute("SELECT 2")
            
            # Verify both sessions were used independently
            mock_session1.execute.assert_called_once_with("SELECT 1")
            mock_session2.execute.assert_called_once_with("SELECT 2")
            mock_session1.commit.assert_called_once()
            mock_session2.commit.assert_called_once()