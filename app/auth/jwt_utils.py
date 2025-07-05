"""JWT utilities for authentication and authorization."""

import jwt
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from fastapi import HTTPException, status
from pydantic import BaseModel, Field

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class JWTPayload(BaseModel):
    """JWT payload model."""
    sub: str = Field(..., description="Subject (user ID)")
    tenant_id: str = Field(..., description="Tenant ID")
    scopes: List[str] = Field(default_factory=list, description="OAuth2 scopes")
    iat: int = Field(..., description="Issued at")
    exp: int = Field(..., description="Expiration time")
    jti: Optional[str] = Field(None, description="JWT ID")
    aud: Optional[str] = Field(None, description="Audience")
    iss: Optional[str] = Field(None, description="Issuer")
    
    class Config:
        """Pydantic configuration."""
        extra = "allow"


class AuthenticatedUser(BaseModel):
    """Authenticated user model."""
    user_id: str
    tenant_id: str
    scopes: List[str]
    jwt_payload: Dict[str, Any]
    
    def has_scope(self, required_scope: str) -> bool:
        """Check if user has required scope."""
        return required_scope in self.scopes
    
    def has_any_scope(self, required_scopes: List[str]) -> bool:
        """Check if user has any of the required scopes."""
        return any(scope in self.scopes for scope in required_scopes)
    
    def has_all_scopes(self, required_scopes: List[str]) -> bool:
        """Check if user has all required scopes."""
        return all(scope in self.scopes for scope in required_scopes)


class JWTManager:
    """JWT token manager."""
    
    def __init__(self):
        """Initialize JWT manager."""
        self.secret_key = settings.JWT_SECRET_KEY
        self.algorithm = settings.JWT_ALGORITHM
        self.expiration_minutes = settings.JWT_EXPIRATION_MINUTES
    
    def create_access_token(
        self,
        user_id: str,
        tenant_id: str,
        scopes: List[str],
        expires_delta: Optional[timedelta] = None,
        **kwargs: Any,
    ) -> str:
        """Create a JWT access token."""
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=self.expiration_minutes)
        
        payload = {
            "sub": user_id,
            "tenant_id": tenant_id,
            "scopes": scopes,
            "iat": datetime.utcnow(),
            "exp": expire,
            **kwargs,
        }
        
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        
        logger.info(
            "JWT token created",
            user_id=user_id,
            tenant_id=tenant_id,
            scopes=scopes,
            expires_at=expire.isoformat(),
        )
        
        return token
    
    def decode_token(self, token: str) -> JWTPayload:
        """Decode and validate JWT token."""
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iat": True,
                    "require_exp": True,
                    "require_iat": True,
                    "require_sub": True,
                },
            )
            
            # Validate payload structure
            jwt_payload = JWTPayload(**payload)
            
            logger.debug(
                "JWT token decoded",
                user_id=jwt_payload.sub,
                tenant_id=jwt_payload.tenant_id,
                scopes=jwt_payload.scopes,
            )
            
            return jwt_payload
            
        except jwt.ExpiredSignatureError:
            logger.warning("JWT token expired")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.PyJWTError as e:
            logger.warning(f"JWT token validation failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception as e:
            logger.error(f"JWT token decode error: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token validation failed",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    def verify_scopes(self, token_scopes: List[str], required_scopes: List[str]) -> bool:
        """Verify that token has required scopes."""
        if not required_scopes:
            return True
        
        for scope in required_scopes:
            if scope not in token_scopes:
                logger.warning(
                    "Insufficient scope",
                    token_scopes=token_scopes,
                    required_scopes=required_scopes,
                    missing_scope=scope,
                )
                return False
        
        return True
    
    def authenticate_token(self, token: str) -> AuthenticatedUser:
        """Authenticate and return user from token."""
        # Remove 'Bearer ' prefix if present
        if token.startswith("Bearer "):
            token = token[7:]
        
        # Decode token
        jwt_payload = self.decode_token(token)
        
        # Create authenticated user
        user = AuthenticatedUser(
            user_id=jwt_payload.sub,
            tenant_id=jwt_payload.tenant_id,
            scopes=jwt_payload.scopes,
            jwt_payload=jwt_payload.dict(),
        )
        
        return user


# Global JWT manager instance
jwt_manager = JWTManager()
