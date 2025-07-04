"""ClamAV virus scanning service."""

import asyncio
import socket
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

from app.config import settings
from app.models.document import ScanStatus, ScanResultType, ThreatSeverity, ScanResult, ThreatDetail
from app.services.redis_client import redis_client
from app.utils.logging import get_logger, log_document_event


class ClamAVScanner:
    """ClamAV virus scanner implementation."""
    
    def __init__(self):
        """Initialize ClamAV scanner."""
        self.logger = get_logger(self.__class__.__name__)
        self.host = settings.CLAMAV_HOST
        self.port = settings.CLAMAV_PORT
        self.enabled = settings.VIRUS_SCAN_ENABLED
    
    async def scan_bytes(self, data: bytes, document_id: str) -> ScanResult:
        """Scan bytes for viruses."""
        if not self.enabled:
            self.logger.info("Virus scanning disabled, returning clean result")
            return ScanResult(
                scan_id=str(uuid.uuid4()),
                document_id=document_id,
                status=ScanStatus.COMPLETED,
                result=ScanResultType.CLEAN,
                scanned_at=datetime.utcnow(),
                duration_ms=0,
                threats=[],
                scanner_version="disabled",
            )
        
        scan_id = str(uuid.uuid4())
        start_time = datetime.utcnow()
        
        try:
            # Create scan job in Redis
            await redis_client.create_scan_job(
                scan_id=scan_id,
                document_id=document_id,
                user_id="system",  # System-initiated scan
                tenant_id="system",
            )
            
            # Update status to scanning
            await redis_client.update_scan_job(
                scan_id=scan_id,
                status=ScanStatus.SCANNING.value,
            )
            
            # Perform scan
            scan_result = await self._scan_with_clamav(data)
            
            # Calculate duration
            end_time = datetime.utcnow()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            
            # Parse threats
            threats = []
            if scan_result["infected"]:
                for threat_name in scan_result["threats"]:
                    threat = ThreatDetail(
                        name=threat_name,
                        type="virus",
                        severity=ThreatSeverity.HIGH,
                        description=f"Threat detected: {threat_name}",
                    )
                    threats.append(threat)
            
            # Determine result type
            if scan_result["infected"]:
                result_type = ScanResultType.INFECTED
            elif scan_result["error"]:
                result_type = ScanResultType.ERROR
            else:
                result_type = ScanResultType.CLEAN
            
            # Create result
            result = ScanResult(
                scan_id=scan_id,
                document_id=document_id,
                status=ScanStatus.COMPLETED,
                result=result_type,
                scanned_at=end_time,
                duration_ms=duration_ms,
                threats=threats,
                scanner_version=scan_result.get("version", "unknown"),
            )
            
            # Update scan job in Redis
            await redis_client.update_scan_job(
                scan_id=scan_id,
                status=ScanStatus.COMPLETED.value,
                result=result_type.value,
                threats=[threat.dict() for threat in threats],
                duration_ms=duration_ms,
            )
            
            # Log event
            self.logger.info(f"Virus scan completed: {scan_id}, result: {result_type}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Virus scan failed: {e}")
            
            # Update scan job with error
            await redis_client.update_scan_job(
                scan_id=scan_id,
                status=ScanStatus.FAILED.value,
                error_message=str(e),
            )
            
            # Return error result
            return ScanResult(
                scan_id=scan_id,
                document_id=document_id,
                status=ScanStatus.FAILED,
                result=ScanResultType.ERROR,
                scanned_at=datetime.utcnow(),
                duration_ms=0,
                threats=[],
                scanner_version="error",
            )
    
    async def _scan_with_clamav(self, data: bytes) -> Dict[str, Any]:
        """Perform actual ClamAV scan."""
        try:
            # Connect to ClamAV daemon
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=30.0,
            )
            
            try:
                # Send scan command
                writer.write(b"zINSTREAM\0")
                await writer.drain()
                
                # Send data in chunks
                chunk_size = 8192
                offset = 0
                
                while offset < len(data):
                    chunk = data[offset:offset + chunk_size]
                    chunk_len = len(chunk)
                    
                    # Send chunk length (4 bytes, big endian)
                    writer.write(chunk_len.to_bytes(4, byteorder='big'))
                    # Send chunk data
                    writer.write(chunk)
                    await writer.drain()
                    
                    offset += chunk_size
                
                # Send end of data marker
                writer.write(b'\x00\x00\x00\x00')
                await writer.drain()
                
                # Read response
                response = await asyncio.wait_for(
                    reader.read(1024),
                    timeout=30.0,
                )
                
                response_str = response.decode('utf-8').strip()
                
                # Parse response
                if response_str.endswith("OK"):
                    return {
                        "infected": False,
                        "threats": [],
                        "error": False,
                        "version": await self._get_version(),
                    }
                elif "FOUND" in response_str:
                    # Extract threat name
                    threat_name = response_str.split(":")[1].strip().replace(" FOUND", "")
                    return {
                        "infected": True,
                        "threats": [threat_name],
                        "error": False,
                        "version": await self._get_version(),
                    }
                else:
                    return {
                        "infected": False,
                        "threats": [],
                        "error": True,
                        "error_message": response_str,
                        "version": await self._get_version(),
                    }
                    
            finally:
                writer.close()
                await writer.wait_closed()
                
        except asyncio.TimeoutError:
            self.logger.error("ClamAV scan timed out")
            return {
                "infected": False,
                "threats": [],
                "error": True,
                "error_message": "Scan timeout",
                "version": "unknown",
            }
        except Exception as e:
            self.logger.error(f"ClamAV scan error: {e}")
            return {
                "infected": False,
                "threats": [],
                "error": True,
                "error_message": str(e),
                "version": "unknown",
            }
    
    async def _get_version(self) -> str:
        """Get ClamAV version."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=10.0,
            )
            
            try:
                writer.write(b"zVERSION\0")
                await writer.drain()
                
                response = await asyncio.wait_for(
                    reader.read(1024),
                    timeout=10.0,
                )
                
                return response.decode('utf-8').strip()
                
            finally:
                writer.close()
                await writer.wait_closed()
                
        except Exception as e:
            self.logger.error(f"Failed to get ClamAV version: {e}")
            return "unknown"
    
    async def health_check(self) -> bool:
        """Check ClamAV health."""
        if not self.enabled:
            return True
        
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=10.0,
            )
            
            try:
                writer.write(b"zPING\0")
                await writer.drain()
                
                response = await asyncio.wait_for(
                    reader.read(1024),
                    timeout=10.0,
                )
                
                return response.decode('utf-8').strip() == "PONG"
                
            finally:
                writer.close()
                await writer.wait_closed()
                
        except Exception as e:
            self.logger.error(f"ClamAV health check failed: {e}")
            return False


# Global scanner instance
virus_scanner = ClamAVScanner()