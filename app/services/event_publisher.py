"""RabbitMQ event publishing service."""

import json
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
import uuid

import pika
from pika import PlainCredentials
from pika.adapters.asyncio_connection import AsyncioConnection
from pika.exchange_type import ExchangeType

from app.config import settings
from app.utils.logging import get_logger


class EventPublisher:
    """RabbitMQ event publisher."""
    
    def __init__(self):
        """Initialize event publisher."""
        self.logger = get_logger(self.__class__.__name__)
        self.connection = None
        self.channel = None
        self.exchange_name = settings.RABBITMQ_EXCHANGE
        self.queue_name = settings.RABBITMQ_QUEUE
        self.connected = False
    
    async def connect(self) -> None:
        """Connect to RabbitMQ."""
        try:
            # Parse RabbitMQ URL
            import urllib.parse
            parsed = urllib.parse.urlparse(settings.RABBITMQ_URL)
            
            # Connection parameters
            connection_params = pika.ConnectionParameters(
                host=parsed.hostname,
                port=parsed.port or 5672,
                virtual_host=parsed.path.lstrip('/') or '/',
                credentials=PlainCredentials(
                    username=parsed.username or 'guest',
                    password=parsed.password or 'guest'
                ),
                heartbeat=600,
                blocked_connection_timeout=300,
            )
            
            # Create connection
            self.connection = await asyncio.get_event_loop().create_future()
            AsyncioConnection(
                connection_params,
                on_open_callback=self._on_connection_open,
                on_open_error_callback=self._on_connection_open_error,
                on_close_callback=self._on_connection_closed,
            )
            
            # Wait for connection
            await self.connection
            
            self.logger.info("Connected to RabbitMQ successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to connect to RabbitMQ: {e}")
            raise
    
    def _on_connection_open(self, connection) -> None:
        """Handle connection open."""
        self.connection.set_result(connection)
        self.connected = True
        
        # Open channel
        connection.channel(on_open_callback=self._on_channel_open)
    
    def _on_connection_open_error(self, connection, error) -> None:
        """Handle connection open error."""
        self.logger.error(f"RabbitMQ connection open error: {error}")
        self.connection.set_exception(Exception(f"Connection failed: {error}"))
    
    def _on_connection_closed(self, connection, reason) -> None:
        """Handle connection closed."""
        self.logger.warning(f"RabbitMQ connection closed: {reason}")
        self.connected = False
        self.channel = None
    
    def _on_channel_open(self, channel) -> None:
        """Handle channel open."""
        self.channel = channel
        
        # Declare exchange
        channel.exchange_declare(
            exchange=self.exchange_name,
            exchange_type=ExchangeType.topic,
            durable=True,
            callback=self._on_exchange_declare,
        )
    
    def _on_exchange_declare(self, method_frame) -> None:
        """Handle exchange declaration."""
        self.logger.info(f"Exchange '{self.exchange_name}' declared")
        
        # Declare queue
        self.channel.queue_declare(
            queue=self.queue_name,
            durable=True,
            callback=self._on_queue_declare,
        )
    
    def _on_queue_declare(self, method_frame) -> None:
        """Handle queue declaration."""
        self.logger.info(f"Queue '{self.queue_name}' declared")
        
        # Bind queue to exchange
        self.channel.queue_bind(
            queue=self.queue_name,
            exchange=self.exchange_name,
            routing_key="document.*",
            callback=self._on_queue_bind,
        )
    
    def _on_queue_bind(self, method_frame) -> None:
        """Handle queue binding."""
        self.logger.info(f"Queue '{self.queue_name}' bound to exchange '{self.exchange_name}'")
    
    async def disconnect(self) -> None:
        """Disconnect from RabbitMQ."""
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
        self.connected = False
        self.logger.info("Disconnected from RabbitMQ")
    
    async def publish_event(
        self,
        event_type: str,
        data: Dict[str, Any],
        routing_key: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> bool:
        """Publish an event to RabbitMQ."""
        if not self.connected or not self.channel:
            self.logger.error("Not connected to RabbitMQ")
            return False
        
        try:
            # Prepare message
            message = {
                "event_type": event_type,
                "event_id": str(uuid.uuid4()),
                "timestamp": datetime.utcnow().isoformat(),
                "service": "document-service",
                "data": data,
            }
            
            if correlation_id:
                message["correlation_id"] = correlation_id
            
            # Prepare routing key
            if routing_key is None:
                routing_key = f"document.{event_type}"
            
            # Publish message
            self.channel.basic_publish(
                exchange=self.exchange_name,
                routing_key=routing_key,
                body=json.dumps(message, default=str),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Make message persistent
                    content_type="application/json",
                    correlation_id=correlation_id,
                    message_id=message["event_id"],
                    timestamp=datetime.utcnow(),
                ),
            )
            
            self.logger.info(f"Published event: {event_type} with routing key: {routing_key}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to publish event {event_type}: {e}")
            return False
    
    async def publish_document_uploaded(
        self,
        document_id: str,
        filename: str,
        content_type: str,
        size_bytes: int,
        owner_id: str,
        tenant_id: str,
    ) -> bool:
        """Publish document uploaded event."""
        data = {
            "document_id": document_id,
            "filename": filename,
            "content_type": content_type,
            "size_bytes": size_bytes,
            "owner_id": owner_id,
            "tenant_id": tenant_id,
        }
        
        return await self.publish_event("uploaded", data)
    
    async def publish_document_scanned(
        self,
        document_id: str,
        scan_id: str,
        result: str,
        threats: list,
        tenant_id: str,
    ) -> bool:
        """Publish document scanned event."""
        data = {
            "document_id": document_id,
            "scan_id": scan_id,
            "result": result,
            "threats": threats,
            "tenant_id": tenant_id,
        }
        
        return await self.publish_event("scanned", data)
    
    async def publish_document_deleted(
        self,
        document_id: str,
        filename: str,
        owner_id: str,
        tenant_id: str,
    ) -> bool:
        """Publish document deleted event."""
        data = {
            "document_id": document_id,
            "filename": filename,
            "owner_id": owner_id,
            "tenant_id": tenant_id,
        }
        
        return await self.publish_event("deleted", data)
    
    async def health_check(self) -> bool:
        """Check RabbitMQ health."""
        return self.connected and self.channel is not None


# Global event publisher instance
event_publisher = EventPublisher()