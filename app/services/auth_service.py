from fastapi import HTTPException
from app.core.supabase import supabase
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    SocialLoginRequest,
)

class AuthService:

    def register(self, req: RegisterRequest) -> dict:
        """Register new user with email and password"""
        try:
            response = supabase.auth.sign_up({
                "email": req.email,
                "password": req.password,
                "options": {
                    "data": {
                        "name": req.name,
                        "timezone": req.timezone,
                        "language": req.language,
                    }
                },
            })

            if not response.user:
                raise HTTPException(
                    status_code = 400,
                    detail = "EMAIL_ALREADY_EXISTS",
                )

            return {
                "user_id": response.user.id,
                "email": response.user.email,
                "access_token": response.session.access_token,
                "refresh_token": response.session.refresh_token,
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    def login(self, req: LoginRequest) -> dict:
        """Login with email and password"""
        try:
            reponse = supabase.auth.sign_in_with_password({
                "email": req.email,
                "password": req.password,
            })

            return {
                "access_token": reponse.session.access_token,
                "refresh_token": reponse.session.refresh_token,
                "user": {
                    "id": reponse.user.id,
                    "email": reponse.user.email,
                    "name": reponse.user.user_metadata.get("name"),
                    "language": reponse.user.user_metadata.get("language", "ko",),
                },
            }

        except Exception:
            raise HTTPException(
                status_code = 400,
                detail = "INVALID_CREDENTIALS",
            )

    def social_login(self, req: SocialLoginRequest) -> dict:
        """Login with Google or Apple OAuth token"""
        try:
            reponse = supabase.auth.sign_up_with_id_token({
                "provider": req.provider,
                "id_token": req.id_token,
            })

            is_new_user = (
                response.user.created_at == response.user.updated_at
            )

            return {
                "access_token": reponse.session.access_token,
                "refresh_token": reponse.session.refresh_token,
                "is_new_user": is_new_user,
                "user": {
                    "id": reponse.user.id,
                    "email": reponse.user.email,
                    "name": reponse.user.user_metadata.get("name"),
                    "language": reponse.user.user_metadata.get("language", "ko",),
                },
            }

        except Exception:
            raise HTTPException(
                status_code = 400,
                detail = "INVALID_TOKEN",
            )

    def refresh_token(self, refresh_token: str) -> dict:
        """Reissue access token using refresh token"""
        try:
            response = supabase.auth.refresh_session(refresh_token)

            return {
                "access_token": response.session.access_token,
            }

        except Exception as e:
            raise HTTPException(
                status_code=401,
                detail=str(e),
            )

    def logout(self, refresh_token: str) -> None:
        """Logout by revoking the refresh token"""
        try:
            supabase.auth.sign_out()
        except Exception:
            pass # Ignore errors during logout, as it is not critical
