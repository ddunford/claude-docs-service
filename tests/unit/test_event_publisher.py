"""Unit tests for event publisher service."""

import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch, MagicMock

import pytest
import pika
from pika.adapters.asyncio_connection import AsyncioConnection

from app.services.event_publisher import EventPublisher, event_publisher


class TestEventPublisher:
    """Test RabbitMQ event publisher."""
    
    @pytest.fixture
    def publisher(self):
        """Create event publisher instance."""
        with patch('app.services.event_publisher.settings') as mock_settings:
            mock_settings.RABBITMQ_URL = "amqp://user:password@localhost:5672/vhost"
            mock_settings.RABBITMQ_EXCHANGE = "document-events"
            mock_settings.RABBITMQ_QUEUE = "document-queue"
            return EventPublisher()
    
    @pytest.fixture
    def mock_connection(self):
        """Create mock RabbitMQ connection."""
        connection = Mock()
        connection.is_closed = False
        connection.close = AsyncMock()
        return connection
    
    @pytest.fixture
    def mock_channel(self):
        """Create mock RabbitMQ channel."""
        channel = Mock()
        channel.exchange_declare = Mock()
        channel.queue_declare = Mock()
        channel.queue_bind = Mock()
        channel.basic_publish = Mock()
        return channel
    
    def test_init(self, publisher):
        """Test publisher initialization."""
        assert publisher.exchange_name == "document-events"
        assert publisher.queue_name == "document-queue"
        assert publisher.connection is None
        assert publisher.channel is None
        assert publisher.connected is False
    
    @pytest.mark.asyncio
    async def test_connect_success(self, publisher):
        """Test successful RabbitMQ connection."""
        mock_connection = Mock()
        mock_connection.is_closed = False
        
        with patch('pika.ConnectionParameters') as mock_params:
            with patch('app.services.event_publisher.AsyncioConnection') as mock_async_conn:
                # Mock the future creation and resolution
                mock_future = AsyncMock()
                mock_future.set_result = Mock()
                
                with patch('asyncio.get_event_loop') as mock_loop:
                    mock_loop.return_value.create_future.return_value = mock_future
                    
                    # Simulate successful connection
                    async def simulate_connection():
                        publisher._on_connection_open(mock_connection)
                    
                    with patch.object(publisher, '_on_connection_open'):
                        # Mock the connection process
                        publisher.connection = mock_future
                        mock_future.set_result(mock_connection)
                        
                        await publisher.connect()
                        
                        assert publisher.connected is True
    
    @pytest.mark.asyncio
    async def test_connect_failure(self, publisher):
        """Test RabbitMQ connection failure."""
        with patch('pika.ConnectionParameters'):
            with patch('app.services.event_publisher.AsyncioConnection') as mock_async_conn:
                with patch('asyncio.get_event_loop') as mock_loop:
                    mock_future = AsyncMock()
                    mock_future.set_exception = Mock()
                    mock_loop.return_value.create_future.return_value = mock_future
                    
                    publisher.connection = mock_future
                    mock_future.set_exception(Exception("Connection failed"))
                    
                    with pytest.raises(Exception) as exc_info:
                        await publisher.connect()
                    
                    assert "Connection failed" in str(exc_info.value)
    
    def test_on_connection_open(self, publisher):
        """Test connection open callback."""
        mock_connection = Mock()
        mock_future = Mock()
        publisher.connection = mock_future
        
        publisher._on_connection_open(mock_connection)
        
        assert publisher.connected is True
        mock_future.set_result.assert_called_once_with(mock_connection)
        mock_connection.channel.assert_called_once()
    
    def test_on_connection_open_error(self, publisher):
        """Test connection open error callback."""
        mock_connection = Mock()
        mock_future = Mock()
        publisher.connection = mock_future
        error = Exception("Connection error")
        
        publisher._on_connection_open_error(mock_connection, error)
        
        mock_future.set_exception.assert_called_once()
    
    def test_on_connection_closed(self, publisher):
        """Test connection closed callback."""
        mock_connection = Mock()
        publisher.connected = True
        publisher.channel = Mock()
        
        publisher._on_connection_closed(mock_connection, "Normal closure")
        
        assert publisher.connected is False
        assert publisher.channel is None
    
    def test_on_channel_open(self, publisher):
        """Test channel open callback."""
        mock_channel = Mock()
        
        publisher._on_channel_open(mock_channel)
        
        assert publisher.channel == mock_channel
        mock_channel.exchange_declare.assert_called_once_with(
            exchange="document-events",
            exchange_type=pika.exchange_type.ExchangeType.topic,
            durable=True,
            callback=publisher._on_exchange_declare,
        )
    
    def test_on_exchange_declare(self, publisher, mock_channel):
        """Test exchange declaration callback."""
        publisher.channel = mock_channel
        mock_method_frame = Mock()
        
        publisher._on_exchange_declare(mock_method_frame)
        
        mock_channel.queue_declare.assert_called_once_with(
            queue="document-queue",
            durable=True,
            callback=publisher._on_queue_declare,
        )
    
    def test_on_queue_declare(self, publisher, mock_channel):
        """Test queue declaration callback."""
        publisher.channel = mock_channel
        mock_method_frame = Mock()
        
        publisher._on_queue_declare(mock_method_frame)
        
        mock_channel.queue_bind.assert_called_once_with(
            queue="document-queue",
            exchange="document-events",
            routing_key="document.*",
            callback=publisher._on_queue_bind,
        )
    
    def test_on_queue_bind(self, publisher):
        """Test queue binding callback."""
        mock_method_frame = Mock()
        
        # Should complete without error
        publisher._on_queue_bind(mock_method_frame)
    
    @pytest.mark.asyncio
    async def test_disconnect_connected(self, publisher, mock_connection):
        """Test disconnecting when connected."""
        publisher.connection = mock_connection
        publisher.connected = True
        
        await publisher.disconnect()
        
        mock_connection.close.assert_called_once()
        assert publisher.connected is False
    
    @pytest.mark.asyncio
    async def test_disconnect_not_connected(self, publisher):
        """Test disconnecting when not connected."""
        publisher.connection = None
        publisher.connected = False
        
        await publisher.disconnect()
        
        assert publisher.connected is False
    
    @pytest.mark.asyncio
    async def test_publish_event_success(self, publisher, mock_channel):
        """Test successful event publishing."""
        publisher.connected = True
        publisher.channel = mock_channel
        
        event_type = "test_event"
        data = {"key": "value", "number": 42}
        correlation_id = str(uuid.uuid4())
        
        result = await publisher.publish_event(
            event_type=event_type,
            data=data,
            correlation_id=correlation_id,
        )
        
        assert result is True
        mock_channel.basic_publish.assert_called_once()
        
        # Verify the published message
        call_args = mock_channel.basic_publish.call_args
        assert call_args[1]['exchange'] == "document-events"
        assert call_args[1]['routing_key'] == "document.test_event"
        
        # Parse the published message body
        message_body = call_args[1]['body']
        message = json.loads(message_body)
        
        assert message['event_type'] == event_type
        assert message['data'] == data
        assert message['correlation_id'] == correlation_id
        assert message['service'] == "document-service"
        assert 'event_id' in message
        assert 'timestamp' in message
    
    @pytest.mark.asyncio
    async def test_publish_event_custom_routing_key(self, publisher, mock_channel):
        """Test event publishing with custom routing key."""
        publisher.connected = True
        publisher.channel = mock_channel
        
        custom_routing_key = "custom.routing.key"
        
        result = await publisher.publish_event(
            event_type="test_event",
            data={"test": "data"},
            routing_key=custom_routing_key,
        )
        
        assert result is True
        
        call_args = mock_channel.basic_publish.call_args
        assert call_args[1]['routing_key'] == custom_routing_key
    
    @pytest.mark.asyncio
    async def test_publish_event_not_connected(self, publisher):
        """Test event publishing when not connected."""
        publisher.connected = False
        publisher.channel = None
        
        result = await publisher.publish_event(
            event_type="test_event",
            data={"test": "data"},
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_publish_event_no_channel(self, publisher):
        """Test event publishing with no channel."""
        publisher.connected = True
        publisher.channel = None
        
        result = await publisher.publish_event(
            event_type="test_event",
            data={"test": "data"},
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_publish_event_exception(self, publisher, mock_channel):
        """Test event publishing with exception."""
        publisher.connected = True
        publisher.channel = mock_channel
        mock_channel.basic_publish.side_effect = Exception("Publishing failed")
        
        result = await publisher.publish_event(
            event_type="test_event",
            data={"test": "data"},
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_publish_document_uploaded(self, publisher, mock_channel):
        """Test publishing document uploaded event."""
        publisher.connected = True
        publisher.channel = mock_channel
        
        document_id = str(uuid.uuid4())
        filename = "test.pdf"
        content_type = "application/pdf"
        size_bytes = 1024
        owner_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        
        result = await publisher.publish_document_uploaded(
            document_id=document_id,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            owner_id=owner_id,
            tenant_id=tenant_id,
        )
        
        assert result is True
        mock_channel.basic_publish.assert_called_once()
        
        # Verify the message content
        call_args = mock_channel.basic_publish.call_args
        message_body = call_args[1]['body']
        message = json.loads(message_body)
        
        assert message['event_type'] == "uploaded"
        assert message['data']['document_id'] == document_id
        assert message['data']['filename'] == filename
        assert message['data']['content_type'] == content_type
        assert message['data']['size_bytes'] == size_bytes
        assert message['data']['owner_id'] == owner_id
        assert message['data']['tenant_id'] == tenant_id
    
    @pytest.mark.asyncio
    async def test_publish_document_scanned(self, publisher, mock_channel):
        """Test publishing document scanned event."""
        publisher.connected = True
        publisher.channel = mock_channel
        
        document_id = str(uuid.uuid4())
        scan_id = str(uuid.uuid4())
        result_type = "clean"
        threats = []
        tenant_id = str(uuid.uuid4())
        
        result = await publisher.publish_document_scanned(
            document_id=document_id,
            scan_id=scan_id,
            result=result_type,
            threats=threats,
            tenant_id=tenant_id,
        )
        
        assert result is True
        mock_channel.basic_publish.assert_called_once()
        
        # Verify the message content
        call_args = mock_channel.basic_publish.call_args
        message_body = call_args[1]['body']
        message = json.loads(message_body)
        
        assert message['event_type'] == "scanned"
        assert message['data']['document_id'] == document_id
        assert message['data']['scan_id'] == scan_id
        assert message['data']['result'] == result_type
        assert message['data']['threats'] == threats
        assert message['data']['tenant_id'] == tenant_id
    
    @pytest.mark.asyncio
    async def test_publish_document_scanned_with_threats(self, publisher, mock_channel):
        """Test publishing document scanned event with threats."""
        publisher.connected = True
        publisher.channel = mock_channel
        
        document_id = str(uuid.uuid4())
        scan_id = str(uuid.uuid4())
        result_type = "infected"
        threats = [
            {
                "name": "TestVirus",
                "type": "virus",
                "severity": "high",
                "description": "Test virus detected",
            }
        ]
        tenant_id = str(uuid.uuid4())
        
        result = await publisher.publish_document_scanned(
            document_id=document_id,
            scan_id=scan_id,
            result=result_type,
            threats=threats,
            tenant_id=tenant_id,
        )
        
        assert result is True
        
        # Verify threats are included
        call_args = mock_channel.basic_publish.call_args
        message_body = call_args[1]['body']
        message = json.loads(message_body)
        
        assert message['data']['threats'] == threats
        assert message['data']['result'] == "infected"
    
    @pytest.mark.asyncio
    async def test_publish_document_deleted(self, publisher, mock_channel):
        """Test publishing document deleted event."""
        publisher.connected = True
        publisher.channel = mock_channel
        
        document_id = str(uuid.uuid4())
        filename = "test.pdf"
        owner_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        
        result = await publisher.publish_document_deleted(
            document_id=document_id,
            filename=filename,
            owner_id=owner_id,
            tenant_id=tenant_id,
        )
        
        assert result is True
        mock_channel.basic_publish.assert_called_once()
        
        # Verify the message content
        call_args = mock_channel.basic_publish.call_args
        message_body = call_args[1]['body']
        message = json.loads(message_body)
        
        assert message['event_type'] == "deleted"
        assert message['data']['document_id'] == document_id
        assert message['data']['filename'] == filename
        assert message['data']['owner_id'] == owner_id
        assert message['data']['tenant_id'] == tenant_id
    
    @pytest.mark.asyncio
    async def test_health_check_connected(self, publisher, mock_channel):
        """Test health check when connected."""
        publisher.connected = True
        publisher.channel = mock_channel
        
        health = await publisher.health_check()
        assert health is True
    
    @pytest.mark.asyncio
    async def test_health_check_not_connected(self, publisher):
        """Test health check when not connected."""
        publisher.connected = False
        publisher.channel = None
        
        health = await publisher.health_check()
        assert health is False
    
    @pytest.mark.asyncio
    async def test_health_check_connected_no_channel(self, publisher):
        """Test health check when connected but no channel."""
        publisher.connected = True
        publisher.channel = None
        
        health = await publisher.health_check()
        assert health is False
    
    def test_message_properties(self, publisher, mock_channel):
        """Test that published messages have correct properties."""
        publisher.connected = True
        publisher.channel = mock_channel
        
        with patch('app.services.event_publisher.datetime') as mock_datetime:
            mock_now = datetime(2023, 7, 5, 12, 0, 0)
            mock_datetime.utcnow.return_value = mock_now
            
            asyncio.run(publisher.publish_event("test", {"data": "value"}))
        
        # Verify message properties
        call_args = mock_channel.basic_publish.call_args
        properties = call_args[1]['properties']
        
        assert properties.delivery_mode == 2  # Persistent
        assert properties.content_type == "application/json"
        assert properties.timestamp == mock_now
        assert properties.message_id is not None
    
    def test_url_parsing_with_all_components(self):
        """Test URL parsing with all components."""
        with patch('app.services.event_publisher.settings') as mock_settings:
            mock_settings.RABBITMQ_URL = "amqp://testuser:testpass@rabbit.example.com:5673/testvhost"
            mock_settings.RABBITMQ_EXCHANGE = "test-exchange"
            mock_settings.RABBITMQ_QUEUE = "test-queue"
            
            publisher = EventPublisher()
            
            with patch('pika.ConnectionParameters') as mock_params:
                with patch('app.services.event_publisher.AsyncioConnection'):
                    with patch('asyncio.get_event_loop') as mock_loop:
                        mock_loop.return_value.create_future.return_value = AsyncMock()
                        
                        try:
                            asyncio.run(publisher.connect())
                        except:
                            pass  # We expect this to fail since we're mocking
                        
                        # Verify connection parameters were created correctly
                        mock_params.assert_called_once()
                        call_args = mock_params.call_args[1]
                        
                        assert call_args['host'] == 'rabbit.example.com'
                        assert call_args['port'] == 5673
                        assert call_args['virtual_host'] == 'testvhost'
                        assert call_args['credentials'].username == 'testuser'
                        assert call_args['credentials'].password == 'testpass'
    
    def test_url_parsing_with_defaults(self):
        """Test URL parsing with missing components using defaults."""
        with patch('app.services.event_publisher.settings') as mock_settings:
            mock_settings.RABBITMQ_URL = "amqp://localhost"
            mock_settings.RABBITMQ_EXCHANGE = "test-exchange"
            mock_settings.RABBITMQ_QUEUE = "test-queue"
            
            publisher = EventPublisher()
            
            with patch('pika.ConnectionParameters') as mock_params:
                with patch('app.services.event_publisher.AsyncioConnection'):
                    with patch('asyncio.get_event_loop') as mock_loop:
                        mock_loop.return_value.create_future.return_value = AsyncMock()
                        
                        try:
                            asyncio.run(publisher.connect())
                        except:
                            pass  # We expect this to fail since we're mocking
                        
                        # Verify defaults were used
                        call_args = mock_params.call_args[1]
                        
                        assert call_args['port'] == 5672  # Default port
                        assert call_args['virtual_host'] == '/'  # Default vhost
                        assert call_args['credentials'].username == 'guest'  # Default username
                        assert call_args['credentials'].password == 'guest'  # Default password
    
    @pytest.mark.asyncio
    async def test_publish_with_datetime_serialization(self, publisher, mock_channel):
        """Test that datetime objects are properly serialized in published messages."""
        publisher.connected = True
        publisher.channel = mock_channel
        
        # Create data with datetime objects
        now = datetime.utcnow()
        data = {
            "created_at": now,
            "updated_at": now,
            "string_field": "test",
        }
        
        result = await publisher.publish_event("test_event", data)
        
        assert result is True
        
        # Verify the message was published and datetime was serialized
        call_args = mock_channel.basic_publish.call_args
        message_body = call_args[1]['body']
        
        # Should not raise JSON serialization error
        message = json.loads(message_body)
        assert message['data']['string_field'] == "test"
        # Datetime should be converted to string
        assert isinstance(message['data']['created_at'], str)


class TestGlobalEventPublisher:
    """Test global event publisher instance."""
    
    def test_global_instance_exists(self):
        """Test that global event publisher instance exists."""
        from app.services.event_publisher import event_publisher
        assert event_publisher is not None
        assert isinstance(event_publisher, EventPublisher)
    
    @pytest.mark.asyncio
    async def test_global_instance_health_check(self):
        """Test global instance health check."""
        # Should return False since it's not connected by default
        health = await event_publisher.health_check()
        assert health is False
    
    def test_global_instance_configuration(self):
        """Test global instance is configured from settings."""
        # The global instance should use the settings
        assert hasattr(event_publisher, 'exchange_name')
        assert hasattr(event_publisher, 'queue_name')
        assert event_publisher.connected is False


import asyncio