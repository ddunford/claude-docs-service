"""Unit tests for authentication components."""

import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

import jwt
import pytest
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

from app.auth.jwt_utils import JWTManager, JWTPayload, AuthenticatedUser, jwt_manager
from app.auth.dependencies import (
    get_current_user,
    get_current_user_with_token,
    require_scopes,
    require_read_access,
    require_write_access,
    require_admin_access,
    validate_tenant_access,
)
from app.auth.middleware import JWTAuthenticationMiddleware, RateLimitMiddleware
from app.config import settings


class TestJWTManager:
    """Test JWT manager."""
    
    @pytest.fixture
    def jwt_manager_instance(self):
        """Create JWT manager instance."""
        return JWTManager()
    
    def test_create_access_token(self, jwt_manager_instance):
        """Test JWT token creation."""
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        scopes = ["doc.read", "doc.write"]
        
        token = jwt_manager_instance.create_access_token(
            user_id=user_id,
            tenant_id=tenant_id,
            scopes=scopes,
        )
        
        assert isinstance(token, str)
        assert len(token) > 0
        
        # Decode and verify token
        decoded = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        
        assert decoded["sub"] == user_id
        assert decoded["tenant_id"] == tenant_id
        assert decoded["scopes"] == scopes
        assert "iat" in decoded
        assert "exp" in decoded
    
    def test_create_access_token_with_custom_expiry(self, jwt_manager_instance):
        """Test JWT token creation with custom expiry."""
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        scopes = ["doc.read"]
        expires_delta = timedelta(hours=1)
        
        token = jwt_manager_instance.create_access_token(
            user_id=user_id,
            tenant_id=tenant_id,
            scopes=scopes,
            expires_delta=expires_delta,
        )
        
        decoded = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        
        # Check expiry is approximately 1 hour from now
        exp_time = datetime.utcfromtimestamp(decoded["exp"])
        expected_exp = datetime.utcnow() + expires_delta
        assert abs((exp_time - expected_exp).total_seconds()) < 60  # Within 1 minute
    
    def test_decode_token_success(self, jwt_manager_instance):
        """Test successful JWT token decoding."""
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        scopes = ["doc.read", "doc.write"]
        
        token = jwt_manager_instance.create_access_token(
            user_id=user_id,
            tenant_id=tenant_id,
            scopes=scopes,
        )
        
        payload = jwt_manager_instance.decode_token(token)
        
        assert isinstance(payload, JWTPayload)
        assert payload.sub == user_id
        assert payload.tenant_id == tenant_id
        assert payload.scopes == scopes
    
    def test_decode_token_expired(self, jwt_manager_instance):
        """Test JWT token decoding with expired token."""
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        scopes = ["doc.read"]
        
        # Create token that expires immediately
        token = jwt_manager_instance.create_access_token(
            user_id=user_id,
            tenant_id=tenant_id,
            scopes=scopes,
            expires_delta=timedelta(seconds=-1),  # Already expired
        )
        
        with pytest.raises(HTTPException) as exc_info:
            jwt_manager_instance.decode_token(token)
        
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()
    
    def test_decode_token_invalid(self, jwt_manager_instance):
        """Test JWT token decoding with invalid token."""
        invalid_token = "invalid.token.here"
        
        with pytest.raises(HTTPException) as exc_info:
            jwt_manager_instance.decode_token(invalid_token)
        
        assert exc_info.value.status_code == 401
        assert "invalid" in exc_info.value.detail.lower()
    
    def test_verify_scopes_success(self, jwt_manager_instance):
        """Test successful scope verification."""
        token_scopes = ["doc.read", "doc.write", "doc.admin"]
        required_scopes = ["doc.read", "doc.write"]
        
        result = jwt_manager_instance.verify_scopes(token_scopes, required_scopes)
        assert result is True
    
    def test_verify_scopes_insufficient(self, jwt_manager_instance):
        """Test scope verification with insufficient scopes."""
        token_scopes = ["doc.read"]
        required_scopes = ["doc.read", "doc.write"]
        
        result = jwt_manager_instance.verify_scopes(token_scopes, required_scopes)
        assert result is False
    
    def test_verify_scopes_empty_required(self, jwt_manager_instance):
        """Test scope verification with empty required scopes."""
        token_scopes = ["doc.read"]
        required_scopes = []
        
        result = jwt_manager_instance.verify_scopes(token_scopes, required_scopes)
        assert result is True
    
    def test_authenticate_token_success(self, jwt_manager_instance):
        """Test successful token authentication."""
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        scopes = ["doc.read", "doc.write"]
        
        token = jwt_manager_instance.create_access_token(
            user_id=user_id,
            tenant_id=tenant_id,
            scopes=scopes,
        )
        
        user = jwt_manager_instance.authenticate_token(token)
        
        assert isinstance(user, AuthenticatedUser)
        assert user.user_id == user_id
        assert user.tenant_id == tenant_id
        assert user.scopes == scopes
    
    def test_authenticate_token_with_bearer_prefix(self, jwt_manager_instance):
        """Test token authentication with Bearer prefix."""
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        scopes = ["doc.read"]
        
        token = jwt_manager_instance.create_access_token(
            user_id=user_id,
            tenant_id=tenant_id,
            scopes=scopes,
        )
        
        user = jwt_manager_instance.authenticate_token(f"Bearer {token}")
        
        assert isinstance(user, AuthenticatedUser)
        assert user.user_id == user_id


class TestAuthenticatedUser:
    """Test authenticated user model."""
    
    @pytest.fixture
    def user(self):
        """Create authenticated user."""
        return AuthenticatedUser(
            user_id=str(uuid.uuid4()),
            tenant_id=str(uuid.uuid4()),
            scopes=["doc.read", "doc.write"],
            jwt_payload={"sub": "test", "tenant_id": "test"},
        )
    
    def test_has_scope_success(self, user):
        """Test has_scope method with existing scope."""
        assert user.has_scope("doc.read") is True
        assert user.has_scope("doc.write") is True
    
    def test_has_scope_missing(self, user):
        """Test has_scope method with missing scope."""
        assert user.has_scope("doc.admin") is False
    
    def test_has_any_scope_success(self, user):
        """Test has_any_scope method with matching scopes."""
        assert user.has_any_scope(["doc.read", "doc.admin"]) is True
        assert user.has_any_scope(["doc.write", "doc.admin"]) is True
    
    def test_has_any_scope_none_match(self, user):
        """Test has_any_scope method with no matching scopes."""
        assert user.has_any_scope(["doc.admin", "doc.delete"]) is False
    
    def test_has_all_scopes_success(self, user):
        """Test has_all_scopes method with all scopes present."""
        assert user.has_all_scopes(["doc.read", "doc.write"]) is True
        assert user.has_all_scopes(["doc.read"]) is True
    
    def test_has_all_scopes_missing(self, user):
        """Test has_all_scopes method with missing scopes."""
        assert user.has_all_scopes(["doc.read", "doc.admin"]) is False


class TestDependencies:
    """Test authentication dependencies."""
    
    @pytest.fixture
    def mock_user(self):
        """Create mock authenticated user."""
        return AuthenticatedUser(
            user_id=str(uuid.uuid4()),
            tenant_id=str(uuid.uuid4()),
            scopes=["doc.read", "doc.write"],
            jwt_payload={"sub": "test", "tenant_id": "test"},
        )
    
    def test_get_current_user_success(self, mock_user):
        """Test get_current_user with authenticated user."""
        request = Mock()
        request.state.user = mock_user
        
        user = get_current_user(request)
        assert user == mock_user
    
    def test_get_current_user_no_auth(self):
        """Test get_current_user without authentication."""
        request = Mock()
        del request.state.user  # No user in state
        
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(request)
        
        assert exc_info.value.status_code == 401
    
    def test_get_current_user_with_token_success(self, mock_user):
        """Test get_current_user_with_token with valid token."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="valid-token",
        )
        
        with patch.object(jwt_manager, "authenticate_token", return_value=mock_user):
            user = get_current_user_with_token(credentials)
            assert user == mock_user
    
    def test_require_scopes_success(self, mock_user):
        """Test require_scopes with sufficient scopes."""
        check_scopes = require_scopes(["doc.read"])
        
        # Call the function directly with the user
        user = check_scopes(mock_user)
        assert user == mock_user
    
    def test_require_scopes_insufficient(self, mock_user):
        """Test require_scopes with insufficient scopes."""
        check_scopes = require_scopes(["doc.admin"])
        
        with pytest.raises(HTTPException) as exc_info:
            check_scopes(mock_user)
        
        assert exc_info.value.status_code == 403
    
    def test_validate_tenant_access_success(self, mock_user):
        """Test validate_tenant_access with matching tenant."""
        result = validate_tenant_access(mock_user, mock_user.tenant_id)
        assert result is True
    
    def test_validate_tenant_access_denied(self, mock_user):
        """Test validate_tenant_access with different tenant."""
        different_tenant = str(uuid.uuid4())
        result = validate_tenant_access(mock_user, different_tenant)
        assert result is False


class TestJWTAuthenticationMiddleware:
    """Test JWT authentication middleware."""
    
    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        app = Mock()
        return JWTAuthenticationMiddleware(app)
    
    def test_is_exempt_path(self, middleware):
        """Test exempt path checking."""
        assert middleware._is_exempt_path("/health") is True
        assert middleware._is_exempt_path("/metrics") is True
        assert middleware._is_exempt_path("/docs") is True
        assert middleware._is_exempt_path("/api/v1/documents") is False
    
    @pytest.mark.asyncio
    async def test_dispatch_exempt_path(self, middleware):
        """Test middleware dispatch with exempt path."""
        request = Mock()
        request.url.path = "/health"
        
        call_next = AsyncMock()
        expected_response = Mock()
        call_next.return_value = expected_response
        
        result = await middleware.dispatch(request, call_next)
        
        call_next.assert_called_once_with(request)
        assert result == expected_response
    
    @pytest.mark.asyncio
    async def test_dispatch_no_auth_header(self, middleware):
        """Test middleware dispatch without Authorization header."""
        request = Mock()
        request.url.path = "/api/v1/documents"
        request.headers = {}
        
        call_next = Mock()
        
        result = await middleware.dispatch(request, call_next)
        
        assert result.status_code == 401
        call_next.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_dispatch_success(self, middleware):
        """Test middleware dispatch with valid authentication."""
        mock_user = AuthenticatedUser(
            user_id=str(uuid.uuid4()),
            tenant_id=str(uuid.uuid4()),
            scopes=["doc.read"],
            jwt_payload={"sub": "test"},
        )
        
        request = Mock()
        request.url.path = "/api/v1/documents"
        request.method = "GET"
        request.headers = {"Authorization": "Bearer valid-token"}
        request.state = Mock()
        
        call_next = AsyncMock()
        expected_response = Mock()
        call_next.return_value = expected_response
        
        with patch.object(jwt_manager, "authenticate_token", return_value=mock_user):
            result = await middleware.dispatch(request, call_next)
        
        assert request.state.user == mock_user
        call_next.assert_called_once_with(request)
        assert result == expected_response


class TestRateLimitMiddleware:
    """Test rate limiting middleware."""
    
    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        app = Mock()
        return RateLimitMiddleware(app, requests_per_minute=5)
    
    def test_get_client_id_with_user(self, middleware):
        """Test client ID generation with authenticated user."""
        mock_user = Mock()
        mock_user.user_id = "test-user-id"
        
        request = Mock()
        request.state.user = mock_user
        
        client_id = middleware._get_client_id(request)
        assert client_id == "user:test-user-id"
    
    def test_get_client_id_with_ip(self, middleware):
        """Test client ID generation with IP address."""
        request = Mock()
        request.client.host = "192.168.1.1"
        del request.state.user  # No user
        
        client_id = middleware._get_client_id(request)
        assert client_id == "ip:192.168.1.1"
    
    @pytest.mark.asyncio
    async def test_dispatch_under_limit(self, middleware):
        """Test middleware dispatch under rate limit."""
        request = Mock()
        request.client.host = "192.168.1.1"
        request.url.path = "/api/v1/documents"
        request.method = "GET"
        
        call_next = AsyncMock()
        expected_response = Mock()
        call_next.return_value = expected_response
        
        result = await middleware.dispatch(request, call_next)
        
        call_next.assert_called_once_with(request)
        assert result == expected_response
    
    @pytest.mark.asyncio
    async def test_dispatch_over_limit(self, middleware):
        """Test middleware dispatch over rate limit."""
        request = Mock()
        request.client.host = "192.168.1.1"
        request.url.path = "/api/v1/documents"
        request.method = "GET"
        
        call_next = AsyncMock()
        
        # Mock the rate limit check to return True (rate limited)
        with patch.object(middleware, '_is_rate_limited', return_value=True):
            result = await middleware.dispatch(request, call_next)
        
        assert result.status_code == 429
        call_next.assert_not_called()
