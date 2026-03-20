import os
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from fastapi import Header, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr, validator
from dotenv import load_dotenv

load_dotenv()

# Required Environment Variables Audit
SECRET_KEY = os.getenv("JWT_SECRET")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH")
USER_PASSWORD_HASH = os.getenv("USER_PASSWORD_HASH")

# Fail on startup if critical secrets are missing
if not all([SECRET_KEY, INTERNAL_API_KEY, ADMIN_PASSWORD_HASH, USER_PASSWORD_HASH]):
    missing = [k for k, v in {
        "JWT_SECRET": SECRET_KEY,
        "INTERNAL_API_KEY": INTERNAL_API_KEY,
        "ADMIN_PASSWORD_HASH": ADMIN_PASSWORD_HASH,
        "USER_PASSWORD_HASH": USER_PASSWORD_HASH
    }.items() if not v]
    raise RuntimeError(f"Missing required security environment variables: {', '.join(missing)}")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
ALLOWED_DOMAIN = "@harrisandtrotter.co.uk"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

class Token(BaseModel):
    access_token: str
    token_type: str

class UserPayload(BaseModel):
    email: str
    role: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    @validator("email")
    def validate_domain(cls, v):
        if not v.endswith(ALLOWED_DOMAIN):
            raise ValueError(f"Only internal emails ({ALLOWED_DOMAIN}) are allowed.")
        return v

# Password Utility
def verify_password(plain_password: str, hashed_password: str):
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

# JWT Creation
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# API Key Validation Dependency
async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Validates the Internal API Key header."""
    if not x_api_key or x_api_key != INTERNAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key",
            headers={"X-Auth-Error": "Invalid API Key"}
        )
    return x_api_key

# JWT Token Validation Dependency
async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Validates the Bearer JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("email")
        role: str = payload.get("role")
        if email is None or not email.endswith(ALLOWED_DOMAIN) or role not in ["user", "admin"]:
            raise credentials_exception
        return UserPayload(email=email, role=role)
    except JWTError:
        raise credentials_exception

# --- COMBINED SECURITY LAYER ---

def require_role(required_roles: list[str]):
    """
    Role-based access control dependency factory.
    Extracts user from JWT and ensures their role is in the allowed list.
    """
    async def role_checker(user: UserPayload = Depends(get_current_user)):
        if user.role not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this operation"
            )
        return user
    return role_checker

def require_secure_role(required_roles: list[str]):
    """
    Production-grade joint authentication:
    1. Valid JWT Token with required role
    2. Valid Internal API Key (X-API-Key header)
    """
    async def secure_role_checker(
        user: UserPayload = Depends(require_role(required_roles)),
        api_key: str = Depends(verify_api_key)
    ):
        return {"user": user, "api_key_valid": True}
    return secure_role_checker
