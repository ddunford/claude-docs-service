"""Authentication dependencies for FastAPI endpoints."""

from typing import List, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.auth.jwt_utils import jwt_manager, AuthenticatedUser
from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)
security = HTTPBearer()


def get_current_user(request: Request) -> AuthenticatedUser:
    """Get current authenticated user from request state."""
    if not hasattr(request.state, "user"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return request.state.user


def get_current_user_with_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AuthenticatedUser:
    """Get current authenticated user from token (alternative method)."""
    try:
        user = jwt_manager.authenticate_token(credentials.credentials)
        return user
    except Exception as e:
        logger.error(f"Token authentication failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_scopes(required_scopes: List[str]):
    """Dependency factory for requiring specific OAuth2 scopes."""
    def check_scopes(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        """Check if user has required scopes."""
        if not jwt_manager.verify_scopes(user.scopes, required_scopes):
            logger.warning(
                "Insufficient scopes",
                user_id=user.user_id,
                user_scopes=user.scopes,
                required_scopes=required_scopes,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient scopes. Required: {required_scopes}",
            )
        return user
    
    return check_scopes


def require_any_scope(required_scopes: List[str]):
    """Dependency factory for requiring any of the specified OAuth2 scopes."""
    def check_scopes(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        """Check if user has any of the required scopes."""
        if not user.has_any_scope(required_scopes):
            logger.warning(
                "Insufficient scopes",
                user_id=user.user_id,
                user_scopes=user.scopes,
                required_scopes=required_scopes,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient scopes. Required any of: {required_scopes}",
            )
        return user
    
    return check_scopes


def require_read_access() -> AuthenticatedUser:
    """Require document read access."""
    return require_scopes(["doc.read"])


def require_write_access() -> AuthenticatedUser:
    """Require document write access."""
    return require_scopes(["doc.write"])


def require_admin_access() -> AuthenticatedUser:
    """Require document admin access."""
    return require_scopes(["doc.admin"])


def require_read_or_write_access():
    """Require either read or write access."""
    return require_any_scope(["doc.read", "doc.write"])


def get_optional_user(request: Request) -> Optional[AuthenticatedUser]:
    """Get current user if authenticated, None otherwise."""
    if hasattr(request.state, "user"):
        return request.state.user
    return None


def validate_tenant_access(user: AuthenticatedUser, tenant_id: str) -> bool:
    """Validate that user has access to the specified tenant."""
    # Simple tenant validation (user must belong to tenant)
    if user.tenant_id != tenant_id:
        logger.warning(
            "Tenant access denied",
            user_id=user.user_id,
            user_tenant=user.tenant_id,
            requested_tenant=tenant_id,
        )
        return False
    return True


def require_tenant_access(tenant_id: str):
    """Dependency factory for requiring access to a specific tenant."""
    def check_tenant(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        """Check if user has access to the specified tenant."""
        if not validate_tenant_access(user, tenant_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to tenant",
            )
        return user
    
    return check_tenant


def get_user_with_read_access(request: Request) -> AuthenticatedUser:
    """Get current user with read access."""
    user = get_current_user(request)
    if not user.has_scope("doc.read"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Read access required",
        )
    return user


def get_user_with_write_access(request: Request) -> AuthenticatedUser:
    """Get current user with write access."""
    user = get_current_user(request)
    if not user.has_scope("doc.write"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access required",
        )
    return user


def get_user_with_admin_access(request: Request) -> AuthenticatedUser:
    """Get current user with admin access."""
    user = get_current_user(request)
    if not user.has_scope("doc.admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


# Testing dependencies (for development/testing only)
def get_mock_user() -> AuthenticatedUser:
    """Get a mock user for testing purposes."""
    import time
    import uuid
    
    # Use proper UUIDs for user and tenant
    test_user_id = "12345678-1234-5678-9012-123456789012"
    test_tenant_id = "87654321-4321-8765-2109-876543210987"
    
    mock_jwt_payload = {
        "sub": test_user_id,
        "tenant_id": test_tenant_id,
        "scopes": ["doc.read", "doc.write", "doc.admin"],
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,  # Expires in 1 hour
        "jti": "mock-jwt-id",
        "aud": "document-service",
        "iss": "test-issuer"
    }
    
    return AuthenticatedUser(
        user_id=test_user_id,
        tenant_id=test_tenant_id,
        scopes=["doc.read", "doc.write", "doc.admin"],
        jwt_payload=mock_jwt_payload
    )


def get_mock_user_with_read_access() -> AuthenticatedUser:
    """Get mock user with read access for testing."""
    return get_mock_user()


def get_mock_user_with_write_access() -> AuthenticatedUser:
    """Get mock user with write access for testing."""
    return get_mock_user()


def get_mock_user_with_admin_access() -> AuthenticatedUser:
    """Get mock user with admin access for testing."""
    return get_mock_user()
