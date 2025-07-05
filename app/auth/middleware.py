"""Authentication middleware for FastAPI."""

from typing import List, Optional, Callable

from fastapi import HTTPException, Request, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.auth.jwt_utils import jwt_manager, AuthenticatedUser
from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class JWTAuthenticationMiddleware(BaseHTTPMiddleware):
    """JWT authentication middleware."""
    
    def __init__(self, app, exempt_paths: Optional[List[str]] = None):
        """Initialize JWT authentication middleware."""
        super().__init__(app)
        self.exempt_paths = exempt_paths or [
            "/health",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
        ]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with JWT authentication."""
        # Check if path is exempt from authentication
        if self._is_exempt_path(request.url.path):
            return await call_next(request)
        
        # Extract token from Authorization header
        authorization = request.headers.get("Authorization")
        if not authorization:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error": "authentication_required",
                    "message": "Authorization header is required",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        try:
            # Authenticate user
            user = jwt_manager.authenticate_token(authorization)
            
            # Add user to request state
            request.state.user = user
            
            # Log successful authentication
            logger.info(
                "User authenticated",
                user_id=user.user_id,
                tenant_id=user.tenant_id,
                scopes=user.scopes,
                path=request.url.path,
                method=request.method,
            )
            
            return await call_next(request)
            
        except HTTPException as e:
            # Return authentication error
            return JSONResponse(
                status_code=e.status_code,
                content={
                    "error": "authentication_failed",
                    "message": e.detail,
                },
                headers=e.headers or {},
            )
        except Exception as e:
            logger.error(f"Authentication middleware error: {e}")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": "internal_server_error",
                    "message": "Authentication processing failed",
                },
            )
    
    def _is_exempt_path(self, path: str) -> bool:
        """Check if path is exempt from authentication."""
        return any(path.startswith(exempt) for exempt in self.exempt_paths)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware."""
    
    def __init__(self, app, requests_per_minute: int = 100):
        """Initialize rate limiting middleware."""
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.request_counts = {}  # In production, use Redis
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with rate limiting."""
        # Get client identifier (IP or user ID)
        client_id = self._get_client_id(request)
        
        # Check rate limit
        if self._is_rate_limited(client_id):
            logger.warning(
                "Rate limit exceeded",
                client_id=client_id,
                path=request.url.path,
                method=request.method,
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "rate_limit_exceeded",
                    "message": f"Rate limit of {self.requests_per_minute} requests per minute exceeded",
                },
                headers={
                    "X-RateLimit-Limit": str(self.requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": "60",
                },
            )
        
        # Increment request count
        self._increment_request_count(client_id)
        
        return await call_next(request)
    
    def _get_client_id(self, request: Request) -> str:
        """Get client identifier for rate limiting."""
        # Try to get user ID from authenticated user
        if hasattr(request.state, "user"):
            return f"user:{request.state.user.user_id}"
        
        # Fallback to IP address
        client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}"
    
    def _is_rate_limited(self, client_id: str) -> bool:
        """Check if client is rate limited."""
        # Simple in-memory rate limiting (use Redis in production)
        import time
        
        now = time.time()
        minute_window = int(now // 60)
        
        if client_id not in self.request_counts:
            self.request_counts[client_id] = {}
        
        # Clean old windows
        for window in list(self.request_counts[client_id].keys()):
            if window < minute_window - 1:
                del self.request_counts[client_id][window]
        
        # Check current window
        current_count = self.request_counts[client_id].get(minute_window, 0)
        return current_count >= self.requests_per_minute
    
    def _increment_request_count(self, client_id: str):
        """Increment request count for client."""
        import time
        
        now = time.time()
        minute_window = int(now // 60)
        
        if client_id not in self.request_counts:
            self.request_counts[client_id] = {}
        
        self.request_counts[client_id][minute_window] = (
            self.request_counts[client_id].get(minute_window, 0) + 1
        )
