"""Unit tests for virus scanner service."""

import pytest
import uuid
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch
from io import BytesIO

from app.services.virus_scanner import ClamAVScanner, virus_scanner
from app.models.document import (
    ScanStatus,
    ScanResultType,
    ThreatSeverity,
    ScanResult,
    ThreatDetail,
)


class TestClamAVScanner:
    """Test ClamAV scanner implementation."""
    
    @pytest.fixture
    def scanner(self):
        """Create scanner instance."""
        with patch('app.services.virus_scanner.settings') as mock_settings:
            mock_settings.CLAMAV_HOST = "localhost"
            mock_settings.CLAMAV_PORT = 3310
            mock_settings.VIRUS_SCAN_ENABLED = True
            return ClamAVScanner()
    
    @pytest.fixture
    def disabled_scanner(self):
        """Create disabled scanner instance."""
        with patch('app.services.virus_scanner.settings') as mock_settings:
            mock_settings.CLAMAV_HOST = "localhost"
            mock_settings.CLAMAV_PORT = 3310
            mock_settings.VIRUS_SCAN_ENABLED = False
            return ClamAVScanner()
    
    @pytest.fixture
    def sample_file_data(self):
        """Create sample file data."""
        return b"Sample file content for virus scanning"
    
    @pytest.mark.asyncio
    async def test_scan_bytes_disabled(self, disabled_scanner, sample_file_data):
        """Test scanning when virus scanning is disabled."""
        document_id = str(uuid.uuid4())
        
        result = await disabled_scanner.scan_bytes(sample_file_data, document_id)
        
        assert isinstance(result, ScanResult)
        assert result.document_id == document_id
        assert result.status == ScanStatus.COMPLETED
        assert result.result == ScanResultType.CLEAN
        assert result.scanner_version == "disabled"
        assert len(result.threats) == 0
        assert result.duration_ms == 0
    
    @pytest.mark.asyncio
    async def test_scan_bytes_clean_file(self, scanner, sample_file_data):
        """Test scanning clean file."""
        document_id = str(uuid.uuid4())
        
        with patch.object(scanner, '_scan_with_clamav') as mock_scan:
            mock_scan.return_value = {
                "infected": False,
                "threats": [],
                "error": False,
                "version": "ClamAV 0.103.8",
            }
            
            with patch('app.services.virus_scanner.redis_client') as mock_redis:
                mock_redis.create_scan_job = AsyncMock(return_value=True)
                mock_redis.update_scan_job = AsyncMock(return_value=True)
                
                with patch.object(scanner, '_store_scan_result_db') as mock_store:
                    mock_store.return_value = None
                    
                    with patch('app.services.virus_scanner.event_publisher') as mock_publisher:
                        mock_publisher.publish_document_scanned = AsyncMock(return_value=True)
                        
                        result = await scanner.scan_bytes(sample_file_data, document_id)
        
        assert isinstance(result, ScanResult)
        assert result.document_id == document_id
        assert result.status == ScanStatus.COMPLETED
        assert result.result == ScanResultType.CLEAN
        assert result.scanner_version == "ClamAV 0.103.8"
        assert len(result.threats) == 0
        assert result.duration_ms > 0
        
        # Verify Redis operations
        mock_redis.create_scan_job.assert_called_once()
        assert mock_redis.update_scan_job.call_count >= 2  # At least scanning and completed
    
    @pytest.mark.asyncio
    async def test_scan_bytes_infected_file(self, scanner, sample_file_data):
        """Test scanning infected file."""
        document_id = str(uuid.uuid4())
        
        with patch.object(scanner, '_scan_with_clamav') as mock_scan:
            mock_scan.return_value = {
                "infected": True,
                "threats": ["Win.Test.EICAR_HDB-1"],
                "error": False,
                "version": "ClamAV 0.103.8",
            }
            
            with patch('app.services.virus_scanner.redis_client') as mock_redis:
                mock_redis.create_scan_job = AsyncMock(return_value=True)
                mock_redis.update_scan_job = AsyncMock(return_value=True)
                
                with patch.object(scanner, '_store_scan_result_db') as mock_store:
                    mock_store.return_value = None
                    
                    with patch('app.services.virus_scanner.event_publisher') as mock_publisher:
                        mock_publisher.publish_document_scanned = AsyncMock(return_value=True)
                        
                        result = await scanner.scan_bytes(sample_file_data, document_id)
        
        assert isinstance(result, ScanResult)
        assert result.document_id == document_id
        assert result.status == ScanStatus.COMPLETED
        assert result.result == ScanResultType.INFECTED
        assert result.scanner_version == "ClamAV 0.103.8"
        assert len(result.threats) == 1
        assert result.threats[0].name == "Win.Test.EICAR_HDB-1"
        assert result.threats[0].type == "virus"
        assert result.threats[0].severity == ThreatSeverity.HIGH
        assert result.duration_ms > 0
    
    @pytest.mark.asyncio
    async def test_scan_bytes_scan_error(self, scanner, sample_file_data):
        """Test scanning with scan error."""
        document_id = str(uuid.uuid4())
        
        with patch.object(scanner, '_scan_with_clamav') as mock_scan:
            mock_scan.return_value = {
                "infected": False,
                "threats": [],
                "error": True,
                "error_message": "Scan failed",
                "version": "ClamAV 0.103.8",
            }
            
            with patch('app.services.virus_scanner.redis_client') as mock_redis:
                mock_redis.create_scan_job = AsyncMock(return_value=True)
                mock_redis.update_scan_job = AsyncMock(return_value=True)
                
                with patch.object(scanner, '_store_scan_result_db') as mock_store:
                    mock_store.return_value = None
                    
                    with patch('app.services.virus_scanner.event_publisher') as mock_publisher:
                        mock_publisher.publish_document_scanned = AsyncMock(return_value=True)
                        
                        result = await scanner.scan_bytes(sample_file_data, document_id)
        
        assert isinstance(result, ScanResult)
        assert result.document_id == document_id
        assert result.status == ScanStatus.COMPLETED
        assert result.result == ScanResultType.ERROR
        assert result.scanner_version == "ClamAV 0.103.8"
        assert len(result.threats) == 0
    
    @pytest.mark.asyncio
    async def test_scan_bytes_exception(self, scanner, sample_file_data):
        """Test scanning with exception."""
        document_id = str(uuid.uuid4())
        
        with patch.object(scanner, '_scan_with_clamav') as mock_scan:
            mock_scan.side_effect = Exception("Connection failed")
            
            with patch('app.services.virus_scanner.redis_client') as mock_redis:
                mock_redis.create_scan_job = AsyncMock(return_value=True)
                mock_redis.update_scan_job = AsyncMock(return_value=True)
                
                result = await scanner.scan_bytes(sample_file_data, document_id)
        
        assert isinstance(result, ScanResult)
        assert result.document_id == document_id
        assert result.status == ScanStatus.FAILED
        assert result.result == ScanResultType.ERROR
        assert result.scanner_version == "error"
        assert len(result.threats) == 0
        
        # Verify error was logged in Redis
        mock_redis.update_scan_job.assert_called()
        error_call = [call for call in mock_redis.update_scan_job.call_args_list 
                     if 'error_message' in call.kwargs or 
                        (len(call.args) > 0 and 'error_message' in call.args)]
        assert len(error_call) > 0
    
    @pytest.mark.asyncio
    async def test_scan_with_clamav_clean(self, scanner):
        """Test ClamAV scan with clean result."""
        data = b"Clean test file"
        
        mock_reader = AsyncMock()
        mock_writer = AsyncMock()
        mock_reader.read.return_value = b"stream: OK\0"
        
        with patch('asyncio.open_connection') as mock_connection:
            mock_connection.return_value = (mock_reader, mock_writer)
            
            with patch.object(scanner, '_get_version') as mock_version:
                mock_version.return_value = "ClamAV 0.103.8"
                
                result = await scanner._scan_with_clamav(data)
        
        assert result["infected"] is False
        assert result["threats"] == []
        assert result["error"] is False
        assert result["version"] == "ClamAV 0.103.8"
        
        # Verify ClamAV protocol
        mock_writer.write.assert_any_call(b"zINSTREAM\0")
        mock_writer.write.assert_any_call(b'\x00\x00\x00\x00')  # End marker
    
    @pytest.mark.asyncio
    async def test_scan_with_clamav_infected(self, scanner):
        """Test ClamAV scan with infected result."""
        data = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
        
        mock_reader = AsyncMock()
        mock_writer = AsyncMock()
        mock_reader.read.return_value = b"stream: Win.Test.EICAR_HDB-1 FOUND\0"
        
        with patch('asyncio.open_connection') as mock_connection:
            mock_connection.return_value = (mock_reader, mock_writer)
            
            with patch.object(scanner, '_get_version') as mock_version:
                mock_version.return_value = "ClamAV 0.103.8"
                
                result = await scanner._scan_with_clamav(data)
        
        assert result["infected"] is True
        assert result["threats"] == ["Win.Test.EICAR_HDB-1"]
        assert result["error"] is False
        assert result["version"] == "ClamAV 0.103.8"
    
    @pytest.mark.asyncio
    async def test_scan_with_clamav_timeout(self, scanner):
        """Test ClamAV scan with timeout."""
        data = b"Test file"
        
        with patch('asyncio.open_connection') as mock_connection:
            mock_connection.side_effect = asyncio.TimeoutError()
            
            result = await scanner._scan_with_clamav(data)
        
        assert result["infected"] is False
        assert result["threats"] == []
        assert result["error"] is True
        assert "timeout" in result["error_message"].lower()
        assert result["version"] == "unknown"
    
    @pytest.mark.asyncio
    async def test_scan_with_clamav_connection_error(self, scanner):
        """Test ClamAV scan with connection error."""
        data = b"Test file"
        
        with patch('asyncio.open_connection') as mock_connection:
            mock_connection.side_effect = ConnectionRefusedError("Connection refused")
            
            result = await scanner._scan_with_clamav(data)
        
        assert result["infected"] is False
        assert result["threats"] == []
        assert result["error"] is True
        assert "Connection refused" in result["error_message"]
        assert result["version"] == "unknown"
    
    @pytest.mark.asyncio
    async def test_get_version_success(self, scanner):
        """Test getting ClamAV version successfully."""
        mock_reader = AsyncMock()
        mock_writer = AsyncMock()
        mock_reader.read.return_value = b"ClamAV 0.103.8/27147/Fri Jul  5 09:36:04 2025\0"
        
        with patch('asyncio.open_connection') as mock_connection:
            mock_connection.return_value = (mock_reader, mock_writer)
            
            version = await scanner._get_version()
        
        assert version == "ClamAV 0.103.8/27147/Fri Jul  5 09:36:04 2025"
        mock_writer.write.assert_called_once_with(b"zVERSION\0")
    
    @pytest.mark.asyncio
    async def test_get_version_error(self, scanner):
        """Test getting ClamAV version with error."""
        with patch('asyncio.open_connection') as mock_connection:
            mock_connection.side_effect = Exception("Connection failed")
            
            version = await scanner._get_version()
        
        assert version == "unknown"
    
    @pytest.mark.asyncio
    async def test_health_check_enabled_success(self, scanner):
        """Test health check when enabled and successful."""
        mock_reader = AsyncMock()
        mock_writer = AsyncMock()
        mock_reader.read.return_value = b"PONG\0"
        
        with patch('asyncio.open_connection') as mock_connection:
            mock_connection.return_value = (mock_reader, mock_writer)
            
            health = await scanner.health_check()
        
        assert health is True
        mock_writer.write.assert_called_once_with(b"zPING\0")
    
    @pytest.mark.asyncio
    async def test_health_check_enabled_failure(self, scanner):
        """Test health check when enabled but fails."""
        mock_reader = AsyncMock()
        mock_writer = AsyncMock()
        mock_reader.read.return_value = b"ERROR\0"
        
        with patch('asyncio.open_connection') as mock_connection:
            mock_connection.return_value = (mock_reader, mock_writer)
            
            health = await scanner.health_check()
        
        assert health is False
    
    @pytest.mark.asyncio
    async def test_health_check_disabled(self, disabled_scanner):
        """Test health check when disabled."""
        health = await disabled_scanner.health_check()
        assert health is True
    
    @pytest.mark.asyncio
    async def test_health_check_connection_error(self, scanner):
        """Test health check with connection error."""
        with patch('asyncio.open_connection') as mock_connection:
            mock_connection.side_effect = Exception("Connection failed")
            
            health = await scanner.health_check()
        
        assert health is False
    
    @pytest.mark.asyncio
    async def test_store_scan_result_db_success(self, scanner):
        """Test storing scan result in database successfully."""
        scan_result = ScanResult(
            scan_id=str(uuid.uuid4()),
            document_id=str(uuid.uuid4()),
            status=ScanStatus.COMPLETED,
            result=ScanResultType.INFECTED,
            scanned_at=datetime.utcnow(),
            duration_ms=1000,
            threats=[
                ThreatDetail(
                    name="TestThreat",
                    type="virus",
                    severity=ThreatSeverity.HIGH,
                    description="Test threat",
                )
            ],
            scanner_version="ClamAV 0.103.8",
        )
        
        with patch('app.services.virus_scanner.get_db') as mock_get_db:
            mock_db = AsyncMock()
            mock_db.add = Mock()
            mock_db.commit = AsyncMock()
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=mock_db)
            mock_context.__aexit__ = AsyncMock(return_value=None)
            mock_get_db.return_value = mock_context
            
            await scanner._store_scan_result_db(scan_result)
        
        # Verify database operations
        assert mock_db.add.call_count == 2  # ScanResult + ThreatDetail
        mock_db.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_store_scan_result_db_error(self, scanner):
        """Test storing scan result in database with error."""
        scan_result = ScanResult(
            scan_id=str(uuid.uuid4()),
            document_id=str(uuid.uuid4()),
            status=ScanStatus.COMPLETED,
            result=ScanResultType.CLEAN,
            scanned_at=datetime.utcnow(),
            duration_ms=500,
            threats=[],
            scanner_version="ClamAV 0.103.8",
        )
        
        with patch('app.services.virus_scanner.get_db') as mock_get_db:
            mock_get_db.side_effect = Exception("Database error")
            
            with pytest.raises(Exception) as exc_info:
                await scanner._store_scan_result_db(scan_result)
            
            assert "Database error" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_scan_large_file(self, scanner):
        """Test scanning large file with chunking."""
        # Create a large file (larger than 8192 bytes chunk size)
        large_data = b"A" * 20000
        document_id = str(uuid.uuid4())
        
        mock_reader = AsyncMock()
        mock_writer = AsyncMock()
        mock_reader.read.return_value = b"stream: OK\0"
        
        with patch('asyncio.open_connection') as mock_connection:
            mock_connection.return_value = (mock_reader, mock_writer)
            
            with patch.object(scanner, '_get_version') as mock_version:
                mock_version.return_value = "ClamAV 0.103.8"
                
                result = await scanner._scan_with_clamav(large_data)
        
        assert result["infected"] is False
        assert result["error"] is False
        
        # Verify multiple chunks were sent
        write_calls = mock_writer.write.call_args_list
        data_writes = [call for call in write_calls if len(call[0][0]) > 100]  # Data chunks
        assert len(data_writes) >= 3  # Should have multiple chunks for 20KB file
    
    @pytest.mark.asyncio
    async def test_multiple_threats_detected(self, scanner, sample_file_data):
        """Test scanning file with multiple threats."""
        document_id = str(uuid.uuid4())
        
        with patch.object(scanner, '_scan_with_clamav') as mock_scan:
            mock_scan.return_value = {
                "infected": True,
                "threats": ["Threat1", "Threat2", "Threat3"],
                "error": False,
                "version": "ClamAV 0.103.8",
            }
            
            with patch('app.services.virus_scanner.redis_client') as mock_redis:
                mock_redis.create_scan_job = AsyncMock(return_value=True)
                mock_redis.update_scan_job = AsyncMock(return_value=True)
                
                with patch.object(scanner, '_store_scan_result_db') as mock_store:
                    mock_store.return_value = None
                    
                    with patch('app.services.virus_scanner.event_publisher') as mock_publisher:
                        mock_publisher.publish_document_scanned = AsyncMock(return_value=True)
                        
                        result = await scanner.scan_bytes(sample_file_data, document_id)
        
        assert result.result == ScanResultType.INFECTED
        assert len(result.threats) == 3
        assert all(threat.severity == ThreatSeverity.HIGH for threat in result.threats)
        assert all(threat.type == "virus" for threat in result.threats)
    
    @pytest.mark.asyncio
    async def test_scan_event_publish_failure(self, scanner, sample_file_data):
        """Test scanning with event publishing failure."""
        document_id = str(uuid.uuid4())
        
        with patch.object(scanner, '_scan_with_clamav') as mock_scan:
            mock_scan.return_value = {
                "infected": False,
                "threats": [],
                "error": False,
                "version": "ClamAV 0.103.8",
            }
            
            with patch('app.services.virus_scanner.redis_client') as mock_redis:
                mock_redis.create_scan_job = AsyncMock(return_value=True)
                mock_redis.update_scan_job = AsyncMock(return_value=True)
                
                with patch.object(scanner, '_store_scan_result_db') as mock_store:
                    mock_store.return_value = None
                    
                    with patch('app.services.virus_scanner.event_publisher') as mock_publisher:
                        mock_publisher.publish_document_scanned = AsyncMock(
                            side_effect=Exception("Publishing failed")
                        )
                        
                        # Should still complete successfully despite publish failure
                        result = await scanner.scan_bytes(sample_file_data, document_id)
        
        assert result.status == ScanStatus.COMPLETED
        assert result.result == ScanResultType.CLEAN
    
    @pytest.mark.asyncio
    async def test_scan_db_store_failure(self, scanner, sample_file_data):
        """Test scanning with database storage failure."""
        document_id = str(uuid.uuid4())
        
        with patch.object(scanner, '_scan_with_clamav') as mock_scan:
            mock_scan.return_value = {
                "infected": False,
                "threats": [],
                "error": False,
                "version": "ClamAV 0.103.8",
            }
            
            with patch('app.services.virus_scanner.redis_client') as mock_redis:
                mock_redis.create_scan_job = AsyncMock(return_value=True)
                mock_redis.update_scan_job = AsyncMock(return_value=True)
                
                with patch.object(scanner, '_store_scan_result_db') as mock_store:
                    mock_store.side_effect = Exception("Database failed")
                    
                    with patch('app.services.virus_scanner.event_publisher') as mock_publisher:
                        mock_publisher.publish_document_scanned = AsyncMock(return_value=True)
                        
                        # Should still complete successfully despite DB failure
                        result = await scanner.scan_bytes(sample_file_data, document_id)
        
        assert result.status == ScanStatus.COMPLETED
        assert result.result == ScanResultType.CLEAN


class TestGlobalVirusScanner:
    """Test global virus scanner instance."""
    
    def test_global_instance_exists(self):
        """Test that global virus scanner instance exists."""
        from app.services.virus_scanner import virus_scanner
        assert virus_scanner is not None
        assert isinstance(virus_scanner, ClamAVScanner)
    
    @pytest.mark.asyncio
    async def test_global_instance_health_check(self):
        """Test global instance health check."""
        with patch('app.services.virus_scanner.settings') as mock_settings:
            mock_settings.VIRUS_SCAN_ENABLED = False
            
            health = await virus_scanner.health_check()
            assert health is True