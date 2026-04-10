from fastapi import HTTPException, Header
from app.core.supabase import supabase
from app.core.config import settings


async def get_current_user(authorization: str = Header(...)):
    """
    Authorization: Bearer <supabase_access_token>
    Verify token with Supabase and return user info.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="AUTH_REQUIRED")

    token = authorization.replace("Bearer ", "")

    try:
        response = supabase.auth.get_user(token)
        return response.user
    except Exception:
        raise HTTPException(status_code=401, detail="AUTH_REQUIRED")


def verify_qstash_signature(body: bytes, signature: str) -> bool:
    """Verify QStash webhook signature using JWT verification"""

    # Skip verification in local development
    if settings.QSTASH_CURRENT_SIGNING_KEY == "local-dummy":
        return True

    from qstash import Receiver

    receiver = Receiver(
        current_signing_key=settings.QSTASH_CURRENT_SIGNING_KEY,
        next_signing_key=settings.QSTASH_NEXT_SIGNING_KEY,
    )

    try:
        receiver.verify(
            body=body.decode("utf-8"),
            signature=signature,
        )
        return True
    except Exception as e:
        print(f"QStash signature verification failed: {e}")
        return False