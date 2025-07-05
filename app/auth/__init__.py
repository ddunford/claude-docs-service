"""Authentication and authorization module."""

from .dependencies import (
    get_current_user,
    get_current_user_with_token,
    get_optional_user,
    require_scopes,
    require_any_scope,
    require_read_access,
    require_write_access,
    require_admin_access,
    require_read_or_write_access,
    require_tenant_access,
    validate_tenant_access,
    get_user_with_read_access,
    get_user_with_write_access,
    get_user_with_admin_access,
)
from .jwt_utils import (
    jwt_manager,
    JWTManager,
    JWTPayload,
    AuthenticatedUser,
)
from .middleware import (
    JWTAuthenticationMiddleware,
    RateLimitMiddleware,
)

__all__ = [
    # Dependencies
    "get_current_user",
    "get_current_user_with_token",
    "get_optional_user",
    "require_scopes",
    "require_any_scope",
    "require_read_access",
    "require_write_access",
    "require_admin_access",
    "require_read_or_write_access",
    "require_tenant_access",
    "validate_tenant_access",
    "get_user_with_read_access",
    "get_user_with_write_access",
    "get_user_with_admin_access",
    # JWT utilities
    "jwt_manager",
    "JWTManager",
    "JWTPayload",
    "AuthenticatedUser",
    # Middleware
    "JWTAuthenticationMiddleware",
    "RateLimitMiddleware",
]
