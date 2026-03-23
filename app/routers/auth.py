from fastapi import APIRouter, Header
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    SocialLoginRequest,
    RefreshTokenRequest,
    AuthResponse,
    RegisterResponse,
)
from app.services.auth_service import AuthService

router = APIRouter()
auth_service = AuthService()


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(req: RegisterRequest):
    """Register new user with email and password"""
    return auth_service.register(req)


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest):
    """Login with email and password"""
    return auth_service.login(req)


@router.post("/social")
async def social_login(req: SocialLoginRequest):
    """Login with Google or Apple"""
    return auth_service.social_login(req)


@router.post("/refresh")
async def refresh_token(req: RefreshTokenRequest):
    """Reissue access token"""
    return auth_service.refresh_token(req.refresh_token)


@router.delete("/logout", status_code=200)
async def logout(authorization: str = Header(...)):
    """Logout and invalidate session"""
    token = authorization.replace("Bearer ", "")
    auth_service.logout(token)
    return {"message": "Successfully logged out"}