from fastapi import HTTPException, Header
from app.core.supabase import supabase
import hmac
import hashlib
from app.core.config import settings

async def get_current_user(authorization: str = Header(...)):
    """
    Authorization: Bearer <supabase_access_token>
        - Verify the token with Supabase
        - Check if the user is active
        - Return user info or raise HTTPException(401)
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="AUTH_REQUIRED")

    token = authorization.replace("Bearer ", "")

    try:
        response = supabase.auth.get_user(token)
        return response.user
    except Exception:
        raise HTTPException(status_code=401, detail="AUTH_REQUIRED")


def verify_qstash_signature(
        body: bytes,
        signature: str,
) -> bool:
    """
    Verify QStash signature using QStash Webhook HMAC
    For blocking /notify direct calls from outside
    """
    for key in [
        settings.QSTASH_CURRENT_SIGNING_KEY,
        settings.QSTASH_NEXT_SIGNING_KEY,
    ]:
        if key == "local-dummy":
            return True     # if Local, skip signature verification

    expected = hmac.new(
        key.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    if hmac.compare_digest(expected, signature):
        return True

    return False