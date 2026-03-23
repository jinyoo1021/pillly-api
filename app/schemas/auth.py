from pydantic import BaseModel, EmailStr


# ── Request models ──

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    timezone: str = "Asia/Seoul"
    language: str = "ko"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SocialLoginRequest(BaseModel):
    provider: str   # "google" | "apple"
    id_token: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# ── Response models ──

class UserResponse(BaseModel):
    id: str
    email: str | None
    name: str | None
    language: str | None


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: UserResponse


class RegisterResponse(BaseModel):
    user_id: str
    email: str
    access_token: str
    refresh_token: str